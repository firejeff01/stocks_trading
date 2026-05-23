"""EmailMessage — 不可變 email 值物件．"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EmailMessage:
    sender: str
    recipients: list[str] = field(default_factory=list)
    subject: str = ""
    html_body: str = ""

    def __post_init__(self) -> None:
        if not self.recipients:
            raise ValueError("recipient 不可為空清單")
