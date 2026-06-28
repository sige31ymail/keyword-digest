"""SitePublisher ポート: レポート HTML と RSS フィードを書き出す。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.feed import Feed, FeedItem
from ..domain.report import Report


class SitePublisher(ABC):
    @abstractmethod
    def write_report_page(self, report: Report) -> FeedItem:
        """レポートを HTML ページとして書き出し、フィード項目を返す。"""
        raise NotImplementedError

    @abstractmethod
    def list_existing_items(self) -> list[FeedItem]:
        """既に書き出し済みのレポートをフィード項目として走査する。"""
        raise NotImplementedError

    @abstractmethod
    def write_feed(self, feed: Feed) -> None:
        """RSS フィード（feed.xml）と一覧（index.html）を書き出す。"""
        raise NotImplementedError
