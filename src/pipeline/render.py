from __future__ import annotations

import os
from datetime import datetime

from src.media.render_script_video import render_script_to_video
from src.media.render_script_video import RenderConfig
from src.media.tts.macos_say import MacOSSayTTS

from .types import Plan, RenderBackend, Script


def render(
    artifact: Script | Plan,
    *,
    backend: RenderBackend,
    out_mp4_path: str | None = None,
    work_dir: str | None = None,
    voice: str | None = None,
    rate: int | None = None,
    width: int | None = None,
    height: int | None = None,
    margin_x: int | None = None,
    margin_y: int | None = None,
    font_size: int | None = None,
) -> str:
    if not out_mp4_path:
        os.makedirs("outputs", exist_ok=True)
        out_mp4_path = os.path.join("outputs", datetime.now().strftime("%Y%m%d_%H%M%S") + ".mp4")
    if not work_dir:
        work_dir = os.path.join("outputs", "_work_" + datetime.now().strftime("%Y%m%d_%H%M%S"))

    if backend == "tts_ffmpeg":
        if not isinstance(artifact, Script):
            raise ValueError("backend=tts_ffmpeg 目前只支援 mode=script（因為是一句一句配音+字幕）。")
        tts = MacOSSayTTS(voice=voice, rate_wpm=rate)
        cfg = RenderConfig(
            width=width or RenderConfig.width,
            height=height or RenderConfig.height,
            margin_x=margin_x or RenderConfig.margin_x,
            margin_y=margin_y or RenderConfig.margin_y,
            font_size=font_size or RenderConfig.font_size,
        )
        return render_script_to_video(
            sentences=artifact.sentences(),
            tts=tts,
            work_dir=work_dir,
            output_mp4_path=out_mp4_path,
            cfg=cfg,
        )

    if backend == "video_api":
        raise NotImplementedError("video_api renderer 尚未實作（預留給未來的影片生成接口）。")

    raise ValueError(f"Unknown backend: {backend}")

