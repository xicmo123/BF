from __future__ import annotations

import schedule

from bitfinex_lending_bot.bot import build_bot


def schedule_tasks(interval_minutes: int = 5) -> None:
    bot = build_bot()
    schedule.every(interval_minutes).minutes.do(bot.run_once)
