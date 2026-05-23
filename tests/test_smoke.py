"""煙霧測試 — 確認 pytest 與 src layout 可運作."""

import stocks_trading


def test_package_version_exposed() -> None:
    assert stocks_trading.__version__ == "0.1.1"
