"""AnthropicReportGenerator: Anthropic Messages API でレポート生成（フォールバック）。"""
from __future__ import annotations

from ..domain.keyword import Keyword
from ..domain.report import Report
from ..ports.report_generator import GenerationError, ReportGenerator
from . import _ai_prompt, _http

_ENDPOINT = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class AnthropicReportGenerator(ReportGenerator):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5"):
        if not api_key:
            raise ValueError("Anthropic API key is required.")
        self._api_key = api_key
        self._model = model

    def generate(self, keyword: Keyword) -> Report:
        payload = {
            "model": self._model,
            "max_tokens": 2000,
            "system": _ai_prompt.SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": _ai_prompt.build_user_prompt(keyword)}
            ],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
        }
        try:
            data = _http.post_json(_ENDPOINT, payload, headers, timeout=180)
            text = data["content"][0]["text"]
            title, paragraphs = _ai_prompt.parse_response(text)
            return Report(
                keyword=keyword,
                title=title,
                paragraphs=paragraphs,
                generated_by=self.name,
            )
        except Exception as exc:
            raise GenerationError(f"Anthropic generation failed: {exc}") from exc
