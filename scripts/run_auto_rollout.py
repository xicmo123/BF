#!/usr/bin/env python3
"""
Stateless CLI entrypoint for auto-rollout evaluation.

Usage:
    python scripts/run_auto_rollout.py [--config-path <path>] [--cycles-stable <N>]

This script:
1. Loads configuration from config.py
2. Initializes OpsManager with repository and notifier
3. Calls run_auto_rollout() with specified parameters
4. Outputs result as JSON
5. Exits with code 0 on success, non-zero on error

Design: No background threads, no persistent state. Completely stateless.
Ideal for triggering via Cronjob or external scheduler.
"""

import sys
import json
import argparse
from pathlib import Path

# Add src to path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bitfinex_lending_bot.config import load_settings
from bitfinex_lending_bot.storage import SQLiteRepository
from bitfinex_lending_bot.notifier import TelegramNotifier
from bitfinex_lending_bot.ops import OpsManager


def main():
    parser = argparse.ArgumentParser(
        description="Stateless auto-rollout evaluation for external scheduler"
    )
    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Optional path to config file (default: uses env vars and defaults)",
    )
    parser.add_argument(
        "--cycles-stable",
        type=int,
        default=5,
        help="Number of stable cycles required for upgrade (default: 5)",
    )
    parser.add_argument(
        "--check-enabled",
        action="store_true",
        help="If set, skip execution if auto_enabled flag is False",
    )

    args = parser.parse_args()

    try:
        # Load settings
        settings = load_settings()

        # Initialize repository and notifier
        repo = SQLiteRepository(settings.database_path)
        repo.initialize()
        notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id)

        # Check auto_enabled flag if requested
        if args.check_enabled:
            settings_row = repo.get_rollout_settings()
            auto_enabled = (
                settings_row and int(settings_row.get("auto_enabled", "0") or 0) == 1
                if settings_row
                else False
            )
            if not auto_enabled:
                result = {
                    "status": "skipped",
                    "reason": "auto_enabled is False",
                }
                print(json.dumps(result, indent=2))
                sys.exit(0)

        # Create OpsManager and run auto-rollout
        ops = OpsManager(repo, notifier, settings)
        result = ops.run_auto_rollout(cycles_stable=args.cycles_stable)

        # Add status
        result["status"] = "completed"

        # Output result
        print(json.dumps(result, indent=2, default=str))

        # Exit with 0 on success
        sys.exit(0)

    except Exception as exc:
        # Output error
        error_result = {
            "status": "error",
            "error": str(exc),
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
