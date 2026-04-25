from __future__ import annotations

from abc import ABC, abstractmethod


class TTSProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def synthesize(self, text: str, *, output_path: str) -> str:
        """
        將 text 合成語音並寫到 output_path。
        回傳實際輸出的檔案路徑（通常等於 output_path）。
        """

