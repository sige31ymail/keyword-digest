"""DeepSeekPipelineReportGenerator: DeepSeek による多段レポート生成（主ジェネレータ）。

DeepSeek（api.deepseek.com / OpenAI 互換 chat）を使い、以下の5段階で高品質な
日本語レポートを生成する。検索だけは DeepSeek に機能がないため WebSearch ポートへ委譲。

  1. クエリ生成        … キーワードから Web 検索クエリを作る
  2. 検索＋選別・要約  … WebSearch で事実と出典を集め、DeepSeek が選別・要約
  3. 論点整理・記事構成 … タイトルとアウトライン
  4. 本文生成          … 段落本文
  5. ファクトチェック  … 事実と照合して修正

各段の失敗は例外として送出し、上位の FallbackReportGenerator が副ジェネレータ
（Anthropic）へ切り替える。
"""
from __future__ import annotations

import sys

from ..domain.keyword import Keyword
from ..domain.report import Report
from ..ports.report_generator import GenerationError, ReportGenerator
from ..ports.web_search import SearchError, SearchFinding, WebSearch
from . import _http, _pipeline_prompts as P

_DEFAULT_BASE_URL = "https://api.deepseek.com"


def _merge_sources(findings: list[SearchFinding]) -> list[tuple[str, str]]:
    """検索結果群の出典を URL で重複排除して結合する。"""
    merged: list[tuple[str, str]] = []
    seen: set[str] = set()
    for finding in findings:
        for label, url in finding.sources:
            if url and url not in seen:
                seen.add(url)
                merged.append((label, url))
    return merged


def _append_sources(
    paragraphs: list[str], sources: list[tuple[str, str]]
) -> list[str]:
    """本文末尾に出典段落を付与する（既に出典がある場合は何もしない）。"""
    if not sources:
        return paragraphs
    if any(p.startswith(("出典", "参考", "参照")) for p in paragraphs):
        return paragraphs
    cited = " / ".join(f"{t}（{u}）" for t, u in sources[:6])
    return paragraphs + [f"出典: {cited}"]


class DeepSeekPipelineReportGenerator(ReportGenerator):
    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        web_search: WebSearch,
        model: str = "deepseek-v4-pro",
        base_url: str = _DEFAULT_BASE_URL,
        max_search_queries: int = 3,
        timeout: int = 180,
    ):
        if not api_key:
            raise ValueError("DeepSeek API key is required.")
        self._api_key = api_key
        self._web_search = web_search
        self._model = model
        self._endpoint = base_url.rstrip("/") + "/chat/completions"
        self._max_search_queries = max(1, max_search_queries)
        self._timeout = timeout

    # --- DeepSeek chat 呼び出し ------------------------------------------
    def _chat(self, user_prompt: str, *, max_tokens: int = 4000) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": P.RESEARCHER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        data = _http.post_json(
            self._endpoint, payload, headers, timeout=self._timeout
        )
        return data["choices"][0]["message"]["content"]

    # --- 各段 -------------------------------------------------------------
    def _stage_queries(self, keyword: Keyword) -> list[str]:
        text = self._chat(
            P.build_query_prompt(keyword, self._max_search_queries),
            max_tokens=500,
        )
        return P.parse_queries(text, keyword.title, self._max_search_queries)

    def _stage_search(self, queries: list[str]) -> list[SearchFinding]:
        findings: list[SearchFinding] = []
        for query in queries:
            try:
                finding = self._web_search.search(query)
                if finding.text.strip():
                    findings.append(finding)
            except SearchError as exc:
                print(f"  [search] スキップ: {exc}", file=sys.stderr)
        if not findings:
            raise GenerationError("Web 検索から有効な結果が得られませんでした。")
        return findings

    def _stage_summarize(
        self, keyword: Keyword, findings: list[SearchFinding]
    ) -> tuple[list[str], str]:
        block = "\n\n".join(
            f"[クエリ: {f.query}]\n{f.text}" for f in findings
        )
        text = self._chat(P.build_summarize_prompt(keyword, block))
        facts, brief = P.parse_facts(text)
        if not facts:  # 要約失敗時は検索本文をそのまま素材にする
            facts = [f.text for f in findings if f.text.strip()]
            brief = brief or (facts[0][:200] if facts else "")
        return facts, brief

    def _stage_outline(
        self, keyword: Keyword, facts: list[str], brief: str
    ) -> str:
        text = self._chat(P.build_outline_prompt(keyword, facts, brief))
        title, sections = P.parse_outline(text)
        return P.format_outline(title, sections)

    def _stage_body(
        self, keyword: Keyword, outline_block: str, facts: list[str]
    ) -> tuple[str, list[str]]:
        text = self._chat(P.build_body_prompt(keyword, outline_block, facts))
        return P.parse_title_paragraphs(text)

    def _stage_factcheck(
        self, title: str, paragraphs: list[str], facts: list[str]
    ) -> tuple[str, list[str]]:
        text = self._chat(P.build_factcheck_prompt(title, paragraphs, facts))
        try:
            new_title, new_paras = P.parse_title_paragraphs(text)
        except ValueError:
            return title, paragraphs
        # ファクトチェックで本文が痩せすぎた場合は草稿を採用（抽出可能性を守る）
        if sum(len(p) for p in new_paras) < 200:
            return title, paragraphs
        return (new_title or title), new_paras

    # --- 公開 API ---------------------------------------------------------
    def generate(self, keyword: Keyword) -> Report:
        try:
            queries = self._stage_queries(keyword)
            findings = self._stage_search(queries)
            sources = _merge_sources(findings)
            facts, brief = self._stage_summarize(keyword, findings)
            outline_block = self._stage_outline(keyword, facts, brief)
            draft_title, draft_paras = self._stage_body(
                keyword, outline_block, facts
            )
            title, paragraphs = self._stage_factcheck(
                draft_title, draft_paras, facts
            )
            paragraphs = _append_sources(paragraphs, sources)
            return Report(
                keyword=keyword,
                title=title,
                paragraphs=paragraphs,
                generated_by=self.name,
            )
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError(f"DeepSeek pipeline generation failed: {exc}") from exc
