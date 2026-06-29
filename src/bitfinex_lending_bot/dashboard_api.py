from __future__ import annotations

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
    return JSONResponse({
        "symbol": symbol,
        "apy": apy,
        "pnl": pnl,
        "execution_success": execution_success,
        "execution_failure": execution_failure,
        "api_failures": api_failures,
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
