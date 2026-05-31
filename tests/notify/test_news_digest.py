"""NewsDigestBuilder — 每日新聞情緒摘要 email．

主旨：[SIM]/[LIVE] 新聞情緒摘要 — 日期
HTML body：TOP 10 候選 (依 score 由大到小)、強訊號醒目色、LLM 用量成本行．
"""

from datetime import date
from decimal import Decimal

from stocks_trading.notify.news_digest import (
    DigestCandidate,
    NewsDigestBuilder,
)


def _candidate(
    *,
    ticker: str = "AAPL",
    market: str = "US",
    side: str = "BUY",
    score: str = "0.50",
    is_strong_signal: bool = False,
    summary: str = "蘋果發表新品",
    num_sources: int = 3,
) -> DigestCandidate:
    return DigestCandidate(
        ticker=ticker,
        market=market,
        side=side,
        score=Decimal(score),
        is_strong_signal=is_strong_signal,
        summary=summary,
        num_sources=num_sources,
    )


class TestSubject:
    def test_sim_subject_tag(self) -> None:
        builder = NewsDigestBuilder()
        msg = builder.build(
            candidates=[_candidate()],
            llm_calls=5,
            llm_cost_usd=Decimal("0.12"),
            as_of=date(2026, 5, 30),
            recipient="me@example.com",
        )
        assert msg.subject.startswith("[SIM]")
        assert "新聞情緒摘要" in msg.subject
        assert "2026-05-30" in msg.subject

    def test_live_subject_tag(self) -> None:
        builder = NewsDigestBuilder()
        msg = builder.build(
            candidates=[_candidate()],
            llm_calls=5,
            llm_cost_usd=Decimal("0.12"),
            as_of=date(2026, 5, 30),
            recipient="me@example.com",
            is_live=True,
        )
        assert msg.subject.startswith("[LIVE]")


class TestTopTen:
    def test_truncates_to_top_10_by_score(self) -> None:
        # 12 個候選，score 各不同；只有前 10 高分應出現
        candidates = [
            _candidate(ticker=f"T{i:02d}", score=f"0.{i:02d}")
            for i in range(12)
        ]
        builder = NewsDigestBuilder()
        msg = builder.build(
            candidates=candidates,
            llm_calls=12,
            llm_cost_usd=Decimal("1.00"),
            as_of=date(2026, 5, 30),
            recipient="me@example.com",
        )
        body = msg.html_body
        # 最高分前 10 名 = T11..T02；最低 2 名 T00 / T01 應被截掉
        assert "T11" in body
        assert "T02" in body
        assert "T01" not in body
        assert "T00" not in body

    def test_sorted_descending(self) -> None:
        low = _candidate(ticker="LOWSCORE", score="0.10")
        high = _candidate(ticker="HIGHSCORE", score="0.90")
        builder = NewsDigestBuilder()
        msg = builder.build(
            candidates=[low, high],
            llm_calls=2,
            llm_cost_usd=Decimal("0.05"),
            as_of=date(2026, 5, 30),
            recipient="me@example.com",
        )
        body = msg.html_body
        assert body.index("HIGHSCORE") < body.index("LOWSCORE")


class TestStrongSignalHighlight:
    def test_strong_signal_row_highlighted(self) -> None:
        builder = NewsDigestBuilder()
        msg = builder.build(
            candidates=[
                _candidate(ticker="STRONGONE", is_strong_signal=True),
            ],
            llm_calls=1,
            llm_cost_usd=Decimal("0.01"),
            as_of=date(2026, 5, 30),
            recipient="me@example.com",
        )
        body = msg.html_body
        assert "STRONGONE" in body
        # 強訊號列應帶醒目背景色 highlight
        assert "background" in body.lower()

    def test_candidate_fields_rendered(self) -> None:
        builder = NewsDigestBuilder()
        msg = builder.build(
            candidates=[
                _candidate(
                    ticker="NVDA",
                    market="US",
                    side="BUY",
                    summary="輝達財報優於預期",
                    num_sources=7,
                ),
            ],
            llm_calls=1,
            llm_cost_usd=Decimal("0.01"),
            as_of=date(2026, 5, 30),
            recipient="me@example.com",
        )
        body = msg.html_body
        assert "NVDA" in body
        assert "US" in body
        assert "BUY" in body
        assert "輝達財報優於預期" in body
        assert "7" in body  # 來源數


class TestCostLine:
    def test_cost_line_present(self) -> None:
        builder = NewsDigestBuilder()
        msg = builder.build(
            candidates=[_candidate()],
            llm_calls=42,
            llm_cost_usd=Decimal("3.14"),
            as_of=date(2026, 5, 30),
            recipient="me@example.com",
        )
        body = msg.html_body
        assert "42" in body
        assert "3.14" in body
        assert "LLM" in body


class TestEmpty:
    def test_empty_candidates_valid_email(self) -> None:
        builder = NewsDigestBuilder()
        msg = builder.build(
            candidates=[],
            llm_calls=0,
            llm_cost_usd=Decimal("0"),
            as_of=date(2026, 5, 30),
            recipient="me@example.com",
        )
        # 仍為合法 email
        assert msg.recipients == ["me@example.com"]
        assert "今日無新聞候選" in msg.html_body
        assert "<html" in msg.html_body.lower()
