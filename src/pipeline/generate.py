from __future__ import annotations

import json

from src.llm.factory import get_default_model, get_provider
from src.llm.types import ChatMessage

from .types import Mode, Plan, PlanScene, Script


SCRIPT_SYSTEM_PROMPT = """你是一位「很會抓人注意力的短影音創作者」。請輸出嚴格 JSON：
{
  "hook": "...",
  "body": ["...","...","...","...","...","..."],
  "ending": "..."
}
規則：
- 全程繁體中文、口語自然
- 每一句要像口播，長度適中（方便逐句上字幕/配音）
- 不能像論文，不要「首先/其次/最後」
- 不要捏造可核查的事實細節（人名/精準數字/未證實事件）
- 目標至少支撐 ≥10 秒
只能輸出 JSON，不要任何多餘文字。"""


PLAN_SYSTEM_PROMPT = """你是一個「短影音導演助理 + 素材關鍵詞工程師」。請輸出嚴格 JSON：
{
  "title_idea": "...",
  "style": { "genre": "news|cute|aesthetic|other", "pace": "fast|medium|slow", "mood": ["..."] },
  "scenes": [
    { "scene": 1, "duration_s": 2, "visual_query": "...", "on_screen_text": "...", "voiceover_hint": "..." }
  ],
  "music_sfx": ["..."],
  "hashtags": ["#..."]
}
規則：
- 這份輸出是給「影片生成/素材搜尋」用，不是直接口播作文
- scenes 至少 5 段，總時長目標 ≥10 秒
- 不要捏造可核查的事實細節
只能輸出 JSON，不要任何多餘文字。"""


def _json_from_llm(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    candidate = text if start == -1 or end == -1 or end <= start else text[start : end + 1]
    return json.loads(candidate)


def generate(topic: str, *, mode: Mode = "script", model: str | None = None) -> Script | Plan:
    provider = get_provider()
    model = model or get_default_model()

    system = SCRIPT_SYSTEM_PROMPT if mode == "script" else PLAN_SYSTEM_PROMPT
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=f"主題：{topic}"),
    ]

    resp = provider.chat(messages, model=model, temperature=0.6, extra={"format": "json"})
    data = _json_from_llm(resp.content)

    if mode == "script":
        return Script(hook=data["hook"], body=list(data["body"]), ending=data["ending"])

    style = data.get("style") or {}
    scenes = []
    for s in data.get("scenes") or []:
        scenes.append(
            PlanScene(
                scene=int(s["scene"]),
                duration_s=float(s["duration_s"]),
                visual_query=str(s["visual_query"]),
                on_screen_text=str(s["on_screen_text"]),
                voiceover_hint=(s.get("voiceover_hint") if s.get("voiceover_hint") else None),
            )
        )
    return Plan(
        title_idea=str(data.get("title_idea") or ""),
        genre=str(style.get("genre") or "other"),
        pace=str(style.get("pace") or "medium"),
        mood=list(style.get("mood") or []),
        scenes=scenes,
        music_sfx=list(data.get("music_sfx") or []),
        hashtags=list(data.get("hashtags") or []),
    )

