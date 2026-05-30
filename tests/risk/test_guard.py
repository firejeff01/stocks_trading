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
    def test_caps_by_risk_to_stop(self) -> None:
        # 1% 法則：equity 10000 × 1% = 最多可虧 100
        # entry 200、stop 180 → 每股風險 20 → 最多 5 股 → 名目上限 1000
        guard = RiskGuard(RiskLimits(single_pct=Decimal("0.01")))
        d = guard.evaluate_buy(
            equity=Decimal("10000"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("4000"),
            entry_price=Decimal("200"),
            stop_price=Decimal("180"),
        )
        assert d.allowed is True
        assert d.max_notional == Decimal("1000")
        assert d.capped is True
        assert d.reason == "capped_single"

    def test_under_cap_not_capped(self) -> None:
        guard = RiskGuard(RiskLimits(single_pct=Decimal("0.01")))
        d = guard.evaluate_buy(
            equity=Decimal("10000"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("600"),
            entry_price=Decimal("200"),
            stop_price=Decimal("180"),
        )
        assert d.max_notional == Decimal("600")
        assert d.capped is False
        assert d.reason == "ok"

    def test_no_stop_skips_single_rule(self) -> None:
        # 無 stop → 單筆風險規則無法套用 → 不限制 (交給總曝險)
        guard = RiskGuard(RiskLimits(single_pct=Decimal("0.01")))
        d = guard.evaluate_buy(
            equity=Decimal("10000"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("4000"),
            entry_price=Decimal("200"),
            stop_price=None,
        )
        assert d.max_notional == Decimal("4000")
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
        # single_cap=(0.05×1000/20)×200=500；exposure 剩餘 100 → 取 min=100
        guard = RiskGuard(
            RiskLimits(
                single_pct=Decimal("0.05"),
                total_exposure_pct=Decimal("0.8"),
            )
        )
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("700"),
            proposed_notional=Decimal("400"),
            entry_price=Decimal("200"),
            stop_price=Decimal("180"),
        )
        assert d.max_notional == Decimal("100")
        assert d.reason == "capped_exposure"

    def test_single_binds_tighter_than_exposure(self) -> None:
        # single_cap=(0.01×1000/20)×200=100；exposure 剩餘 300 → 取 min=100
        guard = RiskGuard(
            RiskLimits(
                single_pct=Decimal("0.01"),
                total_exposure_pct=Decimal("0.8"),
            )
        )
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("500"),
            proposed_notional=Decimal("400"),
            entry_price=Decimal("200"),
            stop_price=Decimal("180"),
        )
        assert d.max_notional == Decimal("100")
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
