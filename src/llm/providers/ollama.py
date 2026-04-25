from __future__ import annotations

import os
from typing import Sequence

import httpx

from ..base import LLMProvider
from ..types import ChatMessage, LLMResponse


class OllamaProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "ollama"

    def __init__(self, *, base_url: str | None = None, timeout_s: float = 120.0):
        self._base_url = (base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self._timeout_s = timeout_s

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        extra: dict | None = None,
    ) -> LLMResponse:
        # Ollama chat API: POST /api/chat
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if extra:
            # e.g. {"format": "json"} to enforce JSON output (supported by newer Ollama)
            payload.update(extra)

        with httpx.Client(timeout=self._timeout_s) as client:
            r = client.post(f"{self._base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()

        content = (data.get("message") or {}).get("content") or ""
        stop_reason = data.get("done_reason")
        used_model = data.get("model") or model

        return LLMResponse(content=content, model=used_model, provider=self.name, stop_reason=stop_reason)

