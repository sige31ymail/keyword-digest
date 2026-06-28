"""FallbackReportGenerator: 主ジェネレータ失敗時に副へ切り替える。

PocketDigest の FallbackAiEnrichmentClient と同思想。
"""
from __future__ import annotations

import sys

from ..domain.keyword import Keyword
from ..domain.report import Report
from ..ports.report_generator import GenerationError, ReportGenerator


class FallbackReportGenerator(ReportGenerator):
    def __init__(self, primary: ReportGenerator, secondary: ReportGenerator | None):
        self._primary = primary
        self._secondary = secondary

    def generate(self, keyword: Keyword) -> Report:
        try:
            return self._primary.generate(keyword)
        except GenerationError as primary_exc:
            if self._secondary is None:
                raise
            print(
                f"  [fallback] primary 失敗のため secondary を試行: {primary_exc}",
                file=sys.stderr,
            )
            try:
                return self._secondary.generate(keyword)
            except GenerationError as secondary_exc:
                raise GenerationError(
                    f"primary と secondary の両方が失敗: "
                    f"{primary_exc} / {secondary_exc}"
                ) from secondary_exc
