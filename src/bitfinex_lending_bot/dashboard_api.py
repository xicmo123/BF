from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body

from .config import load_settings
from .security import encrypt_secret
from .storage import SQLiteRepository
from .notifier import TelegramNotifier

app = FastAPI(title="Lending Bot Ops Dashboard")

settings = load_settings()
repo = SQLiteRepository(settings.database_path)
repo.initialize()
notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id)

app.mount("/static", StaticFiles(directory="./src/bitfinex_lending_bot/web/static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    with open("src/bitfinex_lending_bot/web/dashboard.html", "r") as fh:
        return HTMLResponse(fh.read())


@app.get("/metrics")
def metrics(symbol: str | None = None, limit: int = 100):
    symbol = symbol or settings.default_currency
    apy = repo.get_apy_series(symbol, limit)
    pnl = repo.get_pnl_series(symbol, limit)
    execution_success = repo.get_metrics("execution_success", limit)
    execution_failure = repo.get_metrics("execution_failure", limit)
    api_failures = repo.get_metrics("api_failure", limit)

    # Latest risk decision for idle_cash + exposure snapshot
    latest_risk = repo.latest_risk_decision()
    idle_cash = None
    active_exposure_val = None
    total_capital_val = None
    if latest_risk is not None:
        idle_cash = latest_risk.get("idle_cash")
        active_exposure_val = latest_risk.get("active_exposure")
        total_capital_val = latest_risk.get("total_capital")

    # Also compute from latest wallets for live view
    # Query both USD and UST idle cash independently
    open_offers_total = None
    wallet_balance = None
    wallet_available = None
    idle_cash_from_wallet = None

    def _decimal_or_zero(value: object) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    def _wallet_amount(wallet: dict[str, str] | None, key: str) -> Decimal | None:
        if wallet is None or key not in wallet:
            return None
        return _decimal_or_zero(wallet.get(key))

    def _wallet_provided(wallet: dict[str, str] | None, holding_offers: Decimal) -> Decimal | None:
        """Return provided amount from wallet column if available, otherwise infer it.

        Some databases may already have Bitfinex wallet snapshot columns such as
        `holding_offers` and `provided`. The repository returns all columns from
        the actual wallets table, so use them when present. For older schemas,
        approximate provided as balance - available_balance - holding_offers.
        """
        explicit_provided = _wallet_amount(wallet, "provided")
        if explicit_provided is not None:
            return explicit_provided
        if wallet is None:
            return None
        inferred = (
            _decimal_or_zero(wallet.get("balance"))
            - _decimal_or_zero(wallet.get("available_balance"))
            - holding_offers
        )
        return max(inferred, Decimal("0"))
    
    # Query USD funding wallet
    funding_wallet_usd = repo.latest_wallet_by_type_and_currency("funding", "USD")
    idle_usd = None
    if funding_wallet_usd:
        idle_usd = funding_wallet_usd.get("available_balance")
    
    # Query UST (USDT) funding wallet
    funding_wallet_ust = repo.latest_wallet_by_type_and_currency("funding", "UST")
    idle_usdt = None
    if funding_wallet_ust:
        idle_usdt = funding_wallet_ust.get("available_balance")
    
    # Query active offers/provided totals for USD and UST.
    # Prefer wallet snapshot columns when present; otherwise fall back to
    # active funding_offers rows for offers and infer provided from wallet totals.
    offers_usd = _wallet_amount(funding_wallet_usd, "holding_offers")
    if offers_usd is None:
        offers_usd = repo.get_active_offers_total_by_currency("fUSD")
    offers_usdt = _wallet_amount(funding_wallet_ust, "holding_offers")
    if offers_usdt is None:
        offers_usdt = repo.get_active_offers_total_by_currency("fUST")
    provided_usd = _wallet_provided(funding_wallet_usd, offers_usd)
    provided_usdt = _wallet_provided(funding_wallet_ust, offers_usdt)
    
    # For backward compatibility, also compute the original single currency value
    wallet_currency = symbol[1:] if symbol.startswith('f') else symbol
    funding_wallet = repo.latest_wallet_by_type_and_currency("funding", wallet_currency)
    if funding_wallet:
        wallet_balance = funding_wallet.get("balance")
        wallet_available = funding_wallet.get("available_balance")
        idle_cash_from_wallet = wallet_available

    return JSONResponse({
        "symbol": symbol,
        "apy": apy,
        "pnl": pnl,
        "execution_success": execution_success,
        "execution_failure": execution_failure,
        "api_failures": api_failures,
        "idle_cash": idle_cash_from_wallet,  # Use funding wallet available balance
        "idle_usd": idle_usd,
        "idle_usdt": idle_usdt,
        "offers_usd": str(offers_usd),
        "offers_usdt": str(offers_usdt),
        "provided_usd": str(provided_usd or Decimal("0")),
        "provided_usdt": str(provided_usdt or Decimal("0")),
        "active_exposure": active_exposure_val,
        "total_capital": total_capital_val,
        "wallet_balance": wallet_balance,
        "wallet_available": wallet_available,
    })


@app.get("/health")
def health():
    from .ops import OpsManager

    ops = OpsManager(repo, notifier, settings)
    return JSONResponse(ops.get_health_report())


@app.get("/rollout")
def rollout():
    state = repo.get_rollout_state()
    return JSONResponse(state or {})


@app.get("/rollout/state")
def rollout_state():
    state = repo.get_rollout_state()
    history = repo.get_rollout_history(100)
    return JSONResponse({"state": state or {}, "history": history})


@app.get("/rollout/settings")
def rollout_settings():
    settings_row = repo.get_rollout_settings()
    return JSONResponse(settings_row or {})


@app.post("/rollout/set")
def rollout_set(payload: dict = Body(...)):
    # payload: {"percent": 1|5|10|25}
    allowed = {1, 5, 10, 25}
    percent = float(payload.get("percent", 0))
    if percent not in allowed:
        return JSONResponse({"error": "invalid percent"}, status_code=400)

    # compute failure rate from recent metrics
    succ = repo.get_metrics("execution_success", 200)
    fail = repo.get_metrics("execution_failure", 200)
    total = len(succ) + len(fail)
    failure_rate = (len(fail) / total) if total > 0 else 0.0
    # threshold: disallow upgrade if failure_rate > 0.05
    threshold = 0.05
    if failure_rate > threshold and percent > float((repo.get_rollout_state() or {}).get("allocation_percent", 0)):
        return JSONResponse({"error": "failure_rate_too_high", "failure_rate": failure_rate}, status_code=403)

    # determine stage from percent
    stage_map = {1: 1, 5: 2, 10: 3, 25: 4}
    stage = stage_map.get(int(percent), 0)
    repo.set_rollout_state(stage, percent, 100.0)
    repo.add_rollout_history(stage, percent, "SET", f"manual set to {percent}% failure_rate={failure_rate}")
    return JSONResponse({"ok": True, "percent": percent, "failure_rate": failure_rate})


@app.post("/rollout/stop")
def rollout_stop(payload: dict = Body({})):
    # Emergency stop: set allocation to 0
    repo.set_rollout_state(0, 0.0, 100.0)
    repo.add_rollout_history(0, 0.0, "STOP", payload.get("reason", "manual stop"))
    return JSONResponse({"ok": True})


@app.post("/rollout/auto/run")
def rollout_auto_run():
    """
    Webhook endpoint for external scheduler to trigger auto-rollout evaluation.
    Checks auto_enabled flag in settings before executing.
    """
    try:
        from .ops import OpsManager

        # check if auto is enabled
        settings_row = repo.get_rollout_settings()
        auto_enabled = settings_row and int(settings_row.get("auto_enabled", "0") or 0) == 1 if settings_row else False
        
        if not auto_enabled:
            return JSONResponse({"skipped": True, "reason": "auto_enabled is False"}, status_code=200)
        
        ops = OpsManager(repo, notifier, settings)
        res = ops.run_auto_rollout()
        return JSONResponse({"ok": True, "result": res})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/rollout/auto/enable")
def rollout_auto_enable():
    """Enable auto-rollout flag. External scheduler will trigger /rollout/auto/run."""
    try:
        repo.set_rollout_settings(True, "AUTO_ENABLED", "enabled via API")
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/rollout/auto/disable")
def rollout_auto_disable():
    """Disable auto-rollout flag. External scheduler will skip /rollout/auto/run calls."""
    try:
        repo.set_rollout_settings(False, "AUTO_DISABLED", "disabled via API")
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)



@app.post("/api/settings/keys")
def save_api_keys(payload: dict = Body(...)):
    """Save (or update) Bitfinex API credentials with encrypted secret."""
    user_id = (payload.get("user_id") or "default_user").strip()
    api_key = (payload.get("api_key") or "").strip()
    api_secret = (payload.get("api_secret") or "").strip()
    if not api_key or not api_secret:
        return JSONResponse({"error": "api_key and api_secret are required"}, status_code=400)

    enc_key = settings.encryption_key
    if not enc_key:
        return JSONResponse({"error": "server encryption key not configured"}, status_code=500)

    try:
        encrypted_secret = encrypt_secret(api_secret, enc_key)
        repo.save_api_credentials(user_id, api_key, encrypted_secret)
        return JSONResponse({"ok": True, "api_key_preview": api_key[:4] + "***", "user_id": user_id})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/settings/keys/status")
def api_keys_status(user_id: str | None = None):
    """Return whether API credentials are configured for a specific user (NEVER expose the full secret)."""
    uid = user_id or "default_user"
    creds = repo.get_api_credentials(uid)
    if creds is None:
        return JSONResponse({"is_configured": False, "api_key_preview": None, "user_id": uid})
    raw_key = creds.get("api_key", "")
    preview = (raw_key[:4] + "***") if len(raw_key) > 4 else "***"
    return JSONResponse({
        "is_configured": True,
        "api_key_preview": preview,
        "user_id": uid,
    })


@app.get("/api/settings/keys/users")
def list_api_users():
    """List all users with configured API credentials (NEVER expose secrets)."""
    all_creds = repo.get_all_api_credentials()
    users = []
    for cred in all_creds:
        raw_key = cred.get("api_key", "")
        preview = (raw_key[:4] + "***") if len(raw_key) > 4 else "***"
        users.append({
            "user_id": cred.get("user_id", ""),
            "api_key_preview": preview,
            "updated_at": cred.get("updated_at", ""),
        })
    return JSONResponse({"users": users, "count": len(users)})


@app.get("/exposure")
def exposure(symbol: str | None = None, limit: int = 100):
    symbol = symbol or settings.default_currency
    data = repo.get_exposure_history(symbol, limit)
    return JSONResponse({"symbol": symbol, "exposure": data})


@app.get("/api/logs")
def api_logs(limit: int = 20):
    """Get latest system events/logs from the events table."""
    logs = repo.latest_events(limit)
    return JSONResponse({"logs": logs})


@app.get("/api/strategy/settings")
def strategy_settings():
    """Get current strategy settings (mode, period, reserve_amount)."""
    settings_row = repo.get_strategy_settings()
    return JSONResponse(settings_row or {})


@app.post("/api/strategy/settings")
def set_strategy_settings(payload: dict = Body(...)):
    """Update strategy settings (mode, period, reserve_amount)."""
    mode = payload.get("mode", "high_speed")
    period = int(payload.get("period", 2))
    reserve_amount = float(payload.get("reserve_amount", 0.0))

    # Validate mode
    if mode not in ["high_speed", "high_yield"]:
        return JSONResponse({"error": "mode must be 'high_speed' or 'high_yield'"}, status_code=400)

    # Validate period (2-120 days)
    if period < 2 or period > 120:
        return JSONResponse({"error": "period must be between 2 and 120 days"}, status_code=400)

    # Validate reserve_amount (must be non-negative)
    if reserve_amount < 0:
        return JSONResponse({"error": "reserve_amount must be non-negative"}, status_code=400)

    try:
        repo.set_strategy_settings(mode, period, reserve_amount)
        return JSONResponse({"ok": True, "mode": mode, "period": period, "reserve_amount": reserve_amount})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
