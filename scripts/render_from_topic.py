import argparse
import json
import os
import re
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.pipeline.generate import generate
from src.pipeline.render import render
from src.pipeline.types import Plan, Script
from src.youtube_auth import get_youtube_service
from src.youtube_upload import upload_video


def _slugify_topic(topic: str, *, max_len: int = 40) -> str:
    s = (topic or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_]+", "", s)
    s = s.strip("_")
    return (s[:max_len] or "topic")


def _artifact_to_json(artifact: Script | Plan) -> dict:
    if isinstance(artifact, Script):
        return {"hook": artifact.hook, "body": artifact.body, "ending": artifact.ending}
    return {
        "title_idea": artifact.title_idea,
        "style": {"genre": artifact.genre, "pace": artifact.pace, "mood": list(artifact.mood)},
        "scenes": [
            {
                "scene": s.scene,
                "duration_s": s.duration_s,
                "visual_query": s.visual_query,
                "on_screen_text": s.on_screen_text,
                "voiceover_hint": s.voiceover_hint,
            }
            for s in artifact.scenes
        ],
        "music_sfx": list(artifact.music_sfx),
        "hashtags": list(artifact.hashtags),
    }


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _is_dir_like(path: str) -> bool:
    """
    判斷使用者傳入的 out 是否像「資料夾」：
    - 以 / 結尾
    - 或實際存在且是資料夾
    """
    if path.endswith(os.sep):
        return True
    if os.path.exists(path) and os.path.isdir(path):
        return True
    return False


def _force_under_outputs(path: str) -> str:
    """
    你要求「所有輸出都在 outputs/ 內」：
    - 若是絕對路徑：仍然強制放到 outputs/ 下（取其 basename）
    - 若是相對路徑且不是以 outputs/ 開頭：自動加上 outputs/
    """
    path = path.strip()
    if not path:
        return "outputs"

    if os.path.isabs(path):
        return os.path.join("outputs", os.path.basename(path.rstrip(os.sep)))

    norm = os.path.normpath(path)
    if norm == "outputs" or norm.startswith(f"outputs{os.sep}"):
        return path

    return os.path.join("outputs", path)


def main():
    parser = argparse.ArgumentParser(description="兩階段管線：先生成 script/plan，再選擇渲染/生成影片方式")
    parser.add_argument("--topic", required=True, help="主題，例如：貓狗互動超可愛的一段影片")
    parser.add_argument("--mode", default="script", choices=["script", "plan"], help="第一階段：生成類型")
    parser.add_argument(
        "--out",
        nargs="?",
        const="__AUTO__",
        default=None,
        help=(
            "輸出控制（三態）：\n"
            "1) 不帶 --out：不產生影片，只輸出單一 JSON（用於驗證 script/plan）\n"
            "2) 帶 --out 但不給值，或給資料夾路徑：用預設命名輸出資料夾與 video.mp4\n"
            "3) 帶 --out <名稱>（不含 .mp4）：以該名稱作為輸出資料夾名，並在其中輸出 video.mp4 與相關檔案"
        ),
    )
    parser.add_argument("--voice", default=None, help="macOS say voice（例如：Ting-Ting / Mei-Jia / Sin-Ji）")
    parser.add_argument("--rate", type=int, default=None, help="macOS say 語速（wpm）")
    parser.add_argument("--model", default=None, help="LLM model（預設讀 LLM_MODEL 或 llama3）")
    parser.add_argument("--width", type=int, default=1080, help="畫面寬度（預設 1080）")
    parser.add_argument("--height", type=int, default=1920, help="畫面高度（預設 1920）")
    parser.add_argument("--margin-x", type=int, default=96, help="左右留白（預設 96）")
    parser.add_argument("--margin-y", type=int, default=160, help="上下留白（預設 160）")
    parser.add_argument("--font-size", type=int, default=64, help="字幕字體大小（預設 64）")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="是否自動發佈到 YouTube（預設 False；前期人工審核用）。只有加上此參數才會自動上傳。",
    )
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"], help="自動上傳隱私狀態（預設 private）")
    parser.add_argument("--title", default=None, help="自動上傳標題（預設用 topic）")
    parser.add_argument("--description", default="", help="自動上傳描述（預設空）")
    args = parser.parse_args()

    artifact = generate(args.topic, mode=args.mode, model=args.model)

    ts = _now_stamp()
    topic_slug = _slugify_topic(args.topic)

    # 情況 1：不帶 --out => 不產生影片，只輸出單一 JSON
    if args.out is None:
        os.makedirs("outputs", exist_ok=True)
        out_json = os.path.join("outputs", f"{ts}_{topic_slug}_{args.mode}.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(_artifact_to_json(artifact), f, ensure_ascii=False, indent=2)
        print(out_json)
        if args.publish:
            raise SystemExit("你指定了 --publish，但未帶 --out（未產生影片）。請加上 --out 先產生 video.mp4 再上傳。")
        return

    # 情況 2/3：帶 --out => 產生影片與資料夾
    out_arg = args.out
    if out_arg == "__AUTO__":
        # 2a) 只寫了 --out（未給值）
        parent_dir = "outputs"
        run_name = f"{ts}_{topic_slug}"
    elif _is_dir_like(out_arg):
        # 2b) 給的是資料夾路徑（或看起來像資料夾）
        parent_dir = _force_under_outputs(out_arg.rstrip(os.sep))
        run_name = f"{ts}_{topic_slug}"
    else:
        # 3) 給的是名稱/檔名（不含 .mp4）
        parent_dir = _force_under_outputs(os.path.dirname(out_arg) or "outputs")
        run_name = os.path.basename(out_arg)
        if run_name.lower().endswith(".mp4"):
            run_name = os.path.splitext(run_name)[0]

    run_dir = os.path.join(parent_dir, run_name)
    os.makedirs(run_dir, exist_ok=True)

    # 同步落盤生成結果，方便後續查詢/復現
    artifact_path = os.path.join(run_dir, f"{args.mode}.json")
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(_artifact_to_json(artifact), f, ensure_ascii=False, indent=2)

    out_mp4_path = os.path.join(run_dir, "video.mp4")
    work_dir = os.path.join(run_dir, "_work")

    # 第二階段：依 mode 自動選擇後端
    if args.mode == "plan":
        if args.publish:
            raise SystemExit(
                f"你指定了 --publish，但 mode=plan 的影片生成後端尚未開發（尚無 video.mp4）。已先輸出 {artifact_path}。"
            )
        raise SystemExit(f"目前 mode=plan 的影片生成後端尚未開發（video_api renderer）。已先輸出 {artifact_path}。")

    out = render(
        artifact,
        backend="tts_ffmpeg",
        out_mp4_path=out_mp4_path,
        work_dir=work_dir,
        voice=args.voice,
        rate=args.rate,
        width=args.width,
        height=args.height,
        margin_x=args.margin_x,
        margin_y=args.margin_y,
        font_size=args.font_size,
    )
    print(out)

    if args.publish:
        youtube = get_youtube_service()
        resp = upload_video(
            youtube,
            file_path=out,
            title=(args.title or args.topic),
            description=args.description,
            tags=[],
            privacy_status=args.privacy,
        )
        print(f"published_video_id={resp.get('id')}")


if __name__ == "__main__":
    main()

