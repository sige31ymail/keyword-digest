"""DeepSeek 5段階パイプラインのプロンプトと JSON パース。

段階: (1)クエリ生成 →(2)検索結果の選別・要約 →(3)論点整理・記事構成
      →(4)本文生成 →(5)ファクトチェック。
各段は DeepSeek に JSON 出力させる（response_format=json_object）。検索のみ別ポート。
"""
from __future__ import annotations

import json
import re

from ..domain.keyword import Keyword

# 全段共通の記者（ジャーナリスト）人格。多角的・深掘り・事実忠実を一貫させる。
RESEARCHER_SYSTEM = (
    "あなたは経験豊富な日本語のジャーナリストです。単なる事実の要約ではなく、"
    "読者が最後まで読み進めたくなる、深掘りされた多角的な Web 記事を書きます。"
    "具体的な数値・時期・固有名詞・経緯・具体例を盛り込み、関係する複数の立場や論点"
    "（推進派と慎重派、技術・経済・社会・規制・国際比較など）をバランスよく扱い、"
    "背景と意味合いを丁寧に説明します。誇張・宣伝文句・空疎な一般論・箇条書きの羅列は"
    "避け、自然で読み応えのある記事文体で書きます。"
    "指示された JSON 形式のみを出力し、前後に説明やコードフェンスを付けません。"
)


def _note_line(keyword: Keyword) -> str:
    return f"\n補足の観点・指示: {keyword.note}" if keyword.note else ""


# --- 段階1: 検索クエリ生成 -------------------------------------------------
def build_query_prompt(keyword: Keyword, max_queries: int) -> str:
    return (
        f"キーワード: {keyword.title}{_note_line(keyword)}\n\n"
        "このテーマを多角的に深掘りした記事を書くための Web 検索クエリを考えてください。"
        "技術・市場/経済・規制/政策・社会的影響・関係者の賛否や対立・国際比較・"
        "直近の具体的な出来事や数値など、異なる観点を意識し、重複しない切り口で"
        f"最大 {max_queries} 件。必要に応じ日本語と英語を混ぜます。\n"
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
        "次の事実群をもとに、読み応えのある日本語の Web 記事の構成を作ってください。"
        "「導入(リード)→背景・経緯→現状の最新動向→複数の視点・論点(賛否や利害の"
        "対立を含む)→影響と意味合い→今後の見通し」といった流れで、5〜7 個の見出しに"
        "整理します。各見出しに盛り込むべき具体的な論点・事実を箇条書きで示してください。\n\n"
        f"=== 事実 ===\n{facts_block}\n=== ここまで ===\n\n"
        'JSON 形式: {"title": "読者の関心を引く記事タイトル(40字以内)", '
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
    keyword: Keyword,
    outline_block: str,
    facts: list[str],
    min_chars: int = 1800,
    max_chars: int = 3000,
) -> str:
    facts_block = "\n".join(f"- {f}" for f in facts) or "(事実情報なし)"
    return (
        f"キーワード: {keyword.title}{_note_line(keyword)}\n\n"
        "次の構成と事実に基づき、経験豊富な記者として日本語の Web 記事を執筆してください。\n"
        f"・本文は段落の配列。合計 {min_chars}〜{max_chars} 字程度、6〜9 段落、"
        "各段落 3〜6 文の読み応えのある分量にする。\n"
        "・冒頭に読者の関心を引くリード文を置き、背景・経緯 → 最新動向 → 複数の立場や"
        "論点（賛否・利害の対立）→ 影響と意味合い → 今後の見通し、へと展開する。\n"
        "・判明している時期・数値・固有名詞・具体例を積極的に盛り込み、抽象的な一般論で"
        "字数を埋めない。一つの視点に偏らず、見解が分かれる点は両論を示す。\n"
        "・誇張・宣伝・箇条書きの羅列を避け、自然な記事文体にする。"
        "出典 URL は本文に書かず、内容のみを書く。\n\n"
        f"=== 構成 ===\n{outline_block}\n\n"
        f"=== 事実 ===\n{facts_block}\n=== ここまで ===\n\n"
        'JSON 形式: {"title": "読者の関心を引く記事タイトル(40字以内)", '
        '"paragraphs": ["段落1", "段落2", "段落3"]}'
    )


# --- 段階5: ファクトチェック -----------------------------------------------
def build_factcheck_prompt(
    title: str, paragraphs: list[str], facts: list[str]
) -> str:
    body_block = "\n\n".join(paragraphs)
    facts_block = "\n".join(f"- {f}" for f in facts) or "(事実情報なし)"
    return (
        "以下の記事草稿を、提示された事実と照合してください。事実で裏付けられない"
        "主張・数値・固有名詞は削除するか表現を弱め、誤りがあれば修正します。"
        "ただし裏付けのある内容は削らず、記事の情報量・多角的な視点・段落構成・"
        "読み応えと分量は維持してください（不必要に短くしないこと）。\n\n"
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
