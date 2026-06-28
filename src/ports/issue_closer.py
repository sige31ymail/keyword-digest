"""IssueCloser ポート: 生成完了したキーワード Issue をクローズする。

「一度だけ生成して恒久保存」モデルでは、レポート生成に成功した Issue を
クローズして再生成対象（Open）から外す。記事は site/ に git で永続化される。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class IssueCloser(ABC):
    @abstractmethod
    def close(self, issue_number: int, comment: str | None = None) -> None:
        """指定 Issue をクローズする。comment があれば先にコメントを残す。"""
        raise NotImplementedError
