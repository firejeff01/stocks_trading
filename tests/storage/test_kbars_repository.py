"""KbarsRepository — kbars_cache 表 read/write 規格．

API:
- save_bars(symbol, bars, source) -> int 已寫入筆數
- get_bars(symbol, start, end) -> list[Bar] 排序遞增、含端點
- latest_date(symbol) -> date | None
- delete(symbol) -> int 已刪除筆數 (FR-DL-04 強制重抓)
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.kbars_repository import KbarSource, KbarsRepository
from stocks_trading.storage.migration import MigrationRunner


def _bar(
    d: date, o: str = "100", h: str | None = None, lo: str | None = None,
    c: str = "103", v: int = 1000,
) -> Bar:
    open_d = Decimal(o)
    close_d = Decimal(c)
    # 自動推 high / low 以滿足不變式 (測試 helper 便利)
    high_d = Decimal(h) if h is not None else max(open_d, close_d) + Decimal("1")
    low_d = Decimal(lo) if lo is not None else min(open_d, close_d) - Decimal("1")
    return Bar(d, open_d, high_d, low_d, close_d, v)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> KbarsRepository:
    return KbarsRepository(db_path=db_path)


@pytest.fixture
def spy() -> Symbol:
    return Symbol("SPY", Market.US)


@pytest.fixture
def tw_0050() -> Symbol:
    return Symbol("0050", Market.TW)


class TestEmpty:
    def test_get_bars_returns_empty_list(self, repo: KbarsRepository, spy: Symbol) -> None:
        assert repo.get_bars(spy, date(2020, 1, 1), date(2026, 12, 31)) == []

    def test_latest_date_returns_none(self, repo: KbarsRepository, spy: Symbol) -> None:
        assert repo.latest_date(spy) is None


class TestSaveAndGet:
    def test_save_returns_count(self, repo: KbarsRepository, spy: Symbol) -> None:
        bars = [_bar(date(2026, 5, 21)), _bar(date(2026, 5, 22))]
        assert repo.save_bars(spy, bars, KbarSource.YFINANCE) == 2

    def test_save_then_get_roundtrip(self, repo: KbarsRepository, spy: Symbol) -> None:
        bars = [_bar(date(2026, 5, 21), c="200"), _bar(date(2026, 5, 22), c="210")]
        repo.save_bars(spy, bars, KbarSource.YFINANCE)
        got = repo.get_bars(spy, date(2026, 5, 21), date(2026, 5, 22))
        assert got == bars

    def test_get_filters_by_date_range_inclusive(
        self, repo: KbarsRepository, spy: Symbol
    ) -> None:
        bars = [
            _bar(date(2026, 5, 19)),
            _bar(date(2026, 5, 20)),
            _bar(date(2026, 5, 21)),
            _bar(date(2026, 5, 22)),
        ]
        repo.save_bars(spy, bars, KbarSource.YFINANCE)
        got = repo.get_bars(spy, date(2026, 5, 20), date(2026, 5, 21))
        assert [b.bar_date for b in got] == [date(2026, 5, 20), date(2026, 5, 21)]

    def test_get_returns_ascending_date_order(
        self, repo: KbarsRepository, spy: Symbol
    ) -> None:
        bars = [_bar(date(2026, 5, 22)), _bar(date(2026, 5, 20)), _bar(date(2026, 5, 21))]
        repo.save_bars(spy, bars, KbarSource.YFINANCE)
        got = repo.get_bars(spy, date(2026, 5, 19), date(2026, 5, 23))
        assert [b.bar_date for b in got] == [
            date(2026, 5, 20),
            date(2026, 5, 21),
            date(2026, 5, 22),
        ]


class TestUpsert:
    def test_save_same_symbol_date_replaces(self, repo: KbarsRepository, spy: Symbol) -> None:
        # 同 symbol+market+date 再寫一次 → REPLACE，不應拋例外
        repo.save_bars(spy, [_bar(date(2026, 5, 22), c="200")], KbarSource.YFINANCE)
        repo.save_bars(spy, [_bar(date(2026, 5, 22), c="999")], KbarSource.YFINANCE)
        got = repo.get_bars(spy, date(2026, 5, 22), date(2026, 5, 22))
        assert len(got) == 1
        assert got[0].close == Decimal("999")


class TestLatestDate:
    def test_returns_most_recent(self, repo: KbarsRepository, spy: Symbol) -> None:
        repo.save_bars(
            spy,
            [
                _bar(date(2026, 5, 19)),
                _bar(date(2026, 5, 21)),
                _bar(date(2026, 5, 20)),
            ],
            KbarSource.YFINANCE,
        )
        assert repo.latest_date(spy) == date(2026, 5, 21)


class TestDelete:
    def test_delete_removes_all_bars_for_symbol(
        self, repo: KbarsRepository, spy: Symbol
    ) -> None:
        bars = [_bar(date(2026, 5, 20)), _bar(date(2026, 5, 21))]
        repo.save_bars(spy, bars, KbarSource.YFINANCE)
        deleted = repo.delete(spy)
        assert deleted == 2
        assert repo.get_bars(spy, date(2020, 1, 1), date(2030, 1, 1)) == []


class TestSymbolIsolation:
    def test_different_symbols_dont_collide(
        self, repo: KbarsRepository, spy: Symbol, tw_0050: Symbol
    ) -> None:
        repo.save_bars(spy, [_bar(date(2026, 5, 22), c="500")], KbarSource.YFINANCE)
        repo.save_bars(tw_0050, [_bar(date(2026, 5, 22), c="180")], KbarSource.YFINANCE)

        spy_bars = repo.get_bars(spy, date(2026, 5, 22), date(2026, 5, 22))
        tw_bars = repo.get_bars(tw_0050, date(2026, 5, 22), date(2026, 5, 22))
        assert spy_bars[0].close == Decimal("500")
        assert tw_bars[0].close == Decimal("180")
        assert repo.delete(spy) == 1
        # 刪 spy 不該影響 tw_0050
        assert repo.get_bars(tw_0050, date(2026, 5, 22), date(2026, 5, 22))


class TestKbarSourceEnum:
    def test_only_two_sources_match_schema_check(self) -> None:
        # CHECK (source IN ('shioaji','yfinance'))
        assert {s.value for s in KbarSource} == {"shioaji", "yfinance"}
