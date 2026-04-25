import argparse
import os
import sys
from src.youtube_upload import upload_video

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.youtube_auth import get_youtube_service


def main():
    parser = argparse.ArgumentParser(description="YouTube Data API v3 上傳測試（本地 OAuth 登入）")
    parser.add_argument("--file", required=True, help="要上傳的影片檔路徑（建議 9:16，<=60s 方便 Shorts）")
    parser.add_argument("--title", required=True, help="影片標題")
    parser.add_argument("--description", default="", help="影片描述")
    parser.add_argument("--tags", default="", help="以逗號分隔的 tags，例如：ai,news,shorts")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"], help="隱私狀態（預設 private）")
    args = parser.parse_args()

    file_path = args.file
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到檔案：{file_path}")

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    youtube = get_youtube_service()
    resp = upload_video(
        youtube=youtube,
        file_path=file_path,
        title=args.title,
        description=args.description,
        tags=tags,
        privacy_status=args.privacy,
    )

    video_id = resp.get("id")
    print("Upload success")
    print(f"video_id={video_id}")
    print(resp)


if __name__ == "__main__":
    main()

