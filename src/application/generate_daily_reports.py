"""GenerateDailyReportsUseCase: 中核ユースケース。

Open Issue（キーワード）を取得し、各キーワードのレポートを生成して HTML 化、
直近 N 件で RSS フィードを再構築する。1 件の失敗は全体に波及させない。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from ..domain import feed as feed_module
from ..ports.keyword_source import KeywordSource
from ..ports.report_generator import GenerationError, ReportGenerator
from ..ports.site_publisher import SitePublisher


@dataclass
class GenerationRunResult:
    keyword_count: int = 0
    succeeded: int = 0
    failed: int = 0
    failures: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.failures is None:
            self.failures = []


class GenerateDailyReportsUseCase:
    def __init__(
        self,
        keyword_source: KeywordSource,
        generator: ReportGenerator,
        publisher: SitePublisher,
        feed_title: str,
        feed_link: str,
        feed_description: str,
        max_feed_items: int = 20,
    ):
        self._keywords = keyword_source
        self._generator = generator
        self._publisher = publisher
        self._feed_title = feed_title
        self._feed_link = feed_link
        self._feed_description = feed_description
        self._max_feed_items = max_feed_items

    def execute(self) -> GenerationRunResult:
        keywords = self._keywords.list_open()
        result = GenerationRunResult(keyword_count=len(keywords))
        print(f"対象キーワード: {len(keywords)} 件")

        for keyword in keywords:
            try:
                print(f"- 生成中: {keyword.title}")
                report = self._generator.generate(keyword)
                item = self._publisher.write_report_page(report)
                result.succeeded += 1
                print(
                    f"  OK [{report.generated_by}] {report.body_char_count}字 "
                    f"-> {item.link}"
                )
            except GenerationError as exc:
                result.failed += 1
                result.failures.append(f"{keyword.title}: {exc}")
                print(f"  NG: {exc}", file=sys.stderr)

        # 既存レポートを走査し、直近 N 件でフィードを再構築
        items = self._publisher.list_existing_items()
        built = feed_module.assemble(
            self._feed_title,
            self._feed_link,
            self._feed_description,
            items,
            max_items=self._max_feed_items,
        )
        self._publisher.write_feed(built)
        print(
            f"フィード更新: {len(built.items)} 件掲載 "
            f"(成功 {result.succeeded} / 失敗 {result.failed})"
        )
        return result
