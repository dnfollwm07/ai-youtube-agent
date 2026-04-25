from __future__ import annotations

import os
import subprocess

from .base import TTSProvider
from src.config import get_settings


class MacOSSayTTS(TTSProvider):
    """
    使用 macOS 內建 `say` 指令的離線 TTS。
    - 優點：不需網路、不需 API key
    - 缺點：音色/語言能力有限（後續可替換 provider）
    """

    @property
    def name(self) -> str:
        return "macos_say"

    def __init__(self, *, voice: str | None = None, rate_wpm: int | None = None):
        s = get_settings()
        self._voice = voice or s.tts_voice or self._pick_default_zh_voice()
        self._rate_wpm = rate_wpm if rate_wpm is not None else s.tts_rate_wpm

    @staticmethod
    def _pick_default_zh_voice() -> str | None:
        """
        優先挑選中文語音（繁體/普通話），避免英文 voice 讀中文只剩標點。
        """
        try:
            proc = subprocess.run(["say", "-v", "?"], check=True, capture_output=True, text=True)
        except Exception:
            return None

        # 較常見的中文 voice 名稱（依 macOS 版本不同）
        # 注意：同一語音在不同系統可能有不同拼法（例如 Tingting vs Ting-Ting）。
        preferred_names = [
            # 你這台機器上實際可用的（say -v '?' | grep zh_）
            "Tingting",  # zh_CN
            "Meijia",    # zh_TW
            "Sinji",     # zh_HK

            # 其他 macOS 版本可能出現的拼法（保留兼容）
            "Ting-Ting",
            "Mei-Jia",
            "Sin-Ji",
            "Yu-Shu",
            "Li-mu",
        ]

        lines = proc.stdout.splitlines()
        available = []
        for line in lines:
            # e.g. "Ting-Ting           zh_HK    # 你好！我叫..."
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            locale = parts[1] if len(parts) > 1 else ""
            available.append((name, locale))

        available_names = {name for name, _ in available}
        for want in preferred_names:
            if want in available_names:
                return want

        # 退而求其次：挑第一個 zh_* locale
        for name, locale in available:
            if locale.startswith("zh_"):
                return name

        return None

    def synthesize(self, text: str, *, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        cmd: list[str] = ["say"]
        if self._voice:
            cmd += ["-v", self._voice]
        if self._rate_wpm:
            cmd += ["-r", str(self._rate_wpm)]

        # say: -o output_path  text
        cmd += ["-o", output_path, text]

        subprocess.run(cmd, check=True)
        return output_path

