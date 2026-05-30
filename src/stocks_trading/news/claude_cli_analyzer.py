"""ClaudeCliAnalyzer — 透過本機 `claude -p` (使用者的 Claude Max 訂閱) 分析新聞．

設計重點：
- 不直接呼叫 subprocess，而是注入 CliRunner 介面，單元測試餵固定 stdout，
  完全不開真子程序．SubprocessCliRunner 是正式環境實作．
- `claude -p --output-format json` 回傳「單一 JSON envelope」，真正的分析 JSON
  在 envelope 的 `result` 字串裡 (可能含 ``` code fence 或前後雜訊)．
- CRITICAL：claude 發生 API/model 錯誤時 envelope.is_error=true 但「行程仍 exit 0」，
  所以一律解析 envelope 看 is_error，不可只信 returncode．
- 成本：envelope.total_cost_usd 是「用量代理值」(Max 訂閱為定額，非逐次帳單)；
  仍寫入 CostGuard 做每日用量上限．
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from stocks_trading.news.analyzer import (
    AnalysisResult,
    LLMAnalyzer,
    TickerCandidate,
)

# v2.1.158 envelope 欄位形狀；若 CLI 大改版導致 KeyError 會被歸類為可重試 envelope 錯誤
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 529})
_AUTH_STATUS = frozenset({401, 403})
_MAX_BODY_CHARS = 4000

# claude 不在 PATH 時的已知 fallback 路徑 (Windows 使用者安裝位置)
_KNOWN_CLAUDE_PATHS = (
    str(Path.home() / ".local" / "bin" / "claude.exe"),
    str(Path.home() / ".local" / "bin" / "claude"),
)

SYSTEM_PROMPT = (
    "你是一位專業的金融新聞情緒分析師，服務一位以美股為主、同時關注台股的"
    "台灣散戶投資人。規則：\n"
    "1. 只輸出「單一個」JSON 物件，不要任何前後說明文字，不要使用 Markdown "
    "code fence。\n"
    "2. 欄位固定為：sentiment、impact_score、summary、catalysts、tickers。\n"
    "3. sentiment 為 -1.0 到 1.0 的浮點數（-1 極度利空、0 中性、1 極度利多）。\n"
    "4. impact_score 為 0.0 到 1.0 的浮點數，代表此新聞對相關標的短期股價的"
    "潛在影響程度。\n"
    "5. summary 用繁體中文，30 字以內，客觀摘要事件。\n"
    "6. catalysts 為英文事件標籤陣列（例：earnings_beat、guidance_raise、mna、"
    "lawsuit、product_launch），無則回空陣列 []。\n"
    "7. tickers 為陣列，每個元素 {\"ticker\":\"代號大寫\",\"confidence\":0.0到1.0,"
    "\"rationale\":\"繁中說明\"}；無法明確對應時回空陣列 []，禁止臆測或捏造代號。\n"
    "8. 無法判斷時 sentiment 給 0.0、impact_score 給 0.0，不要拒答。"
)


class AnalyzerError(Exception):
    """新聞分析相關錯誤的基類．"""


class ClaudeUnavailableError(AnalyzerError):
    """找不到 claude CLI — 不可重試．"""


class ClaudeNotLoggedInError(AnalyzerError):
    """claude 未登入 / 認證失敗 — 不可重試 (重試也會一直失敗)．"""


class CliEnvelopeError(AnalyzerError):
    """stdout 非合法 JSON envelope 或缺 result / 逾時 — 可重試．"""


class AnalysisParseError(AnalyzerError):
    """無法從 result 文字抽出合法的分析 JSON — 可重試 (模型下次可能就乖了)．"""


class ClaudeApiError(AnalyzerError):
    """envelope.is_error=true 的一般錯誤 (含 model 不存在等)．"""

    def __init__(
        self, message: str, *, status: int | None = None, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class CliResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool


class CliRunner(Protocol):
    def run(self, args: list[str], *, timeout_s: float) -> CliResult: ...


class SubprocessCliRunner:
    """正式環境：以 subprocess 跑 claude CLI；逾時轉成 timed_out 旗標．"""

    def run(self, args: list[str], *, timeout_s: float) -> CliResult:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",  # 強制 utf-8 避免 cp950 console 把繁中變亂碼
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CliResult(stdout="", stderr="", returncode=-1, timed_out=True)
        return CliResult(
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            returncode=proc.returncode,
            timed_out=False,
        )


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _first_json_object(s: str) -> str | None:
    """從第一個 '{' 起做括號配對 (略過字串內的大括號)，回傳最外層物件切片．"""
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _extract_json_object(text: str) -> dict[str, Any]:
    s = text.strip()
    # 去掉 ```json ... ``` code fence
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s).strip()
    candidates = [s]
    sliced = _first_json_object(s)
    if sliced is not None and sliced != s:
        candidates.append(sliced)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise AnalysisParseError("無法從回應抽出 JSON 物件")


def parse_analysis(
    result_text: str,
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Decimal,
) -> AnalysisResult:
    """純函式：把 LLM 回的文字 (可能含 fence/雜訊) 解析成 AnalysisResult．"""
    obj = _extract_json_object(result_text)
    try:
        sentiment = _clamp(
            Decimal(str(obj["sentiment"])), Decimal("-1"), Decimal("1")
        )
        impact = _clamp(
            Decimal(str(obj["impact_score"])), Decimal("0"), Decimal("1")
        )
        summary = str(obj.get("summary", ""))
        catalysts = tuple(
            str(c) for c in (obj.get("catalysts") or []) if str(c).strip()
        )
        tickers = tuple(
            TickerCandidate(
                ticker=str(t["ticker"]).upper(),
                confidence=_clamp(
                    Decimal(str(t.get("confidence", 0))),
                    Decimal("0"),
                    Decimal("1"),
                ),
                rationale=str(t.get("rationale", "")),
            )
            for t in (obj.get("tickers") or [])
            if isinstance(t, dict) and str(t.get("ticker", "")).strip()
        )
    except (KeyError, TypeError, InvalidOperation, ValueError) as exc:
        raise AnalysisParseError(f"分析 JSON 欄位無法解析: {exc}") from exc

    return AnalysisResult(
        sentiment=sentiment,
        impact_score=impact,
        summary=summary,
        catalysts=catalysts,
        tickers=tickers,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )


class ClaudeCliAnalyzer(LLMAnalyzer):
    def __init__(
        self,
        *,
        runner: CliRunner,
        model: str = "haiku",
        claude_bin: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._runner = runner
        self._model = model
        self._claude_bin = claude_bin
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._sleep = sleep

    def analyze(
        self, *, title: str, body: str, source: str, lang: str
    ) -> AnalysisResult:
        bin_path = self._resolve_bin()
        user_prompt = self._build_prompt(
            title=title, body=body, source=source, lang=lang
        )
        args = [
            bin_path,
            "-p",
            user_prompt,
            "--output-format",
            "json",
            "--model",
            self._model,
            "--append-system-prompt",
            SYSTEM_PROMPT,
        ]

        last_exc: AnalyzerError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._run_once(args)
            except (CliEnvelopeError, AnalysisParseError) as exc:
                last_exc = exc  # 可重試
            except ClaudeApiError as exc:
                if not exc.retryable:
                    raise
                last_exc = exc
            if attempt < self._max_retries:
                self._sleep(float(2**attempt))  # 1s, 2s 退避
        assert last_exc is not None  # 迴圈至少跑一次
        raise last_exc

    def _run_once(self, args: list[str]) -> AnalysisResult:
        res = self._runner.run(args, timeout_s=self._timeout_s)
        if res.timed_out:
            raise CliEnvelopeError("claude -p 逾時")
        try:
            env = json.loads(res.stdout)
        except json.JSONDecodeError as exc:
            raise CliEnvelopeError(
                f"claude 輸出非 JSON: {res.stdout[:200]!r}"
            ) from exc
        if not isinstance(env, dict):
            raise CliEnvelopeError("claude envelope 非物件")

        if env.get("is_error"):
            status = env.get("api_error_status")
            status_int = status if isinstance(status, int) else None
            if status_int in _AUTH_STATUS:
                raise ClaudeNotLoggedInError("claude 未登入或認證失敗")
            raise ClaudeApiError(
                f"claude 回報錯誤 (status={status})",
                status=status_int,
                retryable=status_int in _RETRYABLE_STATUS,
            )

        result_text = env.get("result")
        if not isinstance(result_text, str) or not result_text.strip():
            raise CliEnvelopeError("claude envelope 缺 result")

        usage = env.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = _as_int(usage.get("input_tokens"))
        output_tokens = _as_int(usage.get("output_tokens"))
        cost_usd = _as_decimal(env.get("total_cost_usd"))
        return parse_analysis(
            result_text,
            model=self._resolve_model_name(env),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    def _resolve_model_name(self, env: dict[str, Any]) -> str:
        model_usage = env.get("modelUsage")
        if isinstance(model_usage, dict) and model_usage:
            return str(next(iter(model_usage)))
        return self._model

    def _resolve_bin(self) -> str:
        if self._claude_bin:
            return self._claude_bin
        found = shutil.which("claude")
        if found:
            return found
        for path in _KNOWN_CLAUDE_PATHS:
            if Path(path).exists():
                return path
        raise ClaudeUnavailableError(
            "找不到 claude CLI (請確認 Claude Code 已安裝且在 PATH)"
        )

    @staticmethod
    def _build_prompt(*, title: str, body: str, source: str, lang: str) -> str:
        return (
            "請分析以下新聞並只回傳符合系統指示格式的 JSON。\n"
            f"標題：{title}\n"
            f"來源：{source}（語言：{lang}）\n"
            f"內文：{body[:_MAX_BODY_CHARS]}"
        )


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _as_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
