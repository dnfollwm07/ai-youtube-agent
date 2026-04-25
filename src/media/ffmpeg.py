from __future__ import annotations

import json
import subprocess


def run_ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", *args], check=True)


def get_duration_seconds(path: str) -> float:
    """
    用 ffprobe 取得音訊/影片長度（秒）。
    """
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout)
    return float(data["format"]["duration"])

