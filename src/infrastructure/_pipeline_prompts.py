"""DeepSeek 5段階パイプラインのプロンプトと JSON パース。

段階: (1)クエリ生成 →(2)検索結果の選別・要約 →(3)論点整理・記事構成
      →(4)本文生成 →(5)ファクトチェック。
各段は DeepSeek に JSON 出力させる（response_format=json_object）。検索のみ別ポート。
"""
from __future__ import annotations

import json
import re

from ..domain.keyword import Keyword

# 全段共通のリサーチャー人格。事実忠実・誇張排除を一貫させる。
RESEARCHER_SYSTEM = (
    "あなたは日本語の優秀なリサーチライターです。事実に忠実で、誇張・宣伝文句・"
    "箇条書きの羅列を避け、読み応えのある自然な文章を書きます。"
    "指示された JSON 形式のみを出力し、前後に説明やコードフェンスを付けません。"
)


def _note_line(keyword: Keyword) -> str:
    return f"\n補足の観点・指示: {keyword.note}" if keyword.note else ""


# --- 段階1: 検索クエリ生成 -------------------------------------------------
def build_query_prompt(keyword: Keyword, max_queries: int) -> str:
    return (
        f"キーワード: {keyword.title}{_note_line(keyword)}\n\n"
        "このテーマの最新動向・背景・要点を網羅的に調べるための Web 検索クエリを"
        f"考えてください。観点が重複しないよう異なる切り口で最大 {max_queries} 件。"
        "必要に応じ日本語と英語を混ぜます。\n"
        'JSON 形式: {"queries": ["クエリ1", "クエリ2"]}'
    )


def parse_queries(text: str, fallback: str, max_queries: int) -> list[str]:
    data = loads_json(text)
    raw = data.get("queries") if isinstance(data, dict) else None
    queries = [str(q).strip() for q in raw or [] if str(q).strip()]
    if not queries:
        queries = [fallback]
    return queries[:max_queries]


# --- 段階2: 検索結果の選別・要約 -------------------------------------------
def build_summarize_prompt(keyword: Keyword, findings_block: str) -> str:
    return (
        f"キーワード: {keyword.title}{_note_line(keyword)}\n\n"
        "以下は複数の Web 検索結果です。記事の素材として信頼できる重要な事実だけを"
        "選別し、重複や推測を除いて整理してください。時期（年月）・数値・固有名詞は"
        "省かずに残します。\n\n"
        f"=== 検索結果 ===\n{findings_block}\n=== ここまで ===\n\n"
        'JSON 形式: {"key_facts": ["事実1", "事実2"], "brief": "全体の要約(200字程度)"}'
    )


def parse_facts(text: str) -> tuple[list[str], str]:
    data = loads_json(text)
    facts_raw = data.get("key_facts") if isinstance(data, dict) else None
    facts = [str(f).strip() for f in facts_raw or [] if str(f).strip()]
    brief = str(data.get("brief", "")).strip() if isinstance(data, dict) else ""
    return facts, brief


# --- 段階3: 論点整理・記事構成 ---------------------------------------------
def build_outline_prompt(keyword: Keyword, facts: list[str], brief: str) -> str:
    facts_block = "\n".join(f"- {f}" for f in facts) or "(事実情報なし)"
    return (
        f"キーワード: {keyword.title}{_note_line(keyword)}\n\n"
        f"全体要約: {brief or '(なし)'}\n\n"
        "次の事実群をもとに、日本語レポートの論点を整理し記事構成を作ってください。"
        "概要・背景・最近の動き・注目点・今後の見通しといった流れを意識します。\n\n"
        f"=== 事実 ===\n{facts_block}\n=== ここまで ===\n\n"
        'JSON 形式: {"title": "簡潔なタイトル(40字以内)", '
        '"sections": [{"heading": "見出し", "points": ["論点1", "論点2"]}]}'
    )


def parse_outline(text: str) -> tuple[str, list[dict]]:
    data = loads_json(text)
    if not isinstance(data, dict):
        return "", []
    title = str(data.get("title", "")).strip()
    sections_raw = data.get("sections") or []
    sections: list[dict] = []
    for sec in sections_raw:
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading", "")).strip()
        points = [str(p).strip() for p in sec.get("points", []) if str(p).strip()]
        if heading or points:
            sections.append({"heading": heading, "points": points})
    return title, sections


def format_outline(title: str, sections: list[dict]) -> str:
    lines = [f"タイトル案: {title}"] if title else []
    for sec in sections:
        lines.append(f"■ {sec['heading']}")
        lines.extend(f"  - {p}" for p in sec["points"])
    return "\n".join(lines)


# --- 段階4: 本文生成 -------------------------------------------------------
def build_body_prompt(
    keyword: Keyword, outline_block: str, facts: list[str]
) -> str:
    facts_block = "\n".join(f"- {f}" for f in facts) or "(事実情報なし)"
    return (
        f"キーワード: {keyword.title}{_note_line(keyword)}\n\n"
        "次の構成と事実に基づいて、日本語レポートの本文を執筆してください。\n"
        "本文は段落の配列で、合計 600〜1200 字程度、各段落 2〜5 文。事実に忠実に、"
        "判明している時期・数値・固有名詞は本文に織り込みます。出典 URL は本文には"
        "書かず、内容のみを書いてください。\n\n"
        f"=== 構成 ===\n{outline_block}\n\n"
        f"=== 事実 ===\n{facts_block}\n=== ここまで ===\n\n"
        'JSON 形式: {"title": "簡潔なタイトル(40字以内)", '
        '"paragraphs": ["段落1", "段落2", "段落3"]}'
    )


# --- 段階5: ファクトチェック -----------------------------------------------
def build_factcheck_prompt(
    title: str, paragraphs: list[str], facts: list[str]
) -> str:
    body_block = "\n\n".join(paragraphs)
    facts_block = "\n".join(f"- {f}" for f in facts) or "(事実情報なし)"
    return (
        "以下のレポート草稿を、提示された事実と照合してください。事実で裏付けられない"
        "主張・数値・固有名詞は削除するか表現を弱め、誤りがあれば修正します。文章の"
        "自然さと読みやすさは保ち、過度に短くしないでください。\n\n"
        f"=== 草稿タイトル ===\n{title}\n\n"
        f"=== 草稿本文 ===\n{body_block}\n\n"
        f"=== 裏付けに使える事実 ===\n{facts_block}\n=== ここまで ===\n\n"
        'JSON 形式: {"title": "確定タイトル(40字以内)", '
        '"paragraphs": ["段落1", "段落2"]}'
    )


def parse_title_paragraphs(text: str) -> tuple[str, list[str]]:
    """{"title", "paragraphs"} を堅牢に取り出す（段階4・5共通）。"""
    data = loads_json(text)
    if not isinstance(data, dict):
        raise ValueError(f"JSON が見つかりません: {text[:200]}")
    title = str(data.get("title", "")).strip()
    paragraphs_raw = data.get("paragraphs", [])
    if isinstance(paragraphs_raw, str):
        paragraphs = [p for p in re.split(r"\n{2,}", paragraphs_raw) if p.strip()]
    else:
        paragraphs = [str(p).strip() for p in paragraphs_raw if str(p).strip()]
    if not title:
        title = paragraphs[0][:40] if paragraphs else "レポート"
    return title, paragraphs


# --- 共通: JSON ローダ -----------------------------------------------------
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def loads_json(text: str) -> dict:
    """応答文字列から JSON オブジェクトを取り出す。失敗時は空 dict。"""
    raw = (text or "").strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = _JSON_BLOCK.search(raw)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}
    return {}
