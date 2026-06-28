"""ReportRetentionPolicy: 期間+件数の併用で保持/削除を判定するドメインサービス。

PocketDigest の PruneOfflineLibraryUseCase（期限/件数ベース整理）と対称。
- 期間: max_age_days より古いレポートは削除対象。
- 件数: 新しい順に max_count を超えたレポートは削除対象。
いずれか一方でも条件に触れたら削除（=より厳しい側で上限が決まる）。

フィードに載せる件数（max_feed_items）より保持件数を必ず多くするため、
max_count は呼び出し側で max(max_count, max_feed_items) に補正して渡す想定。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .feed import FeedItem


@dataclass(frozen=True)
class RetentionResult:
    keep: list[FeedItem]
    remove: list[FeedItem]


def partition(
    items: list[FeedItem],
    now: datetime,
    max_age_days: int,
    max_count: int,
) -> RetentionResult:
    ordered = sorted(items, key=lambda i: i.published_at, reverse=True)
    cutoff = now - timedelta(days=max_age_days)
    keep: list[FeedItem] = []
    remove: list[FeedItem] = []
    for index, item in enumerate(ordered):
        too_old = item.published_at < cutoff
        over_count = index >= max_count
        if too_old or over_count:
            remove.append(item)
        else:
            keep.append(item)
    return RetentionResult(keep=keep, remove=remove)
