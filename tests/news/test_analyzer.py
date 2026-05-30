"""LLMAnalyzer ABC + AnalysisResult — 契約測試．

LLMAnalyzer 是可抽換的 LLM 分析介面 (ClaudeCliAnalyzer / 未來 ClaudeApiAnalyzer
等子類)；本檔只驗介面契約與結果值物件，不碰任何真 LLM．
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from stocks_trading.news.analyzer import (
    AnalysisResult,
    LLMAnalyzer,
    TickerCandidate,
)


class _FakeAnalyzer(LLMAnalyzer):
    """測試用最小子類．"""

    def analyze(
        self, *, title: str, body: str, source: str, lang: str
    ) -> AnalysisResult:
        return AnalysisResult(
            sentiment=Decimal("0.8"),
            impact_score=Decimal("0.6"),
            summary="測試摘要",
            catalysts=("earnings_beat",),
            tickers=(
                TickerCandidate(
                    ticker="AAPL",
                    confidence=Decimal("0.9"),
                    rationale="財報優於預期",
                ),
            ),
            model="haiku",
            input_tokens=100,
            output_tokens=50,
            cost_usd=Decimal("0.06"),
        )


class TestLLMAnalyzerContract:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            LLMAnalyzer()  # type: ignore[abstract]

    def test_subclass_returns_analysis_result(self) -> None:
        result = _FakeAnalyzer().analyze(
            title="Apple beats earnings",
            body="...",
            source="yfinance",
            lang="en",
        )
        assert isinstance(result, AnalysisResult)
        assert result.sentiment == Decimal("0.8")
        assert result.impact_score == Decimal("0.6")
        assert result.catalysts == ("earnings_beat",)
        assert result.tickers[0].ticker == "AAPL"
        assert result.tickers[0].confidence == Decimal("0.9")
        assert result.model == "haiku"
        assert result.cost_usd == Decimal("0.06")


class TestAnalysisResultValueObject:
    def test_is_frozen(self) -> None:
        r = AnalysisResult(
            sentiment=Decimal("0"),
            impact_score=Decimal("0"),
            summary="",
            catalysts=(),
            tickers=(),
            model="m",
            input_tokens=0,
            output_tokens=0,
            cost_usd=Decimal("0"),
        )
        with pytest.raises((AttributeError, TypeError)):
            r.sentiment = Decimal("1")  # type: ignore[misc]

    def test_ticker_candidate_is_frozen(self) -> None:
        t = TickerCandidate(
            ticker="TSLA", confidence=Decimal("0.5"), rationale="x"
        )
        with pytest.raises((AttributeError, TypeError)):
            t.ticker = "NVDA"  # type: ignore[misc]
