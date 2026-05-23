"""手續費 / 滑價 / 證交稅計算 — 純函數，無 I/O．

預設值對應永豐 (台股 6 折網路下單 + 美股複委託 0.5%)；user 設定頁可覆寫．
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side


@dataclass(frozen=True, slots=True)
class FeeConfig:
    # 台股：永豐網路下單 0.1425% × 6 折 = 0.0855%
    tw_commission_rate: Decimal = Decimal("0.000855")
    # 台股：賣方證交稅 0.3%
    tw_sell_tax_rate: Decimal = Decimal("0.003")
    # 台股：無 minimum
    tw_min_commission: Decimal = Decimal("0")
    # 美股 (永豐複委託)：0.5%
    us_commission_rate: Decimal = Decimal("0.005")
    # 美股：每筆 minimum USD 35
    us_min_commission: Decimal = Decimal("35")
    # 兩個市場通用滑價 0.05% (隔日開盤可能不剛好 = 收盤)
    slippage_rate: Decimal = Decimal("0.0005")


def apply_slippage(
    *, open_price: Decimal, side: Side, slippage_rate: Decimal
) -> Decimal:
    """BUY 向上滑、SELL 向下滑 — 都對使用者不利的方向．"""
    factor = (
        Decimal("1") + slippage_rate
        if side is Side.BUY
        else Decimal("1") - slippage_rate
    )
    return open_price * factor


def calculate_commission(
    *, market: Market, notional: Decimal, config: FeeConfig
) -> Decimal:
    """成交價值 × 費率，若小於 minimum 則收 minimum．"""
    if market is Market.TW:
        base = notional * config.tw_commission_rate
        return max(base, config.tw_min_commission)
    # Market.US
    base = notional * config.us_commission_rate
    return max(base, config.us_min_commission)


def calculate_sell_tax(
    *, market: Market, notional: Decimal, config: FeeConfig
) -> Decimal:
    """僅台股賣方收 0.3% 證交稅；其他市場 0．"""
    if market is Market.TW:
        return notional * config.tw_sell_tax_rate
    return Decimal("0")
