"""Storage layer — SQLite 持久化、migration、備份．"""

from pathlib import Path

MIGRATIONS_DIR: Path = Path(__file__).parent / "migrations"
"""內建 migration .sql 檔案目錄．"""
