from __future__ import annotations

import os

from .base import LLMProvider
from .providers.ollama import OllamaProvider


def get_provider(name: str | None = None) -> LLMProvider:
    """
    依名稱取得 provider。預設讀環境變數 LLM_PROVIDER（預設 ollama）。
    後續要擴充新供應商，只要在這裡加 mapping，不影響上層邏輯。
    """

    provider_name = (name or os.environ.get("LLM_PROVIDER") or "ollama").strip().lower()

    if provider_name == "ollama":
        return OllamaProvider()

    raise ValueError(f"Unknown LLM provider: {provider_name}")


def get_default_model() -> str:
    return os.environ.get("LLM_MODEL") or "llama3"

