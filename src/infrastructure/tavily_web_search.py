"""TavilyWebSearch: Tavily Search API による Web 検索（既定バックエンド）。

Tavily は LLM/RAG 向けに設計された検索 API で、1 回の呼び出しで本文抽出済みの
結果と要約（answer）、出典 URL を返す。DeepSeek パイプラインの「検索」段に最適。
API: POST https://api.tavily.com/search
"""
from __future__ import annotations

from ..ports.web_search import SearchError, SearchFinding, WebSearch
from . import _http

_ENDPOINT = "https://api.tavily.com/search"


class TavilyWebSearch(WebSearch):
    def __init__(
        self,
        api_key: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        timeout: int = 60,
    ):
        if not api_key:
            raise ValueError("Tavily API key is required.")
        self._api_key = api_key
        self._max_results = max_results
        self._search_depth = search_depth
        self._timeout = timeout

    def search(self, query: str) -> SearchFinding:
        payload = {
            "query": query,
            "search_depth": self._search_depth,
            "max_results": self._max_results,
            "include_answer": True,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            data = _http.post_json(
                _ENDPOINT, payload, headers, timeout=self._timeout
            )
            return self._to_finding(query, data)
        except Exception as exc:
            raise SearchError(f"Tavily search failed for {query!r}: {exc}") from exc

    @staticmethod
    def _to_finding(query: str, data: dict) -> SearchFinding:
        parts: list[str] = []
        answer = (data.get("answer") or "").strip()
        if answer:
            parts.append(f"要約: {answer}")
        sources: list[tuple[str, str]] = []
        seen: set[str] = set()
        for result in data.get("results") or []:
            url = (result.get("url") or "").strip()
            title = (result.get("title") or url).strip()
            content = (result.get("content") or "").strip()
            if content:
                parts.append(f"- {title}: {content}")
            if url and url not in seen:
                seen.add(url)
                sources.append((title or url, url))
        return SearchFinding(query=query, text="\n".join(parts), sources=sources)
