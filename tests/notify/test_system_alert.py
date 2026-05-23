"""SystemAlertBuilder — 系統異常告警 email．

Subject: [ALERT] StocksTrading - <錯誤類型>
HTML：時間 / 錯誤訊息 / 堆疊摘要 / 建議行動
"""

from datetime import UTC, datetime

from stocks_trading.notify.system_alert import SystemAlertBuilder


class TestSubject:
    def test_subject_has_alert_tag(self) -> None:
        builder = SystemAlertBuilder()
        msg = builder.build(
            error_type="Shioaji 登入失敗",
            error_message="認證碼過期",
            occurred_at=datetime(2026, 5, 23, 9, 0, tzinfo=UTC),
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert msg.subject.startswith("[ALERT]")
        assert "Shioaji 登入失敗" in msg.subject


class TestBody:
    def test_body_contains_error_message(self) -> None:
        builder = SystemAlertBuilder()
        msg = builder.build(
            error_type="X",
            error_message="connection refused on port 587",
            occurred_at=datetime(2026, 5, 23, 9, 0, tzinfo=UTC),
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert "connection refused" in msg.html_body

    def test_body_includes_occurrence_time(self) -> None:
        builder = SystemAlertBuilder()
        msg = builder.build(
            error_type="X",
            error_message="oops",
            occurred_at=datetime(2026, 5, 23, 9, 0, tzinfo=UTC),
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert "2026-05-23" in msg.html_body

    def test_body_includes_optional_stacktrace(self) -> None:
        builder = SystemAlertBuilder()
        msg = builder.build(
            error_type="X",
            error_message="exc",
            occurred_at=datetime(2026, 5, 23, 9, 0, tzinfo=UTC),
            stacktrace="Traceback (most recent call last):\n  File ...",
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert "Traceback" in msg.html_body

    def test_body_alert_color_red(self) -> None:
        builder = SystemAlertBuilder()
        msg = builder.build(
            error_type="X",
            error_message="exc",
            occurred_at=datetime(2026, 5, 23, 9, 0, tzinfo=UTC),
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        # 應該有紅色標示提醒
        assert "#dc2626" in msg.html_body or "red" in msg.html_body.lower()
