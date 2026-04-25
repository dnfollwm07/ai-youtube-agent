from __future__ import annotations

from googleapiclient.http import MediaFileUpload


def upload_video(
    youtube,
    *,
    file_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy_status: str = "private",
    made_for_kids: bool = False,
):
    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacy_status,
            # 對應 YouTube Studio 的 Audience / COPPA 設定
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)
    return request.execute()

