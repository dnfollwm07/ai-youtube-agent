from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

from .ffmpeg import get_duration_seconds, run_ffmpeg
from .tts.base import TTSProvider


@dataclass(frozen=True)
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    # 預設 YouTube Shorts（9:16）白底黑字
    bg_color: str = "white"
    font_color: str = "black"
    font_size: int = 64
    line_spacing: int = 10
    # 留白：避免貼邊，也更像 Shorts 安全區
    margin_x: int = 96
    margin_y: int = 160
    # 指定支援中文的字型檔，避免字幕變成方框
    font_file: str | None = None
    # 為了避免極短音訊造成 ffmpeg 產出 0 frame / concat 音訊損毀，
    # 我們允許在「語音結尾」補少量靜音到最小時長；畫面時長會與補齊後的音訊完全一致。
    min_audio_s: float = 0.8


def _sanitize_filename(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")
    return s or "seg"


def _escape_drawtext(text: str) -> str:
    # ffmpeg drawtext filter string escaping for values like fontfile/textfile paths
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )


def _resolve_font_file(preferred: str | None) -> str | None:
    if preferred and os.path.exists(preferred):
        return preferred

    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _wrap_text(text: str, *, max_chars: int) -> str:
    """
    很簡單的自動換行：以字元數為基準（適用中日韓為主的字幕）。
    - 先用空白切詞（如果有）
    - 沒有空白時就按字元硬切
    """
    text = (text or "").strip()
    if not text:
        return text

    if max_chars <= 0:
        return text

    if " " in text:
        words = [w for w in text.split(" ") if w]
        lines: list[str] = []
        cur = ""
        for w in words:
            cand = (cur + " " + w).strip() if cur else w
            if len(cand) <= max_chars:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return "\n".join(lines)

    # 無空白：CJK 常見情況
    return "\n".join(text[i : i + max_chars] for i in range(0, len(text), max_chars))


def _make_segment(
    *,
    text: str,
    audio_path: str,
    out_path: str,
    cfg: RenderConfig,
    work_dir: str,
) -> None:
    audio_duration = get_duration_seconds(audio_path)
    duration = audio_duration

    # 估算每行可容納字元數，避免超出畫面寬度
    usable_w = max(1, cfg.width - 2 * cfg.margin_x)
    # drawtext 的 text_w 受字型與字距影響，這裡保守估算，避免仍然超出畫面
    approx_char_w = max(1.0, cfg.font_size * 1.35)
    max_chars = max(3, int(usable_w / approx_char_w))
    wrapped = _wrap_text(text, max_chars=max_chars)

    # 避免 drawtext 的 \n 跳脫問題：用 textfile 直接餵「真正換行」文字（像一個 view 的概念）
    os.makedirs(work_dir, exist_ok=True)
    textfile_path = os.path.join(work_dir, f"_text_{_sanitize_filename(os.path.basename(out_path))}.txt")
    with open(textfile_path, "w", encoding="utf-8") as f:
        f.write(wrapped)

    font_file = _resolve_font_file(cfg.font_file)
    font_part = f"fontfile={_escape_drawtext(font_file)}:" if font_file else ""
    textfile_part = f"textfile='{_escape_drawtext(os.path.abspath(textfile_path))}':reload=0:"

    drawtext = (
        "drawtext="
        f"{font_part}"
        f"{textfile_part}"
        "x=(w-text_w)/2:"
        "y=(h-text_h)/2:"
        f"fontsize={cfg.font_size}:"
        f"fontcolor={cfg.font_color}:"
        f"line_spacing={cfg.line_spacing}:"
    )

    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c={cfg.bg_color}:s={cfg.width}x{cfg.height}:r={cfg.fps}:d={duration}",
            "-i",
            audio_path,
            "-vf",
            drawtext,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-shortest",
            out_path,
        ]
    )


def render_script_to_video(
    *,
    sentences: list[str],
    tts: TTSProvider,
    work_dir: str,
    output_mp4_path: str,
    cfg: RenderConfig | None = None,
) -> str:
    """
    將「每句一句」的 sentences：
    - 逐句做 TTS 音訊
    - 逐句做素色背景 + 字幕 + 音訊的段落影片
    - 串接成一支完整 mp4
    """
    cfg = cfg or RenderConfig()
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(os.path.dirname(output_mp4_path) or ".", exist_ok=True)

    seg_paths: list[str] = []
    for i, sentence in enumerate(sentences, start=1):
        sentence = (sentence or "").strip()
        if not sentence:
            raise ValueError(f"Sentence {i} is empty; cannot render a segment with 0 duration audio.")
        safe = _sanitize_filename(f"{i:02d}")
        raw_audio_path = os.path.join(work_dir, f"{safe}.aiff")
        audio_path = os.path.join(work_dir, f"{safe}.wav")
        seg_path = os.path.join(work_dir, f"{safe}.mp4")

        # 1) 先用 TTS 生成原始音訊
        tts.synthesize(sentence, output_path=raw_audio_path)

        # 2) 統一轉成 44.1kHz stereo wav，必要時補靜音到最小時長
        raw_dur = get_duration_seconds(raw_audio_path)
        if raw_dur < cfg.min_audio_s:
            run_ffmpeg(
                [
                    "-i",
                    raw_audio_path,
                    "-af",
                    f"apad,atrim=0:{cfg.min_audio_s}",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    audio_path,
                ]
            )
        else:
            run_ffmpeg(["-i", raw_audio_path, "-ar", "44100", "-ac", "2", audio_path])

        _make_segment(text=sentence, audio_path=audio_path, out_path=seg_path, cfg=cfg, work_dir=work_dir)
        seg_paths.append(seg_path)

    # concat demuxer
    concat_list = os.path.join(work_dir, "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in seg_paths:
            # 使用絕對路徑，避免 concat demuxer 以 concat.txt 所在目錄做相對解析時重複拼接路徑
            f.write(f"file '{os.path.abspath(p)}'\n")

    # 重新編碼一次，確保相容性
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            output_mp4_path,
        ],
        check=True,
    )

    return output_mp4_path

