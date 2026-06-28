"""OpenAiReportGenerator: OpenAI Chat Completions でレポート生成。"""
from __future__ import annotations

from ..domain.keyword import Keyword
from ..domain.report import Report
from ..ports.report_generator import GenerationError, ReportGenerator
from . import _ai_prompt, _http

_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class OpenAiReportGenerator(ReportGenerator):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("OpenAI API key is required.")
        self._api_key = api_key
        self._model = model

    def generate(self, keyword: Keyword) -> Report:
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
            data = _http.post_json(_ENDPOINT, payload, headers, timeout=120)
            text = data["choices"][0]["message"]["content"]
            title, paragraphs = _ai_prompt.parse_response(text)
            return Report(
                keyword=keyword,
                title=title,
                paragraphs=paragraphs,
                generated_by=self.name,
            )
        except Exception as exc:  # API/パース/内容不足をまとめて生成失敗に
            raise GenerationError(f"OpenAI generation failed: {exc}") from exc
