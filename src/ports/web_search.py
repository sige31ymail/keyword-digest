"""WebSearch ポート: クエリから Web 検索の事実と出典を得る。

DeepSeek の API には組み込み Web 検索がないため、検索は本ポートに分離する。
現状の実装は OpenAI Responses API の web_search ツール（OpenAiWebSearch）。
将来 SerpApi / Tavily / Brave などへ差し替え可能なように抽象化している。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class SearchError(RuntimeError):
    """Web 検索に失敗した（API エラーなど）。"""


@dataclass(frozen=True)
class SearchFinding:
    """1 クエリの検索結果。

    text    … 検索で判明した事実をまとめた説明テキスト。
    sources … (title, url) の一覧。本文の出典付与に用いる。
    """

    query: str
    text: str
    sources: list[tuple[str, str]] = field(default_factory=list)


class WebSearch(ABC):
    @abstractmethod
    def search(self, query: str) -> SearchFinding:
        """1 つの検索クエリを実行し、事実と出典を返す。失敗時は SearchError。"""
        raise NotImplementedError
