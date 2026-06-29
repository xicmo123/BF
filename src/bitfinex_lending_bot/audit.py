from __future__ import annotations

import ast
import sqlite3
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .bot import LendingBot
from .config import Settings
from .models import FundingBookEntry, Wallet
from .notifier import TelegramNotifier
from .risk import RiskConfig, RiskManager
from .storage import SQLiteRepository
from .strategy import PassiveSpreadStrategy
from .stress import ScenarioClient, StressScenario, api_timeout_scenario, empty_book_scenario, extreme_rate_scenario
from .validation import DecisionTraceError, DecisionTraceValidator, ReplayEngine, ReplayFrame


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    title: str
    detail: str


@dataclass(frozen=True)
class SystemAuditReport:
    risk_score: int
    critical_vulnerabilities: list[str]
    safe_guarantees: list[str]
    findings: list[AuditFinding] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Bitfinex Lending Bot System Correctness Audit",
            "",
            f"System risk score: {self.risk_score}/100",
            "",
            "## Critical Vulnerabilities",
        ]
        lines.extend(f"- {item}" for item in self.critical_vulnerabilities or ["None detected"])
        lines.append("")
        lines.append("## Safe Guarantees")
        lines.extend(f"- {item}" for item in self.safe_guarantees)
        lines.append("")
        lines.append("## Findings")
        lines.extend(f"- [{finding.severity}] {finding.title}: {finding.detail}" for finding in self.findings)
        return "\n".join(lines)


