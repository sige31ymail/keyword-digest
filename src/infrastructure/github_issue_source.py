"""GitHubIssueKeywordSource: Open Issue を REST API でキーワードとして取得。"""
from __future__ import annotations

from ..domain.keyword import Keyword
from ..ports.keyword_source import KeywordSource
from . import _http


class GitHubIssueKeywordSource(KeywordSource):
    def __init__(self, repository: str, token: str):
        self._repository = repository
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "keyword-digest/0.1",
        }

    def list_open(self) -> list[Keyword]:
        keywords: list[Keyword] = []
        page = 1
        while True:
            url = (
                f"https://api.github.com/repos/{self._repository}/issues"
                f"?state=open&per_page=100&page={page}"
            )
            issues, _ = _http.get_json(url, self._headers())
            if not issues:
                break
            for issue in issues:
                # Issues API は PR も返すため除外する
                if "pull_request" in issue:
                    continue
                title = (issue.get("title") or "").strip()
                if not title:
                    continue
                keywords.append(
                    Keyword(
                        title=title,
                        note=(issue.get("body") or "").strip(),
                        issue_number=issue.get("number"),
                    )
                )
            if len(issues) < 100:
                break
            page += 1
        return keywords
