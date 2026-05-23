"""SettingsPage — 設定頁 (SMTP / 風控 / 模擬參數)．

讀寫 ConfigStore；密碼欄位走 secret 命名空間 (DPAPI 加密)．
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.config.store import ConfigStore


class _NotificationServiceLike(Protocol):
    def send_test_email(self) -> bool: ...


# Builder callable type: 接 ConfigStore 回 NotificationService 或 None
NotificationServiceBuilder = Callable[[ConfigStore], _NotificationServiceLike | None]


def _default_notification_builder(config: ConfigStore) -> _NotificationServiceLike | None:
    from stocks_trading.notify.notification_service import NotificationService

    return NotificationService.from_config(config=config)


# 接 (api_key, secret_key) 回 True/False 的測試函式
ShioajiTester = Callable[[str, str], bool]


def _default_shioaji_tester(api_key: str, secret_key: str) -> bool:
    """預設用真實 Shioaji login (短暫連線後即 logout)．"""
    try:
        from stocks_trading.data.shioaji_provider import ShioajiDataProvider

        provider = ShioajiDataProvider(api_key=api_key, secret_key=secret_key)
        provider.login()
        provider.logout()
        return True
    except Exception:
        return False


class SettingsPage(QWidget):
    def __init__(
        self,
        *,
        config: ConfigStore,
        notification_service_builder: NotificationServiceBuilder | None = None,
        shioaji_tester: ShioajiTester | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("surface")
        self._config = config
        self._notification_builder = (
            notification_service_builder or _default_notification_builder
        )
        self._shioaji_tester = shioaji_tester or _default_shioaji_tester

        self._smtp_host = QLineEdit()
        self._smtp_port = QSpinBox()
        self._smtp_port.setRange(1, 65535)
        self._smtp_user = QLineEdit()
        self._smtp_recipient = QLineEdit()
        self._smtp_password = QLineEdit()
        self._smtp_password.setEchoMode(QLineEdit.EchoMode.Password)

        self._single_risk_pct = QDoubleSpinBox()
        self._single_risk_pct.setRange(0.0, 100.0)
        self._single_risk_pct.setSingleStep(0.1)
        self._total_exposure_pct = QDoubleSpinBox()
        self._total_exposure_pct.setRange(0.0, 100.0)

        # Shioaji 區塊 (兩個欄位都走 secret 命名空間)
        self._shioaji_api_key = QLineEdit()
        self._shioaji_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._shioaji_secret_key = QLineEdit()
        self._shioaji_secret_key.setEchoMode(QLineEdit.EchoMode.Password)

        self._build_ui()
        self._load_from_config()

    # ---- public helpers for tests ----
    def smtp_host_value(self) -> str:
        return self._smtp_host.text()

    def smtp_port_value(self) -> int:
        return self._smtp_port.value()

    def smtp_user_value(self) -> str:
        return self._smtp_user.text()

    def smtp_recipient_value(self) -> str:
        return self._smtp_recipient.text()

    def smtp_password_value(self) -> str:
        return self._smtp_password.text()

    def single_risk_pct_value(self) -> float:
        return self._single_risk_pct.value()

    def total_exposure_pct_value(self) -> float:
        return self._total_exposure_pct.value()

    # ---- public setters for tests ----
    def set_smtp_host(self, v: str) -> None:
        self._smtp_host.setText(v)

    def set_smtp_port(self, v: int) -> None:
        self._smtp_port.setValue(v)

    def set_smtp_user(self, v: str) -> None:
        self._smtp_user.setText(v)

    def set_smtp_recipient(self, v: str) -> None:
        self._smtp_recipient.setText(v)

    def set_smtp_password(self, v: str) -> None:
        self._smtp_password.setText(v)

    def set_single_risk_pct(self, v: float) -> None:
        self._single_risk_pct.setValue(v)

    def set_total_exposure_pct(self, v: float) -> None:
        self._total_exposure_pct.setValue(v)

    # ---- Shioaji helpers ----
    def shioaji_api_key_value(self) -> str:
        return self._shioaji_api_key.text()

    def shioaji_secret_key_value(self) -> str:
        return self._shioaji_secret_key.text()

    def set_shioaji_api_key(self, v: str) -> None:
        self._shioaji_api_key.setText(v)

    def set_shioaji_secret_key(self, v: str) -> None:
        self._shioaji_secret_key.setText(v)

    def test_shioaji_connection(self) -> bool:
        """先 save 當前表單，再以 tester 試連線；回 True/False．"""
        self.save()
        api_key = self._shioaji_api_key.text()
        secret_key = self._shioaji_secret_key.text()
        if not api_key or not secret_key:
            return False
        return self._shioaji_tester(api_key, secret_key)

    # ---- test email ----
    def send_test_email(self) -> bool:
        """先 save 當前表單，再呼叫 builder 取 NotificationService 寄測試信．"""
        self.save()
        service = self._notification_builder(self._config)
        if service is None:
            return False
        return service.send_test_email()

    def _on_test_email_clicked(self) -> None:
        ok = self.send_test_email()
        if ok:
            self._test_status_label.setText("✓ 測試信已寄出，請檢查收件匣")
        else:
            self._test_status_label.setText(
                "✗ 寄送失敗，請確認 SMTP host / 認證資訊"
            )

    # ---- save ----
    def save(self) -> None:
        self._config.set_plain("smtp.host", self._smtp_host.text())
        self._config.set_plain("smtp.port", self._smtp_port.value())
        self._config.set_plain("smtp.user", self._smtp_user.text())
        self._config.set_plain("smtp.recipient", self._smtp_recipient.text())
        # 密碼走 secret 不入明文
        pwd = self._smtp_password.text()
        if pwd:
            self._config.set_secret("smtp.password", pwd)

        self._config.set_plain("risk.single_pct", self._single_risk_pct.value())
        self._config.set_plain(
            "risk.total_exposure_pct", self._total_exposure_pct.value()
        )

        # Shioaji api_key + secret_key 都走 secret 命名空間
        sj_api = self._shioaji_api_key.text()
        sj_secret = self._shioaji_secret_key.text()
        if sj_api:
            self._config.set_secret("shioaji.api_key", sj_api)
        if sj_secret:
            self._config.set_secret("shioaji.secret_key", sj_secret)

    # ---- UI ----
    def _build_ui(self) -> None:
        # 用 ScrollArea 包整個內容，視窗縮小時可捲動而非溢出
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        container.setObjectName("surface")
        inner = QVBoxLayout(container)
        inner.setContentsMargins(24, 24, 24, 24)
        inner.setSpacing(16)

        inner.addWidget(self._build_smtp_group())
        inner.addWidget(self._build_shioaji_group())
        inner.addWidget(self._build_risk_group())

        actions = QHBoxLayout()
        actions.addStretch(1)
        test_btn = QPushButton("寄送測試信")
        test_btn.setObjectName("ghost")
        test_btn.clicked.connect(self._on_test_email_clicked)
        actions.addWidget(test_btn)
        save_btn = QPushButton("儲存設定")
        save_btn.clicked.connect(self.save)
        actions.addWidget(save_btn)
        inner.addLayout(actions)

        self._test_status_label = QLabel("")
        self._test_status_label.setObjectName("muted")
        inner.addWidget(self._test_status_label)

        inner.addStretch(1)
        scroll.setWidget(container)

    def _build_smtp_group(self) -> QGroupBox:
        group = QGroupBox("Email 通知 (SMTP)")
        form = QFormLayout(group)
        form.addRow(QLabel("SMTP Host"), self._smtp_host)
        form.addRow(QLabel("Port"), self._smtp_port)
        form.addRow(QLabel("使用者帳號"), self._smtp_user)
        form.addRow(QLabel("App Password"), self._smtp_password)
        form.addRow(QLabel("收件人"), self._smtp_recipient)
        return group

    def _build_risk_group(self) -> QGroupBox:
        group = QGroupBox("風險控管")
        form = QFormLayout(group)
        form.addRow(QLabel("單筆風險 (%)"), self._single_risk_pct)
        form.addRow(QLabel("總曝險 (%)"), self._total_exposure_pct)
        return group

    def _build_shioaji_group(self) -> QGroupBox:
        group = QGroupBox("永豐 Shioaji API (台股行情)")
        form = QFormLayout(group)
        form.addRow(QLabel("API Key"), self._shioaji_api_key)
        form.addRow(QLabel("Secret Key"), self._shioaji_secret_key)
        test_btn = QPushButton("測試連線")
        test_btn.setObjectName("ghost")
        test_btn.clicked.connect(self._on_test_shioaji_clicked)
        self._shioaji_status_label = QLabel("")
        self._shioaji_status_label.setObjectName("muted")
        form.addRow("", test_btn)
        form.addRow("", self._shioaji_status_label)
        return group

    def _on_test_shioaji_clicked(self) -> None:
        ok = self.test_shioaji_connection()
        if ok:
            self._shioaji_status_label.setText("✓ Shioaji 登入成功")
        else:
            self._shioaji_status_label.setText(
                "✗ 連線失敗，請確認 API Key / Secret Key"
            )

    def _load_from_config(self) -> None:
        self._smtp_host.setText(self._config.get_plain("smtp.host", "") or "")
        self._smtp_port.setValue(int(self._config.get_plain("smtp.port", 587) or 587))
        self._smtp_user.setText(self._config.get_plain("smtp.user", "") or "")
        self._smtp_recipient.setText(
            self._config.get_plain("smtp.recipient", "") or ""
        )
        pwd = self._config.get_secret("smtp.password")
        if pwd is not None:
            self._smtp_password.setText(pwd)

        self._single_risk_pct.setValue(
            float(self._config.get_plain("risk.single_pct", 1.0) or 1.0)
        )
        self._total_exposure_pct.setValue(
            float(self._config.get_plain("risk.total_exposure_pct", 80.0) or 80.0)
        )

        sj_api = self._config.get_secret("shioaji.api_key")
        if sj_api is not None:
            self._shioaji_api_key.setText(sj_api)
        sj_secret = self._config.get_secret("shioaji.secret_key")
        if sj_secret is not None:
            self._shioaji_secret_key.setText(sj_secret)
