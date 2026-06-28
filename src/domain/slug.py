"""ReportSlugFactory: (date, keyword) -> URL 安全な slug。

日本語キーワードは ASCII 化が難しいため、ASCII 部分を抽出しつつ末尾に
キーワードの md5 ハッシュ先頭 8 文字を付与して一意性と安定性を担保する。
同一キーワード・同一日付なら必ず同じ slug になる（再実行で上書きされる）。
"""
from __future__ import annotations

import hashlib
import re
from datetime import date

from .keyword import Keyword

_ASCII_SAFE = re.compile(r"[^a-z0-9]+")


def _ascii_part(text: str) -> str:
    lowered = text.lower()
    # ASCII 英数字以外をハイフンに畳み込む
    slug = _ASCII_SAFE.sub("-", lowered).strip("-")
    # 長すぎる場合は短縮
    return slug[:40].strip("-")


def make_slug(on: date, keyword: Keyword) -> str:
    """例: 20260628-generative-ai-1a2b3c4d / 20260628-kw-1a2b3c4d（日本語のみ時）"""
    digest = hashlib.md5(keyword.title.encode("utf-8")).hexdigest()[:8]
    ascii_part = _ascii_part(keyword.title) or "kw"
    return f"{on:%Y%m%d}-{ascii_part}-{digest}"
