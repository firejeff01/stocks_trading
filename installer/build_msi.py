"""cx_Freeze 打包腳本 — 產出 Windows MSI 安裝檔．

用法：
    .\\.venv\\Scripts\\python.exe installer\\build_msi.py bdist_msi

產出：
    installer/dist/StocksTrading-<version>-amd64.msi

附帶階段：
    build_exe → 凍結 Python + 所有依賴到 build/exe.win-amd64-3.11/
    bdist_msi → 打包成 .msi (依賴 build_exe)

備註：
- base=Win32GUI 使 stocks-trading.exe 啟動無 console (適合一般使用者)
- 額外提供 stocks-trading-cli.exe (有 console) 供 debug / 排程使用
- upgrade_code 固定 → 升級時 MSI 會直接覆蓋舊版而非並存
- migrations *.sql 透過 include_files 強制包入 (cx_Freeze 預設只裝 .py)
"""

from __future__ import annotations

import sys
from pathlib import Path

from cx_Freeze import Executable, setup

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
MIGRATIONS = SRC / "stocks_trading" / "storage" / "migrations"

# 固定 GUID — 不要隨意改，否則升級 MSI 會變成並存安裝
UPGRADE_CODE = "{55fee0e4-d3a1-4cd2-a7b3-c40c5a8a3000}"

VERSION = "2.0.0"

build_exe_options: dict[str, object] = {
    # 自動推導大部分依賴；明確列出主套件確保正確
    "packages": [
        "stocks_trading",
        "PySide6",
        "yfinance",
        "pandas",
        "numpy",
        "sqlite3",
        "smtplib",
        "email",
    ],
    "excludes": [
        "tkinter",
        "test",
        "unittest",
        "pytest",
        "pytest_qt",
        "mypy",
        "ruff",
    ],
    # SQL migration 檔案必須隨包帶入 (cx_Freeze 預設只裝 .py)
    "include_files": [
        (str(MIGRATIONS), "lib/stocks_trading/storage/migrations"),
    ],
    "build_exe": str(
        ROOT / "build"
        / f"exe.win-amd64-{sys.version_info.major}.{sys.version_info.minor}"
    ),
    "optimize": 1,
}

bdist_msi_options: dict[str, object] = {
    "upgrade_code": UPGRADE_CODE,
    "add_to_path": False,
    "initial_target_dir": r"[ProgramFiles64Folder]\StocksTrading",
    "all_users": False,  # per-user 安裝避免 UAC
    "dist_dir": str(ROOT / "installer" / "dist"),
    "summary_data": {
        "author": "Jeff Lin",
        "comments": "Personal automated stock trading system (paper + 模擬)",
    },
}

# GUI 版 (無 console 視窗) — 終端使用者捷徑
gui_exe = Executable(
    script=str(SRC / "stocks_trading" / "app.py"),
    base="Win32GUI",
    target_name="StocksTrading.exe",
    shortcut_name="StocksTrading",
    shortcut_dir="ProgramMenuFolder",
)

# CLI 版 (有 console) — debug 與排程使用
# 注意：必須指向 cli/main.py (而非 app.py)，否則 .exe 會啟動 GUI 而非 CLI
cli_exe = Executable(
    script=str(SRC / "stocks_trading" / "cli" / "main.py"),
    base=None,  # console window 保留
    target_name="StocksTrading-cli.exe",
)


setup(
    name="StocksTrading",
    version=VERSION,
    description="Personal automated stock trading system (TW Shioaji + US email signal)",
    author="Jeff Lin",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=[gui_exe, cli_exe],
)
