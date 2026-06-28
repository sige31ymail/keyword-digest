"""ReportContentPolicy: 生成本文が PocketDigest の抽出可能性を満たすか検証する。

PocketDigest の SimpleArticleTextExtractor は最小 120 文字を要求するため、
余裕を持って既定 200 文字以上・段落 1 つ以上を必須とする。
"""
from __future__ import annotations

MIN_BODY_CHARS = 200


class ContentPolicyError(ValueError):
    """抽出可能性を満たさない本文。"""


def validate(paragraphs: list[str]) -> list[str]:
    cleaned = [p.strip() for p in paragraphs if p and p.strip()]
    if not cleaned:
        raise ContentPolicyError("Report body has no paragraphs.")
    total = sum(len(p) for p in cleaned)
    if total < MIN_BODY_CHARS:
        raise ContentPolicyError(
            f"Report body too short: {total} chars (< {MIN_BODY_CHARS})."
        )
    return cleaned
