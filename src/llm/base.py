from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from .types import ChatMessage, LLMResponse


class LLMProvider(ABC):
    """
    統一的 LLM 介面：上層只依賴這個抽象，不綁定任何特定供應商。
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        extra: dict | None = None,
    ) -> LLMResponse: ...

