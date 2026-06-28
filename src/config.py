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
    openai_api_key: str
    openai_model: str
    anthropic_api_key: str
    anthropic_model: str
    max_feed_items: int

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
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip(),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.environ.get(
            "ANTHROPIC_MODEL", "claude-haiku-4-5"
        ).strip(),
        max_feed_items=int(os.environ.get("MAX_FEED_ITEMS", "20")),
    )
