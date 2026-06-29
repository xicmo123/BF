from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body

from .config import load_settings
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
    metrics = repo.get_metrics("execution_success", limit)
    return JSONResponse({"symbol": symbol, "apy": apy, "pnl": pnl, "metrics": metrics})


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


@app.post("/rollout/auto/enable")
def rollout_auto_enable(payload: dict = Body({})):
    ops = None
    try:
        from .ops import OpsManager

        ops = OpsManager(repo, notifier, settings)
        ops.start_auto_rollout(interval_seconds=int(payload.get("interval", 60)), cycles_stable=int(payload.get("cycles", 5)))
        repo.set_rollout_settings(True, "AUTO_ENABLED", "manual enable")
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"ok": True})


@app.post("/rollout/auto/disable")
def rollout_auto_disable():
    try:
        from .ops import OpsManager

        ops = OpsManager(repo, notifier, settings)
        ops.stop_auto_rollout()
        repo.set_rollout_settings(False, "AUTO_DISABLED", "manual disable")
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"ok": True})


@app.post("/rollout/auto/run")
def rollout_auto_run():
    try:
        from .ops import OpsManager

        ops = OpsManager(repo, notifier, settings)
        res = ops.run_auto_rollout()
        return JSONResponse({"ok": True, "result": res})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)



@app.get("/exposure")
def exposure(symbol: str | None = None, limit: int = 100):
    symbol = symbol or settings.default_currency
    data = repo.get_exposure_history(symbol, limit)
    return JSONResponse({"symbol": symbol, "exposure": data})
