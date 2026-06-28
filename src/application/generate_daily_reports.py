"""GenerateDailyReportsUseCase: 中核ユースケース。

Open Issue（キーワード）を取得し、各キーワードのレポートを生成して HTML 化、
保持ポリシー（期間+件数）で古いレポートを整理し、直近 N 件で RSS フィードを
再構築する。1 件の失敗は全体に波及させない。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..domain import feed as feed_module
from ..domain import retention as retention_module
from ..ports.keyword_source import KeywordSource
from ..ports.report_generator import GenerationError, ReportGenerator
from ..ports.site_publisher import SitePublisher


@dataclass
class GenerationRunResult:
    keyword_count: int = 0
    succeeded: int = 0
    failed: int = 0
    pruned: int = 0
    feed_items: int = 0
    failures: list[str] = field(default_factory=list)


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
        retention_max_age_days: int = 30,
        retention_max_count: int = 100,
    ):
        self._keywords = keyword_source
        self._generator = generator
        self._publisher = publisher
        self._feed_title = feed_title
        self._feed_link = feed_link
        self._feed_description = feed_description
        self._max_feed_items = max_feed_items
        self._retention_max_age_days = retention_max_age_days
        # 保持件数はフィード掲載件数を下回らないようにする（リンク切れ防止）
        self._retention_max_count = max(retention_max_count, max_feed_items)

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

        # 既存レポートを走査し、保持ポリシー（期間+件数）で整理
        items = self._publisher.list_existing_items()
        decision = retention_module.partition(
            items,
            now=datetime.now(timezone.utc),
            max_age_days=self._retention_max_age_days,
            max_count=self._retention_max_count,
        )
        if decision.remove:
            result.pruned = self._publisher.delete_reports(decision.remove)
            print(
                f"保持ポリシー適用: {result.pruned} 件削除 "
                f"(期間 {self._retention_max_age_days}日 / 上限 "
                f"{self._retention_max_count}件)"
            )

        # 残ったレポートから直近 N 件でフィードを再構築
        built = feed_module.assemble(
            self._feed_title,
            self._feed_link,
            self._feed_description,
            decision.keep,
            max_items=self._max_feed_items,
        )
        self._publisher.write_feed(built)
        result.feed_items = len(built.items)
        print(
            f"フィード更新: {len(built.items)} 件掲載 / 保持 {len(decision.keep)} 件 "
            f"(成功 {result.succeeded} / 失敗 {result.failed} / 削除 {result.pruned})"
        )
        return result
