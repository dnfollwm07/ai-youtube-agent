from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    v = _env(name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """
    集中管理本專案的「預設值」與「可用環境變數」。
    後續要做設定檔（yaml/toml）或多環境（dev/prod），也可以以此為單一入口擴充。
    """

    # LLM
    llm_provider: str = "ollama"  # env: LLM_PROVIDER
    llm_model: str = "llama3"  # env: LLM_MODEL
    ollama_base_url: str = "http://localhost:11434"  # env: OLLAMA_BASE_URL

    # TTS
    tts_voice: str | None = None  # env: TTS_VOICE（不設時由 provider 自動挑中文 voice）
    tts_rate_wpm: int | None = None  # env: TTS_RATE_WPM（可選）

    # Video render defaults (Shorts 9:16)
    video_width: int = 1080  # env: VIDEO_WIDTH
    video_height: int = 1920  # env: VIDEO_HEIGHT
    video_margin_x: int = 96  # env: VIDEO_MARGIN_X
    video_margin_y: int = 160  # env: VIDEO_MARGIN_Y
    video_font_size: int = 64  # env: VIDEO_FONT_SIZE


def get_settings() -> Settings:
    """
    以環境變數覆蓋預設值，回傳一份不可變 Settings。
    """
    return Settings(
        llm_provider=_env("LLM_PROVIDER", "ollama") or "ollama",
        llm_model=_env("LLM_MODEL", "llama3") or "llama3",
        ollama_base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434") or "http://localhost:11434",
        tts_voice=_env("TTS_VOICE"),
        tts_rate_wpm=(None if _env("TTS_RATE_WPM") is None else _env_int("TTS_RATE_WPM", 180)),
        video_width=_env_int("VIDEO_WIDTH", 1080),
        video_height=_env_int("VIDEO_HEIGHT", 1920),
        video_margin_x=_env_int("VIDEO_MARGIN_X", 96),
        video_margin_y=_env_int("VIDEO_MARGIN_Y", 160),
        video_font_size=_env_int("VIDEO_FONT_SIZE", 64),
    )

