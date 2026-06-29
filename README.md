# Bitfinex Lending Bot

模組化 Python Bitfinex funding lending bot。第一版包含：

- Bitfinex REST API client：funding book、wallets、funding offers 查詢，以及 offer 建立/取消。
- SQLite 儲存：funding book snapshot、wallet snapshot、funding offer、event log。
- Loguru 日誌與 Telegram 通知。
- 可擴充策略介面，內建 `PassiveSpreadStrategy` 範例。
- Streamlit dashboard。
- pytest 單元測試入口，API client 支援 fake transport 注入。

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Create `.env`:

```bash
BFX_API_KEY=...
BFX_API_SECRET=...
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
DATABASE_PATH=data/lending_bot.sqlite3
LOG_PATH=logs/bot.log
DEFAULT_CURRENCY=fUSD
PAPER_TRADING=true
MAX_CAPITAL_EXPOSURE=0.30
MAX_DAILY_LENDING_AMOUNT=500
MIN_IDLE_CASH_THRESHOLD=100
KILL_SWITCH=false
```

## Run

執行一次 bot：

```bash
PYTHONPATH=src python app.py
```

啟動 dashboard：

```bash
PYTHONPATH=src streamlit run dashboard.py
```

測試：

```bash
pytest
```

## Architecture

主要程式碼位於 `src/bitfinex_lending_bot/`：

- `client.py`：Bitfinex API client 與錯誤封裝。
- `models.py`：typed domain models。
- `storage.py`：SQLite repository。
- `strategy.py`：策略抽象類別與範例策略。
- `bot.py`：查詢、儲存、策略決策、下單/取消與通知流程。
- `dashboard.py`：Streamlit dashboard。

新增策略時繼承 `LendingStrategy`，實作 `evaluate()` 回傳 `StrategyDecision`，再於 `select_strategy()` 註冊即可。
