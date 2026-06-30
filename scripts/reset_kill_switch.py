"""一次性手動清除 kill switch 狀態的腳本。
使用方式: python scripts/reset_kill_switch.py "確認 Bitfinex API 已恢復,手動清除舊狀態"
"""
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bitfinex_lending_bot.config import load_settings
from bitfinex_lending_bot.storage import SQLiteRepository


def main():
    reason = sys.argv[1] if len(sys.argv) > 1 else "manual_reset_via_script"
    settings = load_settings()
    repo = SQLiteRepository(settings.database_path)
    repo.initialize()

    before = repo.get_kill_switch_state()
    before_fail = repo.get_failure_count()
    print(f"清除前狀態: {before}, 連續失敗次數: {before_fail}")

    repo.set_kill_switch_state(enabled=False, reason=reason, manual_override=True)
    repo.reset_failure_count()

    after = repo.get_kill_switch_state()
    after_fail = repo.get_failure_count()
    print(f"清除後狀態: {after}, 連續失敗次數: {after_fail}")
    print("已清除,請重新跑一次 bot 確認是否正常下單。")


if __name__ == "__main__":
    main()
