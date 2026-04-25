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
        return {
            "hook": artifact.hook,
            "body": artifact.body,
            "ending": artifact.ending,
            "upload_title": artifact.upload_title,
            "upload_description": artifact.upload_description,
            "hashtags": artifact.hashtags,
            "tags": artifact.tags,
        }
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

def _ascii_ratio(s: str) -> float:
    if not s:
        return 0.0
    ascii_letters = sum(1 for ch in s if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    return ascii_letters / max(1, len(s))

def _is_mostly_zh(s: str) -> bool:
    return _ascii_ratio(s) <= 0.25


def _sanitize_hashtags(hashtags: list[str] | None) -> list[str]:
    if not hashtags:
        return []
    out: list[str] = []
    for h in hashtags:
        if not isinstance(h, str):
            continue
        h = h.strip()
        if not h:
            continue
        if not h.startswith("#"):
            h = "#" + h
        if h.lower() == "#shorts" or _is_mostly_zh(h):
            out.append(h)
    seen = set()
    dedup: list[str] = []
    for h in out:
        if h not in seen:
            seen.add(h)
            dedup.append(h)
    return dedup


def _sanitize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    out: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip().lstrip("#")
        if not t:
            continue
        if _is_mostly_zh(t):
            out.append(t)
    seen = set()
    dedup: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup


def _default_hashtags_for_topic(topic: str) -> list[str]:
    return ["#shorts", "#冷知識", "#腦洞", "#科普", "#你怎麼看", "#熱門話題"]


def _clean_description_hashtags(text: str) -> str:
    """
    移除描述中「大量英文」的 hashtag（保留 #shorts）。
    """
    if not text:
        return text
    parts = text.split()
    cleaned: list[str] = []
    for p in parts:
        if p.startswith("#"):
            if p.lower() == "#shorts" or _is_mostly_zh(p):
                cleaned.append(p)
            else:
                continue
        else:
            cleaned.append(p)
    return " ".join(cleaned)


def _clean_description_prefixes(text: str) -> str:
    """
    移除模型常見的模板前綴（例如「超短摘要：」「摘要：」），避免描述像機器輸出。
    """
    if not text:
        return text
    lines = [ln.strip() for ln in str(text).splitlines()]
    cleaned = []
    for ln in lines:
        ln = re.sub(r"^(超短摘要|摘要|結論|引導)\s*[:：]\s*", "", ln)
        cleaned.append(ln)
    return "\n".join([ln for ln in cleaned if ln])


def _soften_description_call_to_action(text: str) -> str:
    """
    避免描述被硬帶站隊/辯論（除非使用者本來就想做辯論片）。
    這裡只做非常輕量的替換/移除，保留描述的自然度。
    """
    if not text:
        return text
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    softened: list[str] = []
    for ln in lines:
        # 移除明顯站隊句式
        if re.search(r"你站哪邊", ln):
            continue
        if re.search(r"支持.+反對", ln):
            continue
        softened.append(ln)
    return "\n".join(softened)

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
    parser.add_argument(
        "--made-for-kids",
        action="store_true",
        help="上傳時是否宣告為兒童向內容（COPPA）。預設 False（不勾選）。只有加上此參數才為 True。",
    )
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
        # 若使用者未手動指定，優先用 AI 生成的 metadata
        ai_title = artifact.upload_title if isinstance(artifact, Script) else None
        ai_desc = artifact.upload_description if isinstance(artifact, Script) else None

        # 輕量兜底：避免中英夾雜/學術腔造成品質很差（例如大量英文）
        if ai_title and _ascii_ratio(ai_title) > 0.25:
            ai_title = None
        if ai_desc and _ascii_ratio(ai_desc) > 0.25:
            ai_desc = None

        upload_title = args.title or ai_title or args.topic
        upload_description = args.description or (ai_desc or "") or ""
        upload_description = _clean_description_prefixes(upload_description)
        upload_description = _clean_description_hashtags(upload_description)
        upload_description = _soften_description_call_to_action(upload_description)
        tags = _sanitize_tags(artifact.tags if isinstance(artifact, Script) else None)
        hashtags = _sanitize_hashtags(artifact.hashtags if isinstance(artifact, Script) else None)
        if "#shorts" not in [h.lower() for h in hashtags]:
            hashtags = ["#shorts", *hashtags]
        if len(hashtags) < 5:
            for h in _default_hashtags_for_topic(args.topic):
                if h not in hashtags:
                    hashtags.append(h)
                if len(hashtags) >= 8:
                    break
        if hashtags and upload_description:
            # 若 description 沒包含 hashtags，簡單附加在後面（保持可讀性）
            if not any(h in upload_description for h in hashtags):
                upload_description = upload_description.rstrip() + "\n\n" + " ".join(hashtags)
        elif hashtags and not upload_description:
            upload_description = " ".join(hashtags)

        resp = upload_video(
            youtube,
            file_path=out,
            title=upload_title,
            description=upload_description,
            tags=tags,
            privacy_status=args.privacy,
            made_for_kids=args.made_for_kids,
        )
        print(f"published_video_id={resp.get('id')}")


if __name__ == "__main__":
    main()

