"""ClaudeCliAnalyzer — 以注入的 fake runner 測試，完全不開真子程序．

涵蓋：
- 純函式 parse_analysis：乾淨 JSON / code fence / 前綴雜訊 / 範圍夾擠 / 缺欄位 / 壞格式
- analyze 行為：happy / is_error 不可重試 / 可重試後成功 / 未登入 / 壞 envelope 重試耗盡 /
  逾時重試 / claude 不存在
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from stocks_trading.news.analyzer import AnalysisResult
from stocks_trading.news.claude_cli_analyzer import (
    AnalysisParseError,
    ClaudeApiError,
    ClaudeCliAnalyzer,
    ClaudeNotLoggedInError,
    ClaudeUnavailableError,
    CliEnvelopeError,
    CliResult,
    parse_analysis,
)

_ANALYSIS = {
    "sentiment": 0.8,
    "impact_score": 0.6,
    "summary": "蘋果財報優於預期",
    "catalysts": ["earnings_beat"],
    "tickers": [
        {"ticker": "aapl", "confidence": 0.9, "rationale": "財報優於預期"}
    ],
}


class _QueueRunner:
    """依序回傳預先排好的 CliResult，並計呼叫次數．"""

    def __init__(self, results: list[CliResult]) -> None:
        self._results = list(results)
        self.calls = 0

    def run(self, args: list[str], *, timeout_s: float) -> CliResult:
        self.calls += 1
        return self._results.pop(0)


def _envelope_result(
    result_text: str,
    *,
    is_error: bool = False,
    api_error_status: int | None = None,
    cost: float = 0.06,
    usage: dict[str, int] | None = None,
) -> CliResult:
    env: dict[str, object] = {
        "type": "result",
        "subtype": "success",
        "is_error": is_error,
        "total_cost_usd": cost,
        "usage": usage or {"input_tokens": 120, "output_tokens": 48},
    }
    if api_error_status is not None:
        env["api_error_status"] = api_error_status
    if not is_error:
        env["result"] = result_text
    return CliResult(
        stdout=json.dumps(env, ensure_ascii=False),
        stderr="",
        returncode=0,
        timed_out=False,
    )


def _ok_envelope() -> CliResult:
    return _envelope_result(json.dumps(_ANALYSIS, ensure_ascii=False))


def _analyzer(runner: _QueueRunner, **kw: object) -> ClaudeCliAnalyzer:
    return ClaudeCliAnalyzer(
        runner=runner,
        claude_bin="claude",  # 跳過 which()；fake runner 不在乎實際路徑
        max_retries=2,
        sleep=lambda _s: None,  # 重試不真的等待
        **kw,  # type: ignore[arg-type]
    )


class TestParseAnalysis:
    def test_clean_json(self) -> None:
        r = parse_analysis(
            json.dumps(_ANALYSIS, ensure_ascii=False),
            model="haiku",
            input_tokens=10,
            output_tokens=5,
            cost_usd=Decimal("0.01"),
        )
        assert isinstance(r, AnalysisResult)
        assert r.sentiment == Decimal("0.8")
        assert r.impact_score == Decimal("0.6")
        assert r.catalysts == ("earnings_beat",)
        assert r.tickers[0].ticker == "AAPL"  # 自動轉大寫
        assert r.tickers[0].confidence == Decimal("0.9")

    def test_code_fenced_json(self) -> None:
        text = "```json\n" + json.dumps(_ANALYSIS, ensure_ascii=False) + "\n```"
        r = parse_analysis(
            text, model="m", input_tokens=0, output_tokens=0, cost_usd=Decimal("0")
        )
        assert r.sentiment == Decimal("0.8")

    def test_prose_prefixed_json_brace_matched(self) -> None:
        text = "好的，以下是分析結果：\n" + json.dumps(_ANALYSIS) + "\n希望有幫助"
        r = parse_analysis(
            text, model="m", input_tokens=0, output_tokens=0, cost_usd=Decimal("0")
        )
        assert r.tickers[0].ticker == "AAPL"

    def test_out_of_range_values_clamped(self) -> None:
        obj = {
            "sentiment": 5,
            "impact_score": 9,
            "summary": "x",
            "catalysts": [],
            "tickers": [],
        }
        r = parse_analysis(
            json.dumps(obj), model="m", input_tokens=0, output_tokens=0,
            cost_usd=Decimal("0"),
        )
        assert r.sentiment == Decimal("1")  # 夾到 [-1,1]
        assert r.impact_score == Decimal("1")  # 夾到 [0,1]

    def test_missing_optional_fields_default_empty(self) -> None:
        obj = {"sentiment": 0, "impact_score": 0, "summary": "x"}
        r = parse_analysis(
            json.dumps(obj), model="m", input_tokens=0, output_tokens=0,
            cost_usd=Decimal("0"),
        )
        assert r.catalysts == ()
        assert r.tickers == ()

    def test_malformed_raises(self) -> None:
        with pytest.raises(AnalysisParseError):
            parse_analysis(
                "這完全不是 JSON", model="m", input_tokens=0, output_tokens=0,
                cost_usd=Decimal("0"),
            )


class TestAnalyzeHappyPath:
    def test_returns_result_with_cost_and_tokens(self) -> None:
        runner = _QueueRunner([_ok_envelope()])
        result = _analyzer(runner).analyze(
            title="Apple beats", body="...", source="yfinance", lang="en"
        )
        assert result.sentiment == Decimal("0.8")
        assert result.tickers[0].ticker == "AAPL"
        assert result.cost_usd == Decimal("0.06")
        assert result.input_tokens == 120
        assert result.output_tokens == 48
        assert runner.calls == 1

    def test_fenced_result_text(self) -> None:
        fenced = "```json\n" + json.dumps(_ANALYSIS, ensure_ascii=False) + "\n```"
        runner = _QueueRunner([_envelope_result(fenced)])
        result = _analyzer(runner).analyze(
            title="t", body="b", source="yfinance", lang="en"
        )
        assert result.sentiment == Decimal("0.8")


class TestAnalyzeErrors:
    def test_is_error_nonretryable_raises_immediately(self) -> None:
        runner = _QueueRunner(
            [_envelope_result("", is_error=True, api_error_status=404)]
        )
        with pytest.raises(ClaudeApiError):
            _analyzer(runner).analyze(title="t", body="b", source="s", lang="en")
        assert runner.calls == 1  # 不重試

    def test_is_error_retryable_then_success(self) -> None:
        runner = _QueueRunner(
            [
                _envelope_result("", is_error=True, api_error_status=529),
                _ok_envelope(),
            ]
        )
        result = _analyzer(runner).analyze(
            title="t", body="b", source="s", lang="en"
        )
        assert result.sentiment == Decimal("0.8")
        assert runner.calls == 2

    def test_not_logged_in_raises(self) -> None:
        runner = _QueueRunner(
            [_envelope_result("", is_error=True, api_error_status=401)]
        )
        with pytest.raises(ClaudeNotLoggedInError):
            _analyzer(runner).analyze(title="t", body="b", source="s", lang="en")
        assert runner.calls == 1

    def test_bad_envelope_retries_then_raises(self) -> None:
        bad = CliResult(
            stdout="oops not json", stderr="", returncode=0, timed_out=False
        )
        runner = _QueueRunner([bad, bad, bad])
        with pytest.raises(CliEnvelopeError):
            _analyzer(runner).analyze(title="t", body="b", source="s", lang="en")
        assert runner.calls == 3  # 初次 + 2 retry

    def test_timeout_retries_then_succeeds(self) -> None:
        timeout = CliResult(
            stdout="", stderr="", returncode=-1, timed_out=True
        )
        runner = _QueueRunner([timeout, timeout, _ok_envelope()])
        result = _analyzer(runner).analyze(
            title="t", body="b", source="s", lang="en"
        )
        assert result.sentiment == Decimal("0.8")
        assert runner.calls == 3

    def test_claude_unavailable_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import stocks_trading.news.claude_cli_analyzer as mod

        monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
        monkeypatch.setattr(mod, "_KNOWN_CLAUDE_PATHS", ())  # 連已知路徑也清空
        analyzer = ClaudeCliAnalyzer(
            runner=_QueueRunner([_ok_envelope()]),
            claude_bin=None,  # 強制走 which() 解析 → None
        )
        with pytest.raises(ClaudeUnavailableError):
            analyzer.analyze(title="t", body="b", source="s", lang="en")
