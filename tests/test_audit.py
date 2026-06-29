from __future__ import annotations

import sqlite3
from decimal import Decimal

from bitfinex_lending_bot.audit import SystemAuditRunner, generate_system_audit_report
from bitfinex_lending_bot.models import CreateFundingOfferRequest, FundingOffer, RiskMode, StrategyDecision
from bitfinex_lending_bot.risk import RiskConfig, RiskManager
from bitfinex_lending_bot.storage import SQLiteRepository
from bitfinex_lending_bot.validation import DecisionTrace


def test_system_audit_report_generator_runs() -> None:
    report = generate_system_audit_report()

    assert 0 <= report.risk_score <= 100
    assert report.safe_guarantees
    assert any("Risk gate" in finding.title for finding in report.findings)


def test_audit_detects_no_concurrency_double_offer_risk() -> None:
    report = generate_system_audit_report()

    assert not any("Concurrent instances can double-create funding offers" in item for item in report.critical_vulnerabilities)


def test_replay_consistency_audit_passes() -> None:
    findings = SystemAuditRunner(project_root=__import__("pathlib").Path.cwd()).audit_replay_determinism(repetitions=10)

    assert findings[0].severity == "INFO"
    assert findings[0].title == "Replay deterministic"


def test_state_corruption_detector_flags_offer_without_trace(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = SQLiteRepository(tmp_path / "audit.sqlite3")
    repository.initialize()
    repository.upsert_funding_offers(
        [
            FundingOffer(
                id=1,
                symbol="fUSD",
                mts_create=None,
                mts_update=None,
                amount=Decimal("50"),
                amount_orig=Decimal("50"),
                offer_type="PAPER_LIMIT",
                flags=0,
                status="PAPER_ACTIVE",
                rate=Decimal("0.0002"),
                period=2,
            )
        ]
    )

    inconsistencies = SystemAuditRunner(project_root=__import__("pathlib").Path.cwd())._find_state_inconsistencies(  # noqa: SLF001
        tmp_path / "audit.sqlite3"
    )

    assert "funding_offers exist without executed decision traces" in inconsistencies


def test_state_corruption_detector_flags_executed_trace_without_risk_allow(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = SQLiteRepository(tmp_path / "audit.sqlite3")
    repository.initialize()
    manager = RiskManager(
        RiskConfig(
            max_capital_exposure=Decimal("0.30"),
            max_daily_lending_amount=Decimal("500"),
            min_idle_cash_threshold=Decimal("100"),
            kill_switch_enabled=True,
            max_funding_rate=Decimal("0.01"),
            max_funding_rate_spread=Decimal("0.005"),
        )
    )
    risk = manager.safe_idle_decision("test")
    object.__setattr__(risk, "mode", RiskMode.KILL_SWITCH)
    trace = DecisionTrace(
        input_snapshot={"symbol": "fUSD"},
        strategy_decision=StrategyDecision(
            create_offers=(CreateFundingOfferRequest("fUSD", Decimal("50"), Decimal("0.0002"), 2),)
        ),
        risk_decision=risk,
        outcome="EXECUTED",
    )
    try:
        repository.add_decision_trace(trace)
    except Exception:
        with sqlite3.connect(tmp_path / "audit.sqlite3") as connection:
            connection.execute(
                """
                INSERT INTO decision_traces (
                    created_at, input_snapshot, strategy_reason, create_offer_count, cancel_offer_count,
                    risk_allowed, risk_mode, risk_rule, risk_reason, outcome
                )
                VALUES ('now', '{}', 'test', 1, 0, 0, 'KILL_SWITCH', 'KILL_SWITCH', 'test', 'EXECUTED')
                """
            )

    inconsistencies = SystemAuditRunner(project_root=__import__("pathlib").Path.cwd())._find_state_inconsistencies(  # noqa: SLF001
        tmp_path / "audit.sqlite3"
    )

    assert "1 executed traces without allowed risk decision" in inconsistencies


def test_kill_switch_integrity_audit_passes() -> None:
    findings = SystemAuditRunner(project_root=__import__("pathlib").Path.cwd()).audit_kill_switch_integrity()

    assert findings[0].severity == "INFO"
    assert findings[0].title == "Kill switch integrity passed"
