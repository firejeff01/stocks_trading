"""PortfolioState — 單帳本 in-memory 持倉與現金追蹤．

被 SimulatedBroker (M2-S3) 與 BacktestEngine (M2-S4) 共用．
單一 base currency；所有操作以該 currency 為準．

不負責持久化 — 純記憶體狀態．SimulatedBroker 會在每次 mutation 後
另外調用 PositionRepository 持久化．
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stocks_trading.domain.money import Money
from stocks_trading.domain.symbol import Symbol


class InsufficientPositionError(Exception):
    """賣出時持倉不足．"""


@dataclass(frozen=True, slots=True)
class PositionEntry:
    qty: int
    avg_price: Money


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    symbol: Symbol
    qty: int
    entry_price: Money
    exit_price: Money
    commission: Money  # 進場 + 出場手續費合計

    @property
    def pnl(self) -> Money:
        gross = self.exit_price - self.entry_price
        return gross * self.qty - self.commission


class PortfolioState:
    def __init__(self, *, initial_cash: Money) -> None:
        self._cash = initial_cash
        self._currency = initial_cash.currency
        self._positions: dict[Symbol, PositionEntry] = {}
        self._closed_trades: list[ClosedTrade] = []
        # 未配對的進場手續費 (賣出時要含進 ClosedTrade.commission)
        self._entry_commissions: dict[Symbol, Money] = {}

    # ---- read-only views ----
    @property
    def cash(self) -> Money:
        return self._cash

    @property
    def positions(self) -> dict[Symbol, PositionEntry]:
        return dict(self._positions)  # 防外部修改

    @property
    def realized_pnl(self) -> Money:
        if not self._closed_trades:
            return Money(0, self._currency)
        total = Money(0, self._currency)
        for trade in self._closed_trades:
            total = total + trade.pnl
        return total

    @property
    def closed_trade_count(self) -> int:
        return len(self._closed_trades)

    @property
    def win_rate(self) -> Decimal:
        if not self._closed_trades:
            return Decimal("0")
        zero = Money(0, self._currency)
        wins = sum(1 for t in self._closed_trades if t.pnl > zero)
        return Decimal(wins) / Decimal(len(self._closed_trades))

    # ---- mutations ----
    def apply_buy(
        self, symbol: Symbol, *, qty: int, price: Money, commission: Money
    ) -> None:
        self._assert_currency(price, commission)
        cost = price * qty + commission
        if cost > self._cash:
            raise ValueError(
                f"現金不足：需 {cost}、僅有 {self._cash}"
            )
        self._cash = self._cash - cost

        existing = self._positions.get(symbol)
        if existing is None:
            self._positions[symbol] = PositionEntry(qty=qty, avg_price=price)
            self._entry_commissions[symbol] = commission
        else:
            new_qty = existing.qty + qty
            # 加權平均：(舊量×舊均價 + 新量×新價) / 新量
            old_value = existing.avg_price.amount * Decimal(existing.qty)
            new_value = price.amount * Decimal(qty)
            new_avg = (old_value + new_value) / Decimal(new_qty)
            self._positions[symbol] = PositionEntry(
                qty=new_qty, avg_price=Money(new_avg, self._currency)
            )
            self._entry_commissions[symbol] = (
                self._entry_commissions[symbol] + commission
            )

    def apply_sell(
        self, symbol: Symbol, *, qty: int, price: Money, commission: Money
    ) -> None:
        self._assert_currency(price, commission)
        existing = self._positions.get(symbol)
        if existing is None or existing.qty < qty:
            held = existing.qty if existing else 0
            raise InsufficientPositionError(
                f"持倉不足：欲賣 {qty}、僅有 {held} ({symbol})"
            )

        proceeds = price * qty - commission
        self._cash = self._cash + proceeds

        # 記錄 closed trade (若是部分賣出，按比例分攤 entry commission)
        entry_commission_total = self._entry_commissions[symbol]
        portion = Decimal(qty) / Decimal(existing.qty)
        attributed_entry_commission = Money(
            entry_commission_total.amount * portion, self._currency
        )
        trade = ClosedTrade(
            symbol=symbol,
            qty=qty,
            entry_price=existing.avg_price,
            exit_price=price,
            commission=attributed_entry_commission + commission,
        )
        self._closed_trades.append(trade)

        # 更新或移除持倉
        remaining = existing.qty - qty
        if remaining == 0:
            del self._positions[symbol]
            del self._entry_commissions[symbol]
        else:
            self._positions[symbol] = PositionEntry(
                qty=remaining, avg_price=existing.avg_price
            )
            self._entry_commissions[symbol] = (
                self._entry_commissions[symbol] - attributed_entry_commission
            )

    # ---- analytics ----
    def mark_to_market(self, *, prices: dict[Symbol, Money]) -> Money:
        equity = self._cash
        for symbol, pos in self._positions.items():
            if symbol not in prices:
                raise KeyError(f"缺少 {symbol} 的現價，無法 mark-to-market")
            current_price = prices[symbol]
            self._assert_currency(current_price)
            equity = equity + current_price * pos.qty
        return equity

    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed_trades)

    # ---- internals ----
    def _assert_currency(self, *moneys: Money) -> None:
        for m in moneys:
            if m.currency is not self._currency:
                raise ValueError(
                    f"幣別不符：portfolio={self._currency}, 輸入={m.currency}"
                )
