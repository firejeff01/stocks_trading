"""FeeCalculator — 純函數測試．

幣別與市場：
- TW: commission 0.0855% (永豐網路下單 6 折) + 賣方證交稅 0.3%
- US: commission max(0.5%, USD 35) + 無稅
- 滑價 0.05%，BUY 向上、SELL 向下
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side
from stocks_trading.paper_trading.fee_calculator import (
    FeeConfig,
    apply_slippage,
    calculate_commission,
    calculate_sell_tax,
)


@pytest.fixture
def default_config() -> FeeConfig:
    return FeeConfig()  # 預設值與規格一致


class TestSlippage:
    def test_buy_slips_upward(self, default_config: FeeConfig) -> None:
        # open=100，slippage 0.05% → BUY fill = 100.05
        fill = apply_slippage(
            open_price=Decimal("100"),
            side=Side.BUY,
            slippage_rate=default_config.slippage_rate,
        )
        assert fill == Decimal("100.0500")

    def test_sell_slips_downward(self, default_config: FeeConfig) -> None:
        # open=100，slippage 0.05% → SELL fill = 99.95
        fill = apply_slippage(
            open_price=Decimal("100"),
            side=Side.SELL,
            slippage_rate=default_config.slippage_rate,
        )
        assert fill == Decimal("99.9500")

    def test_zero_slippage_returns_open(self) -> None:
        cfg = FeeConfig(slippage_rate=Decimal("0"))
        assert (
            apply_slippage(
                open_price=Decimal("100"),
                side=Side.BUY,
                slippage_rate=cfg.slippage_rate,
            )
            == Decimal("100")
        )


class TestTwCommission:
    def test_commission_pct(self, default_config: FeeConfig) -> None:
        # 100 元 × 1000 股 = 100,000 元；commission 0.0855% = 85.5
        commission = calculate_commission(
            market=Market.TW,
            notional=Decimal("100000"),
            config=default_config,
        )
        assert commission == Decimal("85.500000")

    def test_no_minimum_for_tw(self, default_config: FeeConfig) -> None:
        # 小金額不該被 TW 強制 minimum (TW 預設 min=0)
        commission = calculate_commission(
            market=Market.TW,
            notional=Decimal("1000"),
            config=default_config,
        )
        assert commission == Decimal("0.855000")


class TestUsCommission:
    def test_below_minimum_uses_min(self, default_config: FeeConfig) -> None:
        # 1000 元 × 0.5% = 5，但 min USD 35 → 收 35
        commission = calculate_commission(
            market=Market.US,
            notional=Decimal("1000"),
            config=default_config,
        )
        assert commission == Decimal("35")

    def test_above_minimum_uses_rate(self, default_config: FeeConfig) -> None:
        # 100,000 × 0.5% = 500 > 35 → 收 500
        commission = calculate_commission(
            market=Market.US,
            notional=Decimal("100000"),
            config=default_config,
        )
        assert commission == Decimal("500.000")


class TestSellTax:
    def test_tw_sell_tax(self, default_config: FeeConfig) -> None:
        # TW 賣方收 0.3% 證交稅
        tax = calculate_sell_tax(
            market=Market.TW,
            notional=Decimal("100000"),
            config=default_config,
        )
        assert tax == Decimal("300.000")

    def test_us_no_sell_tax(self, default_config: FeeConfig) -> None:
        tax = calculate_sell_tax(
            market=Market.US,
            notional=Decimal("100000"),
            config=default_config,
        )
        assert tax == Decimal("0")
