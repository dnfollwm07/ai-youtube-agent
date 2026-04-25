from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    provider: str
    stop_reason: Optional[str] = None
