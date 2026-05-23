"""股票名稱解析 (best-effort)．

提供 NameResolver 實作給 UI 使用．呼叫慢 (yfinance Ticker.info 約 3~10s)，
故結果快取在 module-level dict 內，同一支股票第二次不會再打 API．

設計：
- 任何例外都吞掉並回 None；UI 端會 fallback 顯示「—」，不影響圖表載入
- TW 自動加 ".TW" 後綴
"""

from __future__ import annotations

from typing import Any

from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol

_NAME_CACHE: dict[str, str | None] = {}


def _ticker_id(symbol: Symbol) -> str:
    return f"{symbol.code}.TW" if symbol.market is Market.TW else symbol.code


def yfinance_name_resolver(symbol: Symbol) -> str | None:
    """以 yfinance 查股票名稱；任何失敗回 None．結果快取避免重複查詢．"""
    cache_key = _ticker_id(symbol)
    if cache_key in _NAME_CACHE:
        return _NAME_CACHE[cache_key]

    name: str | None = None
    try:
        import yfinance as yf  # type: ignore[import-untyped]

        info: Any = yf.Ticker(cache_key).info
        candidate = info.get("longName") or info.get("shortName")
        if isinstance(candidate, str) and candidate.strip():
            name = candidate.strip()
    except Exception:
        name = None

    _NAME_CACHE[cache_key] = name
    return name
