"""初始 schema migration (0001_initial.sql) 規格 — 對應 SA data_design.md §1．

v1.0 預建 v2.0 空表的策略 (data_design.md §2)：一次性建 17 張表，降低升級風險．

驗收重點：
- apply_pending() 套用 0001 後 schema_version = 1
- 所有預期表都存在
- accounts 表 seed 4 列（雙帳本 × 雙幣別）
- LIVE 帳本預設 is_frozen=1
- CHECK constraint 拒絕非法值 (e.g. accounts.mode 不能是 'PAPER')
"""

import sqlite3
from pathlib import Path

import pytest

from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner

EXPECTED_TABLES = {
    "schema_version",
    "accounts",
    "positions",
    "orders",
    "signals",
    "daily_pnl",
    "kbars_cache",
    "app_log",
    "audit_log",
    "news_articles",
    "news_analysis",
    "news_tickers",
    "watchlist",
    "llm_cost_daily",
    "blacklist",
    "source_credibility",
    "chart_patterns_cache",
}


@pytest.fixture
def applied_db(tmp_path: Path) -> Path:
    """提供已套用 0001 的 SQLite DB．"""
    db = tmp_path / "app.db"
    runner = MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR)
    runner.apply_pending()
    return db


def _all_tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }


class TestInitialSchemaApplied:
    def test_schema_version_set_to_one(self, applied_db: Path) -> None:
        runner = MigrationRunner(db_path=applied_db, migrations_dir=MIGRATIONS_DIR)
        assert runner.current_version() == 1

    def test_all_expected_tables_exist(self, applied_db: Path) -> None:
        tables = _all_tables(applied_db)
        missing = EXPECTED_TABLES - tables
        assert not missing, f"缺少表：{missing}"


class TestAccountSeedData:
    def test_four_seed_accounts(self, applied_db: Path) -> None:
        with sqlite3.connect(applied_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        assert count == 4

    def test_sim_accounts_not_frozen(self, applied_db: Path) -> None:
        with sqlite3.connect(applied_db) as conn:
            rows = conn.execute(
                "SELECT name, is_frozen FROM accounts WHERE mode='SIMULATION'"
            ).fetchall()
        assert len(rows) == 2
        for _name, is_frozen in rows:
            assert is_frozen == 0

    def test_live_accounts_default_frozen(self, applied_db: Path) -> None:
        # LIVE 帳本預設 is_frozen=1，待 v1.5 切到實盤時才解凍
        with sqlite3.connect(applied_db) as conn:
            rows = conn.execute(
                "SELECT name, is_frozen FROM accounts WHERE mode='LIVE'"
            ).fetchall()
        assert len(rows) == 2
        for _name, is_frozen in rows:
            assert is_frozen == 1

    def test_currencies_cover_twd_and_usd(self, applied_db: Path) -> None:
        with sqlite3.connect(applied_db) as conn:
            currencies = {
                row[0]
                for row in conn.execute("SELECT DISTINCT currency FROM accounts")
            }
        assert currencies == {"TWD", "USD"}

    def test_account_uniqueness_mode_broker_currency(self, applied_db: Path) -> None:
        # 同 (mode, broker, currency) 組合不能重複（per SA UNIQUE 約束）
        with sqlite3.connect(applied_db) as conn, pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO accounts "
                    "(name, mode, broker, currency, init_capital, current_equity, "
                    " is_frozen, created_at) "
                    "VALUES ('Dup', 'SIMULATION', 'simulated', 'TWD', '1', '1', 0, "
                    "datetime('now'))"
                )


class TestCheckConstraints:
    def test_account_mode_check(self, applied_db: Path) -> None:
        with (
            sqlite3.connect(applied_db) as conn,
            pytest.raises(sqlite3.IntegrityError, match=r"(CHECK|check)"),
        ):
                conn.execute(
                    "INSERT INTO accounts "
                    "(name, mode, broker, currency, init_capital, current_equity, "
                    " is_frozen, created_at) "
                    "VALUES ('X', 'PAPER', 'simulated', 'TWD', '1', '1', 0, "
                    "datetime('now'))"
                )

    def test_signal_status_check(self, applied_db: Path) -> None:
        # 必須使用合法的 9 個狀態之一
        with (
            sqlite3.connect(applied_db) as conn,
            pytest.raises(sqlite3.IntegrityError, match=r"(CHECK|check)"),
        ):
                conn.execute(
                    "INSERT INTO signals "
                    "(strategy_id, symbol, market, side, target_price, suggested_qty, "
                    " reason, generated_at, status, mode, account_id) "
                    "VALUES ('s', 'SPY', 'US', 'BUY', '100', 1, 'r', "
                    " datetime('now'), 'BOGUS_STATUS', 'SIMULATION', 1)"
                )

    def test_orders_status_check(self, applied_db: Path) -> None:
        with (
            sqlite3.connect(applied_db) as conn,
            pytest.raises(sqlite3.IntegrityError, match=r"(CHECK|check)"),
        ):
                conn.execute(
                    "INSERT INTO orders "
                    "(account_id, mode, symbol, market, side, order_type, qty, "
                    " status, placed_at) "
                    "VALUES (1, 'SIMULATION', 'SPY', 'US', 'BUY', 'LIMIT', 1, "
                    "'INVALID', datetime('now'))"
                )

    def test_kbars_source_check(self, applied_db: Path) -> None:
        with (
            sqlite3.connect(applied_db) as conn,
            pytest.raises(sqlite3.IntegrityError, match=r"(CHECK|check)"),
        ):
                conn.execute(
                    "INSERT INTO kbars_cache "
                    "(symbol, market, date, open, high, low, close, volume, "
                    " source, fetched_at) "
                    "VALUES ('SPY', 'US', '2026-05-23', '1','1','1','1', 1, "
                    "'bloomberg', datetime('now'))"
                )


class TestSourceCredibilitySeed:
    def test_eight_default_sources_seeded(self, applied_db: Path) -> None:
        # SA seed: reuters/edgar/cnbc/yfinance/ars_technica/techcrunch/the_verge/reddit
        with sqlite3.connect(applied_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM source_credibility").fetchone()[0]
        assert count == 8

    def test_reuters_and_edgar_have_high_credibility(self, applied_db: Path) -> None:
        with sqlite3.connect(applied_db) as conn:
            cred = dict(
                conn.execute(
                    "SELECT source, credibility FROM source_credibility "
                    "WHERE source IN ('reuters', 'edgar')"
                )
            )
        assert cred["reuters"] >= 0.8
        assert cred["edgar"] >= 0.9
