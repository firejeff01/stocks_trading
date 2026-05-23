"""AsyncFetcher — 通用背景 worker，把同步 Callable 移到非 main thread．

用途：避免 yfinance 等阻塞 I/O 卡住 PySide6 GUI．

設計：
- QThread 子類，覆寫 run() 跑使用者傳入的 Callable
- 成功 → emit finished_with_result(result)
- 失敗 → emit failed(exc)
- request_cancel() 後不再 emit 上述任何 signal (但 callable 還是會跑完，
  因為 thread 不會被強制中斷；我們只是抑制結果)

注意：QThread 內建的 finished signal 一律會 emit (在 run() 結束時)，
那是 Qt 內部生命週期事件，跟我們的 finished_with_result 是兩回事．
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from PySide6.QtCore import QObject, QThread, Signal

T = TypeVar("T")


class AsyncFetcher(QThread, Generic[T]):
    finished_with_result = Signal(object)
    failed = Signal(object)  # 攜帶 Exception

    def __init__(
        self,
        callable_: Callable[[], T],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._callable = callable_
        self._cancelled = False

    def request_cancel(self) -> None:
        """標記取消；callable 跑完後 emit 會被抑制．"""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:  # QThread override
        try:
            result = self._callable()
        except Exception as exc:
            # 攔截所有同步例外，透過 failed signal 回傳給 UI thread
            if not self._cancelled:
                self.failed.emit(exc)
            return
        if not self._cancelled:
            self.finished_with_result.emit(result)
