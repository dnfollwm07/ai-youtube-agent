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
        msgs = [{"role": m.role, "content": m.content} for m in messages]

        # 1) 優先走 Ollama 原生：POST /api/chat
        payload_api = {
            "model": model,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if extra:
            # e.g. {"format": "json"} to enforce JSON output (supported by newer Ollama)
            payload_api.update(extra)

        with httpx.Client(timeout=self._timeout_s) as client:
            try:
                r = client.post(f"{self._base_url}/api/chat", json=payload_api)
                r.raise_for_status()
                data = r.json()
                content = (data.get("message") or {}).get("content") or ""
                stop_reason = data.get("done_reason")
                used_model = data.get("model") or model
                return LLMResponse(content=content, model=used_model, provider=self.name, stop_reason=stop_reason)
            except httpx.HTTPStatusError as e:
                # 有些環境/版本只暴露 OpenAI 相容路徑（/v1/chat/completions）
                if e.response is None or e.response.status_code != 404:
                    raise

            # 2) Fallback：OpenAI 相容：POST /v1/chat/completions
            payload_v1 = {
                "model": model,
                "messages": msgs,
                "temperature": temperature,
                "stream": False,
            }
            if extra and extra.get("format") == "json":
                # OpenAI-style JSON mode
                payload_v1["response_format"] = {"type": "json_object"}

            r2 = client.post(f"{self._base_url}/v1/chat/completions", json=payload_v1)
            r2.raise_for_status()
            data2 = r2.json()

        choice0 = (data2.get("choices") or [{}])[0]
        content2 = ((choice0.get("message") or {}) or {}).get("content") or ""
        stop_reason2 = choice0.get("finish_reason")
        used_model2 = data2.get("model") or model

        return LLMResponse(content=content2, model=used_model2, provider=self.name, stop_reason=stop_reason2)

