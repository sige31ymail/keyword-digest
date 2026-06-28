"""OpenAI / Anthropic 共通のプロンプト構築と応答パース。

レポートは「要約しすぎず実用的な日本語記事」を、JSON 固定スキーマで生成させる。
PocketDigest の OpenAiEnrichmentClient の JSON スキーマ設計を踏襲。
"""
from __future__ import annotations

import json
import re

from ..domain.keyword import Keyword

SYSTEM_PROMPT = (
    "あなたは日本語のリサーチライターです。与えられたキーワードについて、"
    "最新の動向・背景・要点を整理した読み応えのある日本語レポートを書きます。"
    "事実に忠実に、わかりやすく、過度に短くせず複数段落で構成してください。"
    "宣伝文句・誇張・箇条書きの羅列は避け、自然な文章で記述します。"
    "出力は必ず指定された JSON のみとし、前後に説明やコードフェンスを付けないでください。"
)

OUTPUT_SCHEMA_HINT = (
    '{"title": "一覧用の簡潔な日本語タイトル(40字以内)", '
    '"paragraphs": ["段落1", "段落2", "段落3"]}'
)


def build_user_prompt(keyword: Keyword) -> str:
    note = f"\n補足の観点・指示: {keyword.note}" if keyword.note else ""
    return (
        f"キーワード: {keyword.title}{note}\n\n"
        "このキーワードについて、概要・背景・最近の動き・注目点・今後の見通しを含む"
        "日本語レポートを作成してください。\n"
        "本文は段落の配列で、合計 600〜1200 字程度。各段落は 2〜5 文。\n"
        f"出力フォーマット(JSON): {OUTPUT_SCHEMA_HINT}"
    )


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_response(text: str) -> tuple[str, list[str]]:
    """モデル出力(JSON文字列)から (title, paragraphs) を取り出す。"""
    raw = text.strip()
    # コードフェンスや前後の余分なテキストに耐える
    match = _JSON_BLOCK.search(raw)
    if not match:
        raise ValueError(f"JSON が見つかりません: {raw[:200]}")
    data = json.loads(match.group(0))
    title = str(data.get("title", "")).strip()
    paragraphs_raw = data.get("paragraphs", [])
    if isinstance(paragraphs_raw, str):
        paragraphs = [p for p in re.split(r"\n{2,}", paragraphs_raw) if p.strip()]
    else:
        paragraphs = [str(p).strip() for p in paragraphs_raw if str(p).strip()]
    if not title:
        # タイトルが無ければ最初の段落の冒頭で代替
        title = (paragraphs[0][:40] if paragraphs else "レポート")
    return title, paragraphs
