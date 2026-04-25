from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence


Mode = Literal["script", "plan"]
RenderBackend = Literal["tts_ffmpeg", "video_api"]


@dataclass(frozen=True)
class Script:
    hook: str
    body: list[str]
    ending: str

    def sentences(self) -> list[str]:
        return [self.hook, *self.body, self.ending]


@dataclass(frozen=True)
class PlanScene:
    scene: int
    duration_s: float
    visual_query: str
    on_screen_text: str
    voiceover_hint: str | None = None


@dataclass(frozen=True)
class Plan:
    title_idea: str
    genre: str
    pace: str
    mood: Sequence[str]
    scenes: Sequence[PlanScene]
    music_sfx: Sequence[str]
    hashtags: Sequence[str]

