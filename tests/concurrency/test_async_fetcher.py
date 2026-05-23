"""AsyncFetcher — 通用背景 worker (QThread)．

設計目標：
- 接受任意 Callable[[], T]，在非 main thread 跑
- 成功 emit finished_with_result(T)
- 失敗 emit failed(Exception)
- 可 request_cancel() — 取消後不再 emit result / failed

測試使用 pytest-qt 的 waitSignal 等待非同步事件．
"""

from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication, QThread
from pytestqt.qtbot import QtBot

from stocks_trading.concurrency.async_fetcher import AsyncFetcher


class TestAsyncFetcherSuccess:
    def test_emits_result_on_success(self, qtbot: QtBot) -> None:
        fetcher: AsyncFetcher[int] = AsyncFetcher(lambda: 42)
        with qtbot.waitSignal(
            fetcher.finished_with_result, timeout=2000
        ) as blocker:
            fetcher.start()
        assert blocker.args == [42]

    def test_callable_runs_off_main_thread(self, qtbot: QtBot) -> None:
        app = QCoreApplication.instance()
        assert app is not None
        main_thread = app.thread()
        captured: dict[str, QThread] = {}

        def fn() -> str:
            captured["thread"] = QThread.currentThread()
            return "ok"

        fetcher: AsyncFetcher[str] = AsyncFetcher(fn)
        with qtbot.waitSignal(fetcher.finished_with_result, timeout=2000):
            fetcher.start()
        assert captured["thread"] is not main_thread


class TestAsyncFetcherFailure:
    def test_emits_failed_on_exception(self, qtbot: QtBot) -> None:
        def boom() -> int:
            raise ValueError("kaboom")

        fetcher: AsyncFetcher[int] = AsyncFetcher(boom)
        with qtbot.waitSignal(fetcher.failed, timeout=2000) as blocker:
            fetcher.start()
        exc = blocker.args[0]
        assert isinstance(exc, ValueError)
        assert "kaboom" in str(exc)

    def test_failed_signal_excludes_finished(self, qtbot: QtBot) -> None:
        """失敗時不該同時 emit finished_with_result．"""
        results: list[int] = []

        def boom() -> int:
            raise RuntimeError("nope")

        fetcher: AsyncFetcher[int] = AsyncFetcher(boom)
        fetcher.finished_with_result.connect(lambda r: results.append(r))
        with qtbot.waitSignal(fetcher.failed, timeout=2000):
            fetcher.start()
        # 等執行緒徹底結束才驗證 (避免 race)
        fetcher.wait(2000)
        assert results == []


class TestAsyncFetcherCancellation:
    def test_cancel_before_finish_suppresses_result(self, qtbot: QtBot) -> None:
        """cancel 後 callable 即使 return，也不該 emit finished_with_result．"""
        results: list[int] = []

        def slow() -> int:
            time.sleep(0.3)
            return 1

        fetcher: AsyncFetcher[int] = AsyncFetcher(slow)
        fetcher.finished_with_result.connect(lambda r: results.append(r))
        fetcher.start()
        # 立刻取消 (callable 還在 sleep)
        fetcher.request_cancel()
        # 等執行緒結束
        assert fetcher.wait(2000)
        assert results == []

    def test_cancel_before_finish_suppresses_failed(
        self, qtbot: QtBot
    ) -> None:
        """cancel 後 callable 拋例外，也不該 emit failed．"""
        errors: list[Exception] = []

        def slow_boom() -> int:
            time.sleep(0.3)
            raise RuntimeError("late boom")

        fetcher: AsyncFetcher[int] = AsyncFetcher(slow_boom)
        fetcher.failed.connect(lambda e: errors.append(e))
        fetcher.start()
        fetcher.request_cancel()
        assert fetcher.wait(2000)
        assert errors == []


class TestAsyncFetcherLifecycle:
    def test_does_not_start_until_start_called(self, qtbot: QtBot) -> None:
        ran: list[bool] = []
        fetcher: AsyncFetcher[None] = AsyncFetcher(lambda: ran.append(True))
        # 只建構不 start
        qtbot.wait(100)
        assert ran == []
        # 真正 start 之後才會跑
        with qtbot.waitSignal(fetcher.finished_with_result, timeout=2000):
            fetcher.start()
        assert ran == [True]
