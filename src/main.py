"""エントリポイント: 依存を配線して GenerateDailyReportsUseCase を実行する。

実行例:
    python -m src.main
必要な環境変数: GITHUB_REPOSITORY, GITHUB_TOKEN, OPENAI_API_KEY
任意: ANTHROPIC_API_KEY, SITE_BASE_URL, MAX_FEED_ITEMS, OPENAI_MODEL, ANTHROPIC_MODEL
"""
from __future__ import annotations

import sys

from . import config
from .application.generate_daily_reports import GenerateDailyReportsUseCase
from .infrastructure.anthropic_generator import AnthropicReportGenerator
from .infrastructure.fallback_generator import FallbackReportGenerator
from .infrastructure.github_issue_source import GitHubIssueKeywordSource
from .infrastructure.openai_generator import OpenAiReportGenerator
from .infrastructure.static_site_publisher import StaticSitePublisher


def build_generator(cfg: config.Config):
    """OpenAI を主、Anthropic を副に。どちらかが無ければ片方のみで動作。"""
    primary = (
        OpenAiReportGenerator(cfg.openai_api_key, cfg.openai_model)
        if cfg.openai_api_key
        else None
    )
    secondary = (
        AnthropicReportGenerator(cfg.anthropic_api_key, cfg.anthropic_model)
        if cfg.anthropic_api_key
        else None
    )
    if primary and secondary:
        return FallbackReportGenerator(primary, secondary)
    if primary:
        return primary
    if secondary:
        return secondary
    raise SystemExit(
        "OPENAI_API_KEY または ANTHROPIC_API_KEY の少なくとも一方が必要です。"
    )


def main() -> int:
    cfg = config.load()
    keyword_source = GitHubIssueKeywordSource(cfg.github_repository, cfg.github_token)
    generator = build_generator(cfg)
    publisher = StaticSitePublisher(cfg.site_dir, cfg.site_base_url)

    use_case = GenerateDailyReportsUseCase(
        keyword_source=keyword_source,
        generator=generator,
        publisher=publisher,
        feed_title="keyword-digest レポート",
        feed_link=cfg.site_base_url,
        feed_description="登録キーワードについて AI が生成した日次レポート",
        max_feed_items=cfg.max_feed_items,
    )
    result = use_case.execute()
    # 1 件でも成功すれば正常終了（全滅時のみエラー終了）
    if result.keyword_count > 0 and result.succeeded == 0:
        print("すべてのキーワードで生成に失敗しました。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
