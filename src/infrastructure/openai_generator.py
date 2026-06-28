"""OpenAiReportGenerator: OpenAI でレポート生成。

web_search=True のときは Responses API（/v1/responses）の web_search ツールを使い、
最新の Web 情報に基づいて生成し、出典 URL を本文末尾に付与する（案A）。
web_search=False のときは従来の Chat Completions（モデル知識のみ）にフォールバック。
"""
from __future__ import annotations

from ..domain.keyword import Keyword
from ..domain.report import Report
from ..ports.report_generator import GenerationError, ReportGenerator
from . import _ai_prompt, _http

_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"


def _extract_text_and_sources(data: dict) -> tuple[str, list[tuple[str, str]]]:
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


class OpenAiReportGenerator(ReportGenerator):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        web_search: bool = True,
        search_context_size: str = "medium",
    ):
        if not api_key:
            raise ValueError("OpenAI API key is required.")
        self._api_key = api_key
        self._model = model
        self._web_search = web_search
        self._search_context_size = search_context_size

    def generate(self, keyword: Keyword) -> Report:
        if self._web_search:
            return self._generate_with_web_search(keyword)
        return self._generate_from_knowledge(keyword)

    def _generate_with_web_search(self, keyword: Keyword) -> Report:
        payload = {
            "model": self._model,
            "instructions": _ai_prompt.SYSTEM_PROMPT,
            "input": _ai_prompt.build_user_prompt(keyword),
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
                _RESPONSES_ENDPOINT, payload, headers, timeout=240
            )
            text, sources = _extract_text_and_sources(data)
            title, paragraphs = _ai_prompt.parse_response(text)
            if sources:
                cited = " / ".join(f"{t}（{u}）" for t, u in sources[:5])
                paragraphs = paragraphs + [f"出典: {cited}"]
            return Report(
                keyword=keyword,
                title=title,
                paragraphs=paragraphs,
                generated_by=self.name,
            )
        except Exception as exc:
            raise GenerationError(
                f"OpenAI(web_search) generation failed: {exc}"
            ) from exc

    def _generate_from_knowledge(self, keyword: Keyword) -> Report:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _ai_prompt.SYSTEM_PROMPT},
                {"role": "user", "content": _ai_prompt.build_user_prompt(keyword)},
            ],
            "temperature": 0.6,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            data = _http.post_json(_CHAT_ENDPOINT, payload, headers, timeout=120)
            text = data["choices"][0]["message"]["content"]
            title, paragraphs = _ai_prompt.parse_response(text)
            return Report(
                keyword=keyword,
                title=title,
                paragraphs=paragraphs,
                generated_by=self.name,
            )
        except Exception as exc:
            raise GenerationError(f"OpenAI generation failed: {exc}") from exc
