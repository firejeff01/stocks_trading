"""DailySummaryBuilder — 收盤後 daily summary email．

主旨：[SIM]/[LIVE] + 日期 + 摘要
HTML body：equity / cash / today's PnL / holdings table / signals table
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.notify.daily_summary import (
    DailySummaryBuilder,
    HoldingSummary,
)


def _spy_holding() -> HoldingSummary:
    return HoldingSummary(
        symbol="SPY",
        market="US",
        qty=5,
        avg_price=Money("487.20", Currency.USD),
        current_price=Money("492.55", Currency.USD),
    )


def _qqq_signal() -> Signal:
    return Signal(
        account_id=uuid4(),
        strategy_name="DualMomentum",
        symbol=Symbol("QQQ", Market.US),
        side=Side.BUY,
        target_price=Money("400", Currency.USD),
        stop_loss=Money("380", Currency.USD),
        generated_at=datetime(2026, 5, 23, 14, 30, tzinfo=UTC),
    )


class TestSubject:
    def test_sim_mode_subject_prefix(self) -> None:
        builder = DailySummaryBuilder()
        msg = builder.build(
            mode=Mode.SIM,
            summary_date=date(2026, 5, 23),
            equity=Money(10000, Currency.USD),
            cash=Money(8000, Currency.USD),
            todays_pnl=Money(0, Currency.USD),
            holdings=[],
            todays_signals=[],
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert msg.subject.startswith("[SIM]")
        assert "2026-05-23" in msg.subject

    def test_live_mode_subject_prefix(self) -> None:
        builder = DailySummaryBuilder()
        msg = builder.build(
            mode=Mode.LIVE,
            summary_date=date(2026, 5, 23),
            equity=Money(10000, Currency.USD),
            cash=Money(8000, Currency.USD),
            todays_pnl=Money(0, Currency.USD),
            holdings=[],
            todays_signals=[],
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert msg.subject.startswith("[LIVE]")


class TestBody:
    def test_html_body_contains_equity(self) -> None:
        builder = DailySummaryBuilder()
        msg = builder.build(
            mode=Mode.SIM,
            summary_date=date(2026, 5, 23),
            equity=Money("103247.00", Currency.USD),
            cash=Money(8000, Currency.USD),
            todays_pnl=Money("842.50", Currency.USD),
            holdings=[],
            todays_signals=[],
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert "103247" in msg.html_body
        assert "842" in msg.html_body  # today's PnL

    def test_html_body_lists_holdings(self) -> None:
        builder = DailySummaryBuilder()
        msg = builder.build(
            mode=Mode.SIM,
            summary_date=date(2026, 5, 23),
            equity=Money(10000, Currency.USD),
            cash=Money(8000, Currency.USD),
            todays_pnl=Money(0, Currency.USD),
            holdings=[_spy_holding()],
            todays_signals=[],
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert "SPY" in msg.html_body

    def test_html_body_lists_signals(self) -> None:
        builder = DailySummaryBuilder()
        msg = builder.build(
            mode=Mode.SIM,
            summary_date=date(2026, 5, 23),
            equity=Money(10000, Currency.USD),
            cash=Money(8000, Currency.USD),
            todays_pnl=Money(0, Currency.USD),
            holdings=[],
            todays_signals=[_qqq_signal()],
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert "QQQ" in msg.html_body
        assert "DualMomentum" in msg.html_body

    def test_empty_holdings_shows_placeholder(self) -> None:
        builder = DailySummaryBuilder()
        msg = builder.build(
            mode=Mode.SIM,
            summary_date=date(2026, 5, 23),
            equity=Money(10000, Currency.USD),
            cash=Money(10000, Currency.USD),
            todays_pnl=Money(0, Currency.USD),
            holdings=[],
            todays_signals=[],
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        # 仍應產生合法 HTML
        assert "<html" in msg.html_body.lower() or "<table" in msg.html_body.lower()


class TestDisclaimer:
    def test_includes_not_advice_disclaimer(self) -> None:
        builder = DailySummaryBuilder()
        msg = builder.build(
            mode=Mode.SIM,
            summary_date=date(2026, 5, 23),
            equity=Money(10000, Currency.USD),
            cash=Money(10000, Currency.USD),
            todays_pnl=Money(0, Currency.USD),
            holdings=[],
            todays_signals=[],
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert "不構成投資建議" in msg.html_body
