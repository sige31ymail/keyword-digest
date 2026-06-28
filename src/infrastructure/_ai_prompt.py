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

SYSTEM_PROMPT_PLAIN = (
    "あなたは日本語のリサーチライターです。与えられたキーワードについて、"
    "最新の動向・背景・要点を整理した読み応えのある日本語レポートを書きます。"
    "事実に忠実に、わかりやすく、過度に短くせず複数段落で構成してください。"
    "宣伝文句・誇張・箇条書きの羅列は避け、自然な文章で記述します。"
    "指定された出力形式（1行目タイトル＋空行区切りの本文）に従ってください。"
)

OUTPUT_SCHEMA_HINT = (
    '{"title": "一覧用の簡潔な日本語タイトル(40字以内)", '
    '"paragraphs": ["段落1", "段落2", "段落3"]}'
)


def build_user_prompt(keyword: Keyword) -> str:
    """JSON 出力用プロンプト（Chat Completions / Anthropic 用。response_format で強制）。"""
    note = f"\n補足の観点・指示: {keyword.note}" if keyword.note else ""
    return (
        f"キーワード: {keyword.title}{note}\n\n"
        "このキーワードについて、概要・背景・最近の動き・注目点・今後の見通しを含む"
        "日本語レポートを作成してください。\n"
        "本文は段落の配列で、合計 600〜1200 字程度。各段落は 2〜5 文。\n"
        f"出力フォーマット(JSON): {OUTPUT_SCHEMA_HINT}"
    )


def build_user_prompt_plain(keyword: Keyword) -> str:
    """プレーンテキスト出力用プロンプト（Web 検索モデル用。JSON は壊れやすいため不使用）。"""
    note = f"\n補足の観点・指示: {keyword.note}" if keyword.note else ""
    return (
        f"キーワード: {keyword.title}{note}\n\n"
        "Web 検索で最新情報を確認し、判明した事実（時期・数値・固有名詞）に基づく"
        "日本語レポートを書いてください。可能なら年月などの時点を本文に明記します。\n"
        "概要・背景・最近の動き・注目点・今後の見通しを含めてください。\n\n"
        "出力形式（JSON にしないでください）:\n"
        "・1行目: 簡潔な日本語タイトル（40字以内。記号や見出し記法 # は付けない）\n"
        "・2行目以降: 本文を段落ごとに空行で区切って記述（合計600〜1200字、各段落2〜5文）\n"
        "・Web 検索で参照した情報には、該当箇所に出典 URL を Markdown リンクで併記して"
        "ください（例: 〜と報じられている([出典](https://example.com/article)) ）。"
    )


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _normalize_paragraph(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


# Web 検索モデルが本文に埋め込むインライン引用 `([ラベル](URL))` / `[ラベル](URL)`
_MD_LINK = re.compile(r"\(?\[([^\]]+)\]\((https?://[^)\s]+)\)\)?")


def strip_and_collect_links(
    paragraphs: list[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """段落からインライン引用リンクを除去し、出典(label,url)一覧を集める。"""
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    cleaned: list[str] = []
    for para in paragraphs:
        def _repl(m: re.Match) -> str:
            label, url = m.group(1).strip(), m.group(2).strip()
            if url not in seen:
                seen.add(url)
                sources.append((label, url))
            return ""

        new_para = _MD_LINK.sub(_repl, para)
        new_para = re.sub(r"\s+", " ", new_para)
        # 句読点・閉じ括弧の前の余分な空白を詰める
        new_para = re.sub(r"\s+([。、，．）)」』】])", r"\1", new_para).strip()
        if new_para:
            cleaned.append(new_para)
    if not cleaned:  # 全段落がリンクのみだった場合の保険
        cleaned = [p for p in paragraphs if p.strip()]
    return cleaned, sources


def parse_response(text: str) -> tuple[str, list[str]]:
    """JSON 文字列から (title, paragraphs) を取り出す。"""
    raw = text.strip()
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
        title = paragraphs[0][:40] if paragraphs else "レポート"
    return title, paragraphs


def parse_plain(text: str) -> tuple[str, list[str]]:
    """プレーンテキスト（1行目タイトル + 空行区切り本文）を堅牢に解釈する。

    Web 検索モデルの自由形式出力でも壊れないよう、JSON でもプレーンでも拾う。
    """
    raw = text.strip()
    # 念のため JSON で来たら従来パースを試す
    if raw.startswith("{"):
        try:
            return parse_response(raw)
        except Exception:
            pass
    # コードフェンス除去
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw).strip()

    lines = raw.split("\n")
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    title_line = lines[idx].strip() if idx < len(lines) else "レポート"
    title = re.sub(r"^#+\s*", "", title_line)
    title = re.sub(r"^(タイトル|見出し)\s*[:：]\s*", "", title)
    title = title.strip().strip("“”\"'　 ")[:60] or "レポート"

    body = "\n".join(lines[idx + 1:]).strip()
    body_lines = [l.strip() for l in lines[idx + 1:] if l.strip()]
    chunks = [c for c in re.split(r"\n\s*\n", body) if c.strip()]
    if len(chunks) >= 2:  # 空行区切り（指定どおり）
        paragraphs = [_normalize_paragraph(c) for c in chunks]
    elif len(body_lines) >= 2:  # 空行なし・複数行 → 行ごとに段落化
        paragraphs = [_normalize_paragraph(l) for l in body_lines]
    elif body_lines:  # 本文1行のみ
        paragraphs = [_normalize_paragraph(body)]
    else:  # 本文が取れない → 全体を1段落に救済
        paragraphs = [_normalize_paragraph(raw)]
        title = title if title != "レポート" else paragraphs[0][:40]
    return title, paragraphs
