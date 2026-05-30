"""RiskGuard — 純邏輯風控閘門測試．

三條規則（百分比輸入 0~100；0 或 None 視為「停用該限制」）：
- 單筆風險上限 (single_pct)：單一持倉名目 ≤ single_pct × equity
- 總曝險上限 (total_exposure_pct)：所有持倉名目合計 ≤ total_exposure_pct × equity
- 單日熔斷 (circuit_breaker_pct)：當日權益較基準下跌 ≥ 門檻 → 停止所有買進
"""

from __future__ import annotations

from decimal import Decimal

from stocks_trading.risk.guard import RiskDecision, RiskGuard, RiskLimits


class TestNoLimits:
    def test_all_disabled_allows_full(self) -> None:
        guard = RiskGuard(RiskLimits())
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("400"),
        )
        assert isinstance(d, RiskDecision)
        assert d.allowed is True
        assert d.max_notional == Decimal("400")
        assert d.capped is False
        assert d.reason == "ok"

    def test_zero_proposed_blocked(self) -> None:
        # 防呆：預算為 0 不該成交
        guard = RiskGuard(RiskLimits())
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("0"),
        )
        assert d.allowed is False
        assert d.reason == "blocked_zero_budget"


class TestSingleTradeCap:
    def test_caps_to_single_pct(self) -> None:
        # 單檔上限 = 20% × 1000 = 200；想買 400 → 縮到名目 200
        guard = RiskGuard(RiskLimits(single_pct=Decimal("0.20")))
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("400"),
        )
        assert d.allowed is True
        assert d.max_notional == Decimal("200")
        assert d.capped is True
        assert d.reason == "capped_single"

    def test_under_cap_not_capped(self) -> None:
        guard = RiskGuard(RiskLimits(single_pct=Decimal("0.20")))
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("150"),
        )
        assert d.max_notional == Decimal("150")
        assert d.capped is False
        assert d.reason == "ok"


class TestTotalExposureCap:
    def test_caps_to_remaining_exposure(self) -> None:
        guard = RiskGuard(RiskLimits(total_exposure_pct=Decimal("0.8")))
        # 上限 = 0.8 × 1000 = 800；已持 700 → 剩 100
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("700"),
            proposed_notional=Decimal("300"),
        )
        assert d.max_notional == Decimal("100")
        assert d.capped is True
        assert d.reason == "capped_exposure"

    def test_exposure_full_blocks(self) -> None:
        guard = RiskGuard(RiskLimits(total_exposure_pct=Decimal("0.8")))
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("800"),
            proposed_notional=Decimal("100"),
        )
        assert d.allowed is False
        assert d.max_notional == Decimal("0")
        assert d.reason == "blocked_exposure_full"


class TestCircuitBreaker:
    def test_trips_when_drawdown_exceeds(self) -> None:
        guard = RiskGuard(RiskLimits(circuit_breaker_pct=Decimal("0.05")))
        # 從 1000 跌到 940 = -6% ≥ 5% → 停買
        d = guard.evaluate_buy(
            equity=Decimal("940"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("100"),
            day_start_equity=Decimal("1000"),
        )
        assert d.allowed is False
        assert d.reason == "blocked_circuit_breaker"

    def test_not_tripped_below_threshold(self) -> None:
        guard = RiskGuard(RiskLimits(circuit_breaker_pct=Decimal("0.05")))
        # 從 1000 跌到 970 = -3% < 5% → 照常
        d = guard.evaluate_buy(
            equity=Decimal("970"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("100"),
            day_start_equity=Decimal("1000"),
        )
        assert d.allowed is True
        assert d.reason == "ok"

    def test_inactive_without_baseline(self) -> None:
        guard = RiskGuard(RiskLimits(circuit_breaker_pct=Decimal("0.05")))
        # 沒有基準 (首次執行) → 熔斷不啟用
        d = guard.evaluate_buy(
            equity=Decimal("500"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("100"),
            day_start_equity=None,
        )
        assert d.allowed is True


class TestCombinedAndConstruction:
    def test_min_of_single_and_exposure_wins(self) -> None:
        # single 上限 0.20×1000=200；exposure 剩餘 0.8×1000−700=100 → 取 min=100
        guard = RiskGuard(
            RiskLimits(
                single_pct=Decimal("0.20"),
                total_exposure_pct=Decimal("0.8"),
            )
        )
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("700"),
            proposed_notional=Decimal("400"),
        )
        assert d.max_notional == Decimal("100")
        assert d.reason == "capped_exposure"

    def test_single_binds_tighter_than_exposure(self) -> None:
        # single 上限 0.20×1000=200；exposure 剩餘 0.8×1000−500=300 → 取 min=200
        guard = RiskGuard(
            RiskLimits(
                single_pct=Decimal("0.20"),
                total_exposure_pct=Decimal("0.8"),
            )
        )
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("500"),
            proposed_notional=Decimal("400"),
        )
        assert d.max_notional == Decimal("200")
        assert d.reason == "capped_single"

    def test_from_percentages_converts(self) -> None:
        limits = RiskLimits.from_percentages(
            single=25.0, total=80.0, circuit_breaker=5.0
        )
        assert limits.single_pct == Decimal("0.25")
        assert limits.total_exposure_pct == Decimal("0.8")
        assert limits.circuit_breaker_pct == Decimal("0.05")

    def test_from_percentages_zero_means_disabled(self) -> None:
        limits = RiskLimits.from_percentages(
            single=0.0, total=0.0, circuit_breaker=0.0
        )
        assert limits.single_pct is None
        assert limits.total_exposure_pct is None
        assert limits.circuit_breaker_pct is None
