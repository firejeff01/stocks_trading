"""PortfolioState — 單帳本 in-memory 持倉與現金追蹤．

供 SimulatedBroker 與 BacktestEngine 共用．單一 base currency．

操作：
- apply_buy(symbol, qty, price, commission) → 扣現金、加倉位
- apply_sell(symbol, qty, price, commission) → 加現金、減倉位、記錄 closed trade
- mark_to_market(prices) → equity = cash + Σ qty × current_price
"""

from decimal import Decimal

import pytest

from stocks_trading.backtest.portfolio_state import (
    InsufficientPositionError,
    PortfolioState,
)
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.money import Money
from stocks_trading.domain.symbol import Symbol


def _spy() -> Symbol:
    return Symbol("SPY", Market.US)


def _qqq() -> Symbol:
    return Symbol("QQQ", Market.US)


def _usd(amount: str | int) -> Money:
    return Money(Decimal(str(amount)), Currency.USD)


class TestEmptyPortfolio:
    def test_initial_cash_matches_capital(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        assert pf.cash == _usd(10000)

    def test_no_positions(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        assert pf.positions == {}

    def test_equity_equals_cash_when_no_positions(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        assert pf.mark_to_market(prices={}) == _usd(10000)

    def test_realized_pnl_zero(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        assert pf.realized_pnl == _usd(0)


class TestApplyBuy:
    def test_buy_deducts_cash_including_commission(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd("1.50"))
        # cash = 10000 - 10 × 100 - 1.5 = 8998.5
        assert pf.cash == _usd("8998.5")

    def test_buy_adds_position(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        pos = pf.positions[_spy()]
        assert pos.qty == 10
        assert pos.avg_price == _usd(100)

    def test_buy_adds_to_existing_position_with_avg_price(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        pf.apply_buy(_spy(), qty=10, price=_usd(120), commission=_usd(0))
        pos = pf.positions[_spy()]
        assert pos.qty == 20
        # avg = (10×100 + 10×120) / 20 = 110
        assert pos.avg_price == _usd(110)

    def test_buy_more_than_cash_allows_raises(self) -> None:
        pf = PortfolioState(initial_cash=_usd(100))
        with pytest.raises(ValueError, match="現金"):
            pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))


class TestApplySell:
    def test_full_sell_closes_position_and_returns_cash(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        # 之後 SPY 漲到 120 賣出
        pf.apply_sell(_spy(), qty=10, price=_usd(120), commission=_usd("1.20"))
        # cash = 9000 + 10 × 120 - 1.20 = 10198.8
        assert pf.cash == _usd("10198.8")
        assert _spy() not in pf.positions

    def test_partial_sell_reduces_qty_keeps_avg(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        pf.apply_sell(_spy(), qty=4, price=_usd(120), commission=_usd(0))
        pos = pf.positions[_spy()]
        assert pos.qty == 6
        assert pos.avg_price == _usd(100)  # 部分賣出不變動均價

    def test_sell_more_than_held_raises(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=5, price=_usd(100), commission=_usd(0))
        with pytest.raises(InsufficientPositionError):
            pf.apply_sell(_spy(), qty=10, price=_usd(120), commission=_usd(0))

    def test_sell_symbol_not_held_raises(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        with pytest.raises(InsufficientPositionError):
            pf.apply_sell(_spy(), qty=1, price=_usd(100), commission=_usd(0))


class TestRealizedPnl:
    def test_winning_trade_recorded(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        pf.apply_sell(_spy(), qty=10, price=_usd(120), commission=_usd(0))
        # pnl = 10 × (120 - 100) = 200
        assert pf.realized_pnl == _usd(200)

    def test_losing_trade_recorded(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        pf.apply_sell(_spy(), qty=10, price=_usd(80), commission=_usd(0))
        assert pf.realized_pnl == _usd(-200)

    def test_commission_subtracted_from_pnl(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd("1.50"))
        pf.apply_sell(_spy(), qty=10, price=_usd(120), commission=_usd("1.50"))
        # gross = 200, commissions = 3 → net = 197
        assert pf.realized_pnl == _usd(197)


class TestWinRate:
    def test_win_rate_counts_only_closed_trades(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        # 3 trades: 2 wins (SPY, QQQ), 1 loss (SPY again)
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        pf.apply_sell(_spy(), qty=10, price=_usd(120), commission=_usd(0))  # win
        pf.apply_buy(_qqq(), qty=5, price=_usd(200), commission=_usd(0))
        pf.apply_sell(_qqq(), qty=5, price=_usd(210), commission=_usd(0))  # win
        pf.apply_buy(_spy(), qty=10, price=_usd(110), commission=_usd(0))
        pf.apply_sell(_spy(), qty=10, price=_usd(100), commission=_usd(0))  # loss
        assert pf.closed_trade_count == 3
        assert pf.win_rate == Decimal("2") / Decimal("3")


class TestMarkToMarket:
    def test_equity_includes_unrealized(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        # 現價 SPY = 120 → unrealized = 10 × 120 = 1200
        equity = pf.mark_to_market(prices={_spy(): _usd(120)})
        # cash = 9000, position market value = 1200, equity = 10200
        assert equity == _usd(10200)

    def test_mark_to_market_missing_price_raises(self) -> None:
        pf = PortfolioState(initial_cash=_usd(10000))
        pf.apply_buy(_spy(), qty=10, price=_usd(100), commission=_usd(0))
        with pytest.raises(KeyError, match="SPY"):
            pf.mark_to_market(prices={})
