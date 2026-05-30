"""LLMAnalyzer — 可抽換的新聞情緒分析介面 + 結果值物件．

子類負責「如何呼叫 LLM」(ClaudeCliAnalyzer 走使用者的 Claude Max `claude -p`；
未來可加 ClaudeApiAnalyzer / OllamaAnalyzer)，上層的 collector / ranker / pipeline
只依賴本 ABC，換後端不必動其他程式．
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TickerCandidate:
    """LLM 從新聞抽出的個股候選．"""

    ticker: str
    confidence: Decimal  # 0.0 ~ 1.0
    rationale: str


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """單篇新聞的結構化分析結果 (對映 news_analysis 表)．

    - sentiment：-1.0 (極度利空) ~ 1.0 (極度利多)
    - impact_score：0.0 ~ 1.0，對相關標的短期股價的潛在影響程度
    - catalysts：英文事件標籤 (earnings_beat / guidance_raise / mna ...)
    - tickers：相關個股候選 (含 confidence)
    - input_tokens / output_tokens / cost_usd：用量與成本代理值 (給 CostGuard)
    """

    sentiment: Decimal
    impact_score: Decimal
    summary: str
    catalysts: tuple[str, ...]
    tickers: tuple[TickerCandidate, ...]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class LLMAnalyzer(ABC):
    @abstractmethod
    def analyze(
        self, *, title: str, body: str, source: str, lang: str
    ) -> AnalysisResult:
        """分析單篇新聞，回傳結構化情緒結果．

        實作失敗時應 raise (讓上層略過該篇、留待下次重試)，不可捏造中性結果．
        """
        ...
