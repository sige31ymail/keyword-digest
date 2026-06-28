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
from .infrastructure.deepseek_generator import DeepSeekPipelineReportGenerator
from .infrastructure.fallback_generator import FallbackReportGenerator
from .infrastructure.github_issue_source import GitHubIssueKeywordSource
from .infrastructure.openai_generator import OpenAiReportGenerator
from .infrastructure.openai_web_search import OpenAiWebSearch
from .infrastructure.static_site_publisher import StaticSitePublisher
from .infrastructure.tavily_web_search import TavilyWebSearch


def build_search_backend(cfg: config.Config):
    """検索バックエンドを選ぶ。Tavily を優先し、無ければ OpenAI web_search。"""
    if cfg.tavily_api_key:
        return TavilyWebSearch(
            cfg.tavily_api_key, max_results=cfg.tavily_max_results
        )
    if cfg.openai_api_key:
        return OpenAiWebSearch(
            cfg.openai_api_key,
            cfg.openai_model,
            search_context_size=cfg.openai_search_context_size,
        )
    return None


def build_generator(cfg: config.Config):
    """DeepSeek 多段パイプラインを主、Anthropic を副に配線する。

    検索バックエンドは Tavily（既定）/ OpenAI web_search。DeepSeek には検索機能が
    ないため検索は WebSearch ポートへ委譲する。DeepSeek 未設定時は従来の OpenAI
    単段生成へ後方互換フォールバックする。
    """
    web_search = build_search_backend(cfg)

    primary = None
    if cfg.deepseek_api_key and web_search is not None:
        primary = DeepSeekPipelineReportGenerator(
            cfg.deepseek_api_key,
            web_search,
            model=cfg.deepseek_model,
            base_url=cfg.deepseek_base_url,
            max_search_queries=cfg.max_search_queries,
            article_min_chars=cfg.article_min_chars,
            article_max_chars=cfg.article_max_chars,
        )
    elif cfg.openai_api_key:
        # DeepSeek 未設定（または検索バックエンド無し）時は従来方式で動かす
        primary = OpenAiReportGenerator(
            cfg.openai_api_key,
            cfg.openai_model,
            web_search=cfg.openai_web_search,
            search_context_size=cfg.openai_search_context_size,
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
        "DEEPSEEK_API_KEY(+OPENAI_API_KEY) / OPENAI_API_KEY / "
        "ANTHROPIC_API_KEY のいずれかが必要です。"
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
        retention_max_age_days=cfg.retention_max_age_days,
        retention_max_count=cfg.retention_max_count,
    )
    result = use_case.execute()
    # 1 件でも成功すれば正常終了（全滅時のみエラー終了）
    if result.keyword_count > 0 and result.succeeded == 0:
        print("すべてのキーワードで生成に失敗しました。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
