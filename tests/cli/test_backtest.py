"""cli.backtest — 業務邏輯 + 結果格式化測試 (純 Python)．

驗證：
- run_backtest 注入 fetcher 跑完回 BacktestResult (有合理 metrics)
- format_result_text 含關鍵欄位 (總報酬 / 年化 / 最大回撤 / 勝率)
- format_result_json 是合法 JSON，欄位齊全
- 幣別由參數決定 (USD / TWD)
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from stocks_trading.cli.backtest import (
    format_result_json,
    format_result_text,
    run_backtest,
)
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol


def _ramp_bars(start: date, n: int, base: float = 100.0) -> list[Bar]:
    out: list[Bar] = []
    for i in range(n):
        cl = Decimal(str(base + i))
        out.append(
            Bar(
                bar_date=start + timedelta(days=i),
                open=cl,
                high=cl + Decimal("0.5"),
                low=cl - Decimal("0.5"),
                close=cl,
                volume=1000,
            )
        )
    return out


class _FakeRouter:
    def __init__(self, bars_by_symbol: dict[Symbol, list[Bar]]) -> None:
        self._bars = bars_by_symbol

    def fetch_bars(self, symbol: Symbol, start: date, end: date) -> list[Bar]:
        return self._bars.get(symbol, [])


class TestRunBacktest:
    def test_returns_backtest_result(self, tmp_path: Path) -> None:
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})

        result = run_backtest(
            tickers=["SPY"],
            router=router,
            start=date(2026, 1, 1),
            end=date(2026, 1, 30),
            lookback_days=3,
            top_n=1,
            initial_capital=Decimal("10000"),
            currency=Currency.USD,
            tmp_dir=tmp_path,
        )
        assert result.initial_capital.amount == Decimal("10000")
        assert result.final_equity.currency is Currency.USD
        # ramp bars 持續上漲，total_return 應 > 0
        assert result.total_return > Decimal("0")
        # 30 根 bar 內可能來不及完成 round-trip，所以只驗 equity 變動
        assert result.final_equity.amount > result.initial_capital.amount

    def test_twd_backtest(self, tmp_path: Path) -> None:
        symbol_0050 = Symbol("0050", Market.TW)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({symbol_0050: bars})

        result = run_backtest(
            tickers=["0050"],
            router=router,
            start=date(2026, 1, 1),
            end=date(2026, 1, 30),
            lookback_days=3,
            top_n=1,
            initial_capital=Decimal("100000"),
            currency=Currency.TWD,
            tmp_dir=tmp_path,
        )
        assert result.final_equity.currency is Currency.TWD

    def test_empty_bars_returns_result_with_zero_trades(
        self, tmp_path: Path
    ) -> None:
        router = _FakeRouter({})
        result = run_backtest(
            tickers=["SPY"],
            router=router,
            start=date(2026, 1, 1),
            end=date(2026, 1, 30),
            lookback_days=3,
            top_n=1,
            initial_capital=Decimal("10000"),
            currency=Currency.USD,
            tmp_dir=tmp_path,
        )
        # 沒有資料 → 沒有交易，final_equity == initial
        assert result.total_trades == 0
        assert result.final_equity.amount == result.initial_capital.amount


class TestFormatResultText:
    def test_contains_key_metrics(self, tmp_path: Path) -> None:
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})
        result = run_backtest(
            tickers=["SPY"],
            router=router,
            start=date(2026, 1, 1),
            end=date(2026, 1, 30),
            lookback_days=3,
            top_n=1,
            initial_capital=Decimal("10000"),
            currency=Currency.USD,
            tmp_dir=tmp_path,
        )
        text = format_result_text(result)
        assert "總報酬" in text
        assert "年化" in text
        assert "最大回撤" in text
        assert "勝率" in text


class TestFormatResultJson:
    def test_valid_json_with_expected_fields(self, tmp_path: Path) -> None:
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})
        result = run_backtest(
            tickers=["SPY"],
            router=router,
            start=date(2026, 1, 1),
            end=date(2026, 1, 30),
            lookback_days=3,
            top_n=1,
            initial_capital=Decimal("10000"),
            currency=Currency.USD,
            tmp_dir=tmp_path,
        )
        text = format_result_json(result)
        # 必須是合法 JSON
        data = json.loads(text)
        # 必要欄位齊全
        for key in (
            "initial_capital",
            "final_equity",
            "total_return",
            "annualized_return",
            "max_drawdown",
            "win_rate",
            "total_trades",
            "currency",
        ):
            assert key in data, f"缺少欄位 {key}"
        # currency 是 USD / TWD 字串
        assert data["currency"] == "USD"
