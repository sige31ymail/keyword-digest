"""ReportGenerator ポート: キーワードからレポートを生成する。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.keyword import Keyword
from ..domain.report import Report


class GenerationError(RuntimeError):
    """レポート生成に失敗した（API エラー・内容不足など）。"""


class ReportGenerator(ABC):
    @abstractmethod
    def generate(self, keyword: Keyword) -> Report:
        """キーワードからレポートを生成する。失敗時は GenerationError を送出。"""
        raise NotImplementedError
