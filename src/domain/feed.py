"""FeedAssembler: 既存レポートメタ情報から直近 N 件の Feed を組み立てる純粋ロジック。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str
    guid: str
    published_at: datetime
    slug: str = ""  # レポートファイルの識別子（保持ポリシーでの削除に使用）


@dataclass(frozen=True)
class Feed:
    title: str
    link: str
    description: str
    items: list[FeedItem]


def assemble(
    feed_title: str,
    feed_link: str,
    feed_description: str,
    items: list[FeedItem],
    max_items: int = 20,
) -> Feed:
    """公開日時の新しい順に並べ、直近 max_items 件に絞る。"""
    ordered = sorted(items, key=lambda i: i.published_at, reverse=True)
    return Feed(
        title=feed_title,
        link=feed_link,
        description=feed_description,
        items=ordered[:max_items],
    )
