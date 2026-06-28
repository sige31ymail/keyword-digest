"""キーワード（値オブジェクト）。GitHub Issue 由来。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Keyword:
    """利用者が関心を持つテーマ。Issue タイトル=title、Issue 本文=note。"""

    title: str
    note: str = ""
    issue_number: int | None = None

    def __post_init__(self) -> None:
        stripped = self.title.strip()
        if not stripped:
            raise ValueError("Keyword title must not be blank.")
        # frozen dataclass なので object.__setattr__ で正規化を反映
        object.__setattr__(self, "title", stripped)
        object.__setattr__(self, "note", self.note.strip())
