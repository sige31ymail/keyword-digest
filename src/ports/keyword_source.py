"""KeywordSource ポート: Open な Issue 一覧をキーワードとして取得する。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.keyword import Keyword


class KeywordSource(ABC):
    @abstractmethod
    def list_open(self) -> list[Keyword]:
        """Open 状態のキーワード一覧を返す。"""
        raise NotImplementedError
