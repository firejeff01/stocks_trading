"""FillEngine 規格 — T+1 開盤成交 + 跳空保護 (FR-EX-03/06)．

設計：
- 純函式 try_fill_at_next_open(signal, next_open, qty, settings)
- 回測 (BacktestEngine) 與 SimulatedBroker 共用同一份函式 → 杜絕回測與 paper 偏離
- 跳空門檻：|next_open - target| / target > threshold → UNFILLED_GAP
- 滑價：BUY 加價、SELL 減價
- 手續費以成交金額 × commission_pct 計算
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from stocks_trading.backtest.fill_engine import (
    DEFAULT_FILL_SETTINGS,
    FillResult,
    FillSettings,
    try_fill_at_next_open,
)
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol


def _buy_signal(target_price: str = "100", currency: Currency = Currency.USD) -> Signal:
    symbol = Symbol("SPY", Market.US) if currency is Currency.USD else Symbol("0050", Market.TW)
    return Signal(
        account_id=uuid4(),
        strategy_name="Test",
        symbol=symbol,
        side=Side.BUY,
        target_price=Money(target_price, currency),
        stop_loss=Money(Decimal(target_price) * Decimal("0.95"), currency),
        generated_at=datetime(2026, 5, 22, 21, 0, tzinfo=UTC),
    )


class TestNormalFill:
    def test_fill_when_open_equals_target(self) -> None:
        sig = _buy_signal("100")
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("100"),
            qty=10,
            settings=FillSettings(
                gap_threshold_pct=Decimal("0.05"),
                slippage_pct=Decimal("0"),
                commission_pct=Decimal("0"),
            ),
        )
        assert result.status is SignalStatus.FILLED
        assert result.fill_price == Money("100", Currency.USD)
        assert result.qty == 10
        assert result.commission == Money("0", Currency.USD)

    def test_fill_within_threshold(self) -> None:
        sig = _buy_signal("100")
        # 跳空 +3%（< 5% 閾值）→ 應成交
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("103"),
            qty=5,
            settings=FillSettings(
                gap_threshold_pct=Decimal("0.05"),
                slippage_pct=Decimal("0"),
                commission_pct=Decimal("0"),
            ),
        )
        assert result.status is SignalStatus.FILLED
        assert result.fill_price == Money("103", Currency.USD)


class TestGapProtection:
    def test_up_gap_over_threshold_rejected(self) -> None:
        sig = _buy_signal("100")
        # 跳空 +6% > 5% 閾值
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("106"),
            qty=10,
            settings=DEFAULT_FILL_SETTINGS,
        )
        assert result.status is SignalStatus.UNFILLED_GAP
        assert result.fill_price is None

    def test_down_gap_over_threshold_rejected(self) -> None:
        sig = _buy_signal("100")
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("93"),  # -7%
            qty=10,
            settings=DEFAULT_FILL_SETTINGS,
        )
        assert result.status is SignalStatus.UNFILLED_GAP

    def test_exactly_at_threshold_filled(self) -> None:
        # 跳空 = 閾值 → 仍應成交 (邊界 inclusive)
        sig = _buy_signal("100")
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("105"),  # +5% 正好
            qty=10,
            settings=FillSettings(
                gap_threshold_pct=Decimal("0.05"),
                slippage_pct=Decimal("0"),
                commission_pct=Decimal("0"),
            ),
        )
        assert result.status is SignalStatus.FILLED


class TestSlippage:
    def test_buy_pays_extra_slippage(self) -> None:
        sig = _buy_signal("100")
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("100"),
            qty=10,
            settings=FillSettings(
                gap_threshold_pct=Decimal("0.05"),
                slippage_pct=Decimal("0.001"),  # 0.1%
                commission_pct=Decimal("0"),
            ),
        )
        # BUY 滑價：實際成交價 = 100 × (1 + 0.001) = 100.1
        assert result.fill_price == Money("100.100", Currency.USD)


class TestCommission:
    def test_commission_on_fill_amount(self) -> None:
        sig = _buy_signal("100", Currency.TWD)
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("100"),
            qty=1000,
            settings=FillSettings(
                gap_threshold_pct=Decimal("0.05"),
                slippage_pct=Decimal("0"),
                commission_pct=Decimal("0.001425"),  # 台股
            ),
        )
        # 100 × 1000 × 0.001425 = 142.5
        assert result.commission == Money("142.500", Currency.TWD)

    def test_unfilled_gap_has_no_commission(self) -> None:
        sig = _buy_signal("100")
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("110"),  # +10%
            qty=10,
            settings=DEFAULT_FILL_SETTINGS,
        )
        assert result.status is SignalStatus.UNFILLED_GAP
        assert result.commission is None


class TestDefaultSettings:
    def test_defaults_match_taiwan_market_conservative(self) -> None:
        # 預設應接近台股實況：5% 跳空門檻、0.05% 滑價、0.1425% 手續費
        assert DEFAULT_FILL_SETTINGS.gap_threshold_pct == Decimal("0.05")
        assert DEFAULT_FILL_SETTINGS.slippage_pct == Decimal("0.0005")
        assert DEFAULT_FILL_SETTINGS.commission_pct == Decimal("0.001425")


class TestFillResultImmutability:
    def test_frozen_dataclass(self) -> None:
        sig = _buy_signal("100")
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("100"),
            qty=10,
            settings=DEFAULT_FILL_SETTINGS,
        )
        import pytest

        with pytest.raises((AttributeError, TypeError)):
            result.status = SignalStatus.UNFILLED_GAP  # type: ignore[misc]
        # also check FillResult is immutable
        _ = FillResult  # explicit reference


class TestSellSide:
    def test_sell_slippage_reduces_price(self) -> None:
        # Dual Momentum 不放空但 base 引擎要支援 SELL (平倉用)
        sig = Signal(
            account_id=uuid4(),
            strategy_name="Test",
            symbol=Symbol("SPY", Market.US),
            side=Side.SELL,
            target_price=Money("100", Currency.USD),
            stop_loss=Money("105", Currency.USD),  # SELL 停損需高於進場
        )
        result = try_fill_at_next_open(
            signal=sig,
            next_open=Decimal("100"),
            qty=10,
            settings=FillSettings(
                gap_threshold_pct=Decimal("0.05"),
                slippage_pct=Decimal("0.001"),
                commission_pct=Decimal("0"),
            ),
        )
        # SELL 滑價：實際成交價 = 100 × (1 - 0.001) = 99.9
        assert result.fill_price == Money("99.900", Currency.USD)
