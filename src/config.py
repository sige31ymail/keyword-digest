"""環境変数からの設定読み取り。Actions では多くが自動注入される。"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    github_repository: str  # "owner/repo"
    github_token: str
    site_base_url: str  # 例: https://owner.github.io/keyword-digest
    site_dir: str
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    max_search_queries: int
    article_min_chars: int
    article_max_chars: int
    tavily_api_key: str
    tavily_max_results: int
    openai_api_key: str
    openai_model: str
    openai_web_search: bool
    openai_search_context_size: str
    anthropic_api_key: str
    anthropic_model: str
    max_feed_items: int
    retention_max_age_days: int
    retention_max_count: int

    @property
    def owner(self) -> str:
        return self.github_repository.split("/", 1)[0]

    @property
    def repo(self) -> str:
        return self.github_repository.split("/", 1)[1]


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"環境変数 {name} が未設定です。")
    return value


def load() -> Config:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    github_repository = _required("GITHUB_REPOSITORY")
    default_base = (
        f"https://{github_repository.split('/', 1)[0]}.github.io/"
        f"{github_repository.split('/', 1)[1]}"
    )
    return Config(
        github_repository=github_repository,
        github_token=_required("GITHUB_TOKEN"),
        site_base_url=os.environ.get("SITE_BASE_URL", default_base).rstrip("/"),
        site_dir=os.environ.get("SITE_DIR", os.path.join(repo_root, "site")),
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip(),
        deepseek_base_url=os.environ.get(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ).strip(),
        max_search_queries=int(os.environ.get("MAX_SEARCH_QUERIES", "5")),
        article_min_chars=int(os.environ.get("ARTICLE_MIN_CHARS", "1800")),
        article_max_chars=int(os.environ.get("ARTICLE_MAX_CHARS", "3000")),
        tavily_api_key=os.environ.get("TAVILY_API_KEY", "").strip(),
        tavily_max_results=int(os.environ.get("TAVILY_MAX_RESULTS", "6")),
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip(),
        openai_web_search=os.environ.get("OPENAI_WEB_SEARCH", "true").strip().lower()
        not in ("0", "false", "no", ""),
        openai_search_context_size=os.environ.get(
            "OPENAI_SEARCH_CONTEXT_SIZE", "medium"
        ).strip(),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.environ.get(
            "ANTHROPIC_MODEL", "claude-haiku-4-5"
        ).strip(),
        max_feed_items=int(os.environ.get("MAX_FEED_ITEMS", "20")),
        retention_max_age_days=int(
            os.environ.get("RETENTION_MAX_AGE_DAYS", "30")
        ),
        retention_max_count=int(os.environ.get("RETENTION_MAX_COUNT", "100")),
    )
