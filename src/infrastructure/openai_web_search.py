"""OpenAiWebSearch: OpenAI Responses API の web_search ツールで Web 検索を行う。

DeepSeek パイプラインの「検索」段で使う。与えられたクエリについて Web を調べ、
判明した事実テキストと url_citation（出典）を回収して返す。本文の執筆・推論は
DeepSeek 側が担うため、ここではモデルに「事実と出典の報告」だけをさせる。
"""
from __future__ import annotations

from ..ports.web_search import SearchError, SearchFinding, WebSearch
from . import _http

_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"

_SEARCH_INSTRUCTION = (
    "あなたは日本語のリサーチアシスタントです。指定されたトピックについて Web を検索し、"
    "判明した事実のみを簡潔に報告してください。意見・推測・宣伝は含めません。"
    "時期（年月）・数値・固有名詞をできるだけ明記し、各事実の根拠となる出典 URL を"
    "本文中に併記してください。"
)


def extract_text_and_sources(data: dict) -> tuple[str, list[tuple[str, str]]]:
    """Responses API 応答から最終テキストと出典(title,url)一覧を取り出す。"""
    text = data.get("output_text") or ""
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in data.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if content.get("type") != "output_text":
                continue
            if not text:
                text = content.get("text", "")
            for ann in content.get("annotations", []) or []:
                if ann.get("type") == "url_citation":
                    url = ann.get("url")
                    if url and url not in seen:
                        seen.add(url)
                        sources.append((ann.get("title") or url, url))
    return text, sources


class OpenAiWebSearch(WebSearch):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        search_context_size: str = "medium",
        timeout: int = 240,
    ):
        if not api_key:
            raise ValueError("OpenAI API key is required for web search.")
        self._api_key = api_key
        self._model = model
        self._search_context_size = search_context_size
        self._timeout = timeout

    def search(self, query: str) -> SearchFinding:
        payload = {
            "model": self._model,
            "instructions": _SEARCH_INSTRUCTION,
            "input": (
                f"次のトピックについて Web を検索し、最新の事実と出典を報告してください:\n{query}"
            ),
            "tools": [
                {
                    "type": "web_search",
                    "search_context_size": self._search_context_size,
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            data = _http.post_json(
                _RESPONSES_ENDPOINT, payload, headers, timeout=self._timeout
            )
            text, sources = extract_text_and_sources(data)
            return SearchFinding(query=query, text=text, sources=sources)
        except Exception as exc:
            raise SearchError(f"OpenAI web_search failed for {query!r}: {exc}") from exc
