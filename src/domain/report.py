"""Report（集約ルート）と関連値オブジェクト。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from . import content_policy
from .keyword import Keyword
from .slug import make_slug


@dataclass(frozen=True)
class Report:
    """あるキーワードについて AI が生成した日本語レポート。"""

    keyword: Keyword
    title: str
    paragraphs: list[str]
    generated_by: str  # "openai" | "anthropic"
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    on: date = field(default_factory=lambda: datetime.now(timezone.utc).date())

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Report title must not be blank.")
        # 抽出可能性を満たすことを集約の不変条件として強制
        cleaned = content_policy.validate(self.paragraphs)
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "paragraphs", cleaned)

    @property
    def slug(self) -> str:
        return make_slug(self.on, self.keyword)

    @property
    def body_char_count(self) -> int:
        return sum(len(p) for p in self.paragraphs)
