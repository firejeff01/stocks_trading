"""StrategyPage 規格 — Dual Momentum 參數設定持久化．"""

from pytestqt.qtbot import QtBot

from stocks_trading.config.store import ConfigStore
from stocks_trading.ui.strategy_page import StrategyPage


class TestStrategyPage:
    def test_defaults(self, qtbot: QtBot, config: ConfigStore) -> None:
        page = StrategyPage(config=config)
        qtbot.addWidget(page)
        assert page.lookback_value() == 252
        assert page.top_n_value() == 2
        assert page.abs_momentum_threshold_value() == 4.0

    def test_load_from_config(self, qtbot: QtBot, config: ConfigStore) -> None:
        config.set_plain("strategy.dual_momentum.lookback", 60)
        config.set_plain("strategy.dual_momentum.top_n", 3)
        config.set_plain("strategy.dual_momentum.abs_momentum_threshold", 5.0)
        page = StrategyPage(config=config)
        qtbot.addWidget(page)
        assert page.lookback_value() == 60
        assert page.top_n_value() == 3
        assert page.abs_momentum_threshold_value() == 5.0

    def test_save_persists(self, qtbot: QtBot, config: ConfigStore) -> None:
        page = StrategyPage(config=config)
        qtbot.addWidget(page)
        page.set_lookback(120)
        page.set_top_n(4)
        page.set_abs_momentum_threshold(3.5)
        page.save()
        assert config.get_plain("strategy.dual_momentum.lookback") == 120
        assert config.get_plain("strategy.dual_momentum.top_n") == 4
        assert config.get_plain("strategy.dual_momentum.abs_momentum_threshold") == 3.5