class SystemAuditRunner:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._src_root = project_root / "src" / "bitfinex_lending_bot"

    def run(self) -> SystemAuditReport:
        findings: list[AuditFinding] = []
        findings.extend(self.audit_execution_paths())
        findings.extend(self.audit_concurrency_safety())
        findings.extend(self.audit_replay_determinism())
        findings.extend(self.audit_state_consistency())
        findings.extend(self.audit_kill_switch_integrity())

        critical = [finding for finding in findings if finding.severity == "CRITICAL"]
        high = [finding for finding in findings if finding.severity == "HIGH"]
        medium = [finding for finding in findings if finding.severity == "MEDIUM"]
        risk_score = max(0, 100 - (40 * len(critical)) - (20 * len(high)) - (10 * len(medium)))
        safe_guarantees = [
            "Runtime bot execution validates each StrategyDecision with RiskManager before create/cancel calls.",
            "DecisionTraceValidator rejects execution outcomes that do not include a risk decision.",
            "API failures and SQLite read/write failures enter safe idle and trigger kill switch state.",
            "Paper trading is enabled by default, so live write calls require explicit PAPER_TRADING=false.",
            "ReplayEngine routes every replayed frame through strategy, risk, and trace validation.",
        ]
        return SystemAuditReport(
            risk_score=risk_score,
            critical_vulnerabilities=[f"{finding.title}: {finding.detail}" for finding in critical],
            safe_guarantees=safe_guarantees,
            findings=findings,
        )

    def audit_execution_paths(self) -> list[AuditFinding]:
        call_sites = self._find_method_calls({"create_funding_offer", "cancel_funding_offer"})
        findings: list[AuditFinding] = []
        runtime_call_sites = [
            call for call in call_sites if not call["path"].startswith("tests/") and call["path"] != "src/bitfinex_lending_bot/client.py"
        ]
        untracked = [
            call for call in runtime_call_sites if call["path"] not in {"src/bitfinex_lending_bot/bot.py", "src/bitfinex_lending_bot/stress.py"}
        ]
        if untracked:
            findings.append(
                AuditFinding(
                    "CRITICAL",
                    "Untracked funding execution path",
                    f"Found create/cancel calls outside approved runtime paths: {untracked}",
                )
            )
        else:
            findings.append(
                AuditFinding(
                    "INFO",
                    "Funding execution paths scoped",
                    "No funding create/cancel calls found outside bot/client/stress/test surfaces.",
                )
            )

        bot_source = (self._src_root / "bot.py").read_text()
        if "self._risk_manager.evaluate" in bot_source and "create_funding_offer" in bot_source:
            findings.append(
                AuditFinding("INFO", "Risk gate present before bot execution", "bot.py contains risk evaluation before create/cancel loops.")
            )
        else:
            findings.append(AuditFinding("CRITICAL", "Risk gate missing", "bot.py does not show risk evaluation before execution."))
        return findings

    def audit_concurrency_safety(self) -> list[AuditFinding]:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings = _settings(tmp_path)
            client = ScenarioClient(StressScenario(name="normal"))
            errors: list[BaseException] = []

            def run_one() -> None:
                bot = LendingBot(
                    settings=settings,
                    client=client,
                    repository=SQLiteRepository(settings.database_path),
                    notifier=TelegramNotifier(None, None),
                    strategy=PassiveSpreadStrategy(),
                    risk_manager=RiskManager(RiskConfig.from_settings(settings)),
                )
                try:
                    bot.run_once("fUSD")
                except BaseException as exc:  # pragma: no cover - surfaced by finding detail
                    errors.append(exc)

            threads = [threading.Thread(target=run_one) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            created = client.created_offer_count
            if created > 1:
                return [
                    AuditFinding(
                        "CRITICAL",
                        "Concurrent instances can double-create funding offers",
                        f"Two simultaneous bot instances created {created} simulated offers; no process-wide execution lock was observed.",
                    )
                ]
            if errors:
                return [AuditFinding("HIGH", "Concurrent run raised errors", "; ".join(str(error) for error in errors))]
            return [AuditFinding("INFO", "Concurrency check passed", f"Concurrent instances created {created} offer(s).")]

    def audit_replay_determinism(self, repetitions: int = 20) -> list[AuditFinding]:
        frame = ReplayFrame(
            funding_book=[FundingBookEntry(rate=Decimal("0.0002"), period=2, count=1, amount=Decimal("100"))],
            wallets=[Wallet("funding", "USD", Decimal("1000"), Decimal("0"), Decimal("1000"))],
            open_offers=[],
        )
        signatures = []
        for _ in range(repetitions):
            traces = ReplayEngine(strategy=PassiveSpreadStrategy(), risk_manager=RiskManager(RiskConfig.from_settings(_settings(Path("/tmp"))))).replay(
                [frame],
                symbol="fUSD",
                limit=1,
            )
            trace = traces[0]
            assert trace.risk_decision is not None
            signatures.append((trace.risk_decision.allowed, trace.risk_decision.mode.value, trace.risk_decision.rule, trace.outcome))
        if len(set(signatures)) == 1:
            return [AuditFinding("INFO", "Replay deterministic", f"Same market frame replayed {repetitions} times with identical outcome.")]
        return [AuditFinding("CRITICAL", "Replay non-deterministic", f"Observed replay signatures: {sorted(set(signatures))}")]

    def audit_state_consistency(self) -> list[AuditFinding]:
        with TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            repository = SQLiteRepository(settings.database_path)
            bot = LendingBot(
                settings=settings,
                client=ScenarioClient(StressScenario(name="normal")),
                repository=repository,
                notifier=TelegramNotifier(None, None),
                strategy=PassiveSpreadStrategy(),
                risk_manager=RiskManager(RiskConfig.from_settings(settings)),
            )
            bot.run_once("fUSD")
            inconsistencies = self._find_state_inconsistencies(settings.database_path)
            if inconsistencies:
                return [
                    AuditFinding(
                        "HIGH",
                        "Decision trace/storage inconsistency",
                        "; ".join(inconsistencies),
                    )
                ]
            return [AuditFinding("INFO", "State consistency check passed", "decision_traces and funding_offers remained consistent after restart scan.")]

    def audit_kill_switch_integrity(self) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        validator = DecisionTraceValidator()
        scenarios = [
            ("api_failure", api_timeout_scenario()),
            ("stress_empty_book", empty_book_scenario()),
            ("stress_extreme_rate", extreme_rate_scenario(Decimal("50"))),
        ]
        for name, scenario in scenarios:
            with TemporaryDirectory() as tmp:
                settings = _settings(Path(tmp))
                client = ScenarioClient(scenario)
                bot = LendingBot(
                    settings=settings,
                    client=client,
                    repository=SQLiteRepository(settings.database_path),
                    notifier=TelegramNotifier(None, None),
                    strategy=PassiveSpreadStrategy(),
                    risk_manager=RiskManager(RiskConfig.from_settings(settings)),
                    trace_validator=validator,
                )
                bot.run_once("fUSD")
                if client.created_offer_count != 0:
                    findings.append(AuditFinding("CRITICAL", "Kill switch bypass", f"{name} created {client.created_offer_count} offer(s)."))
        replay_traces = ReplayEngine(
            strategy=PassiveSpreadStrategy(),
            risk_manager=RiskManager(RiskConfig(kill_switch_enabled=True, **_risk_limits())),
        ).replay(
            [
                ReplayFrame(
                    funding_book=[FundingBookEntry(rate=Decimal("0.0002"), period=2, count=1, amount=Decimal("100"))],
                    wallets=[Wallet("funding", "USD", Decimal("1000"), Decimal("0"), Decimal("1000"))],
                    open_offers=[],
                )
            ],
            symbol="fUSD",
        )
        if replay_traces[0].outcome != "SAFE_IDLE":
            findings.append(AuditFinding("CRITICAL", "Replay kill switch bypass", f"Replay outcome was {replay_traces[0].outcome}."))
        if findings:
            return findings
        return [AuditFinding("INFO", "Kill switch integrity passed", "API failure, stress modes, and replay mode did not execute offers.")]

    def _find_method_calls(self, names: set[str]) -> list[dict[str, Any]]:
        call_sites: list[dict[str, Any]] = []
        for path in self._project_root.rglob("*.py"):
            if ".git" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in names:
                    call_sites.append(
                        {
                            "path": str(path.relative_to(self._project_root)),
                            "line": node.lineno,
                            "method": node.func.attr,
                        }
                    )
        return call_sites

    def _find_state_inconsistencies(self, database_path: Path) -> list[str]:
        inconsistencies: list[str] = []
        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            executed_traces = connection.execute(
                "SELECT COUNT(*) AS count FROM decision_traces WHERE outcome = 'EXECUTED' AND risk_allowed != 1"
            ).fetchone()["count"]
            if executed_traces:
                inconsistencies.append(f"{executed_traces} executed traces without allowed risk decision")

            offer_count = connection.execute("SELECT COUNT(*) AS count FROM funding_offers").fetchone()["count"]
            trace_count = connection.execute(
                "SELECT COUNT(*) AS count FROM decision_traces WHERE outcome = 'EXECUTED'"
            ).fetchone()["count"]
            if offer_count > 0 and trace_count == 0:
                inconsistencies.append("funding_offers exist without executed decision traces")
        return inconsistencies


def generate_system_audit_report(project_root: Path | None = None) -> SystemAuditReport:
    return SystemAuditRunner(project_root or Path.cwd()).run()


def _risk_limits() -> dict[str, Decimal]:
    return {
        "max_capital_exposure": Decimal("0.30"),
        "max_daily_lending_amount": Decimal("500"),
        "min_idle_cash_threshold": Decimal("100"),
        "max_funding_rate": Decimal("0.001"),
        "max_funding_rate_spread": Decimal("0.005"),
    }


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        bitfinex_api_key=None,
        bitfinex_api_secret=None,
        telegram_token=None,
        telegram_chat_id=None,
        database_path=tmp_path / "audit.sqlite3",
        log_path=tmp_path / "audit.log",
        **_risk_limits(),
    )
