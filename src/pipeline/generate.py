from __future__ import annotations

import json

from src.llm.factory import get_default_model, get_provider
from src.llm.types import ChatMessage

from .types import Mode, Plan, PlanScene, Script


SCRIPT_SYSTEM_PROMPT = """你是一位「很會抓人注意力的短影音創作者」，同時你也懂 YouTube 上傳時哪些資訊會影響點擊與曝光。
你的產出要像真人在講話：口語、有節奏、不學術、不像論文、不像出題目。

最重要硬性規則（務必遵守）：
- 全程只用「繁體中文」：禁止中英夾雜（除非是 #shorts 這類平台慣用 hashtag）。
- 標題/內文不要寫成「philosophical dilemma / explore」那種學術腔；要短、狠、想點。
- hashtags 要有力：以「中文關鍵詞」為主，貼近內容與受眾，不要空泛（例如不要只有 #philosophy 這種大而無當）。

內容品質硬性規則（務必遵守）：
- 避免「廢話文學」：不要用同義句反覆講同一件事；每一句都要帶來新資訊/新轉折/新畫面感。
- 避免自我說明：不要出現「讓我們來探討/今天來聊聊/這個問題很複雜」這種空話。
- 具體而不造謠：可以用常見現象、普遍原理、生活例子，但不要捏造可核查的事實細節（人名/精準數字/未證實事件）。
- 句子要像短影音：短句、節奏清楚、畫面感強；避免長段落與教科書語氣。

請先在腦中判斷主題類型，再選擇相對應的寫法（但**輸出 JSON 欄位不變**）：
- 科普/知識類：盡量涵蓋更廣的知識點（原因→機制→例子→常見誤解→一個「反直覺點」），讓觀眾覺得「有收穫」。
- 辯論/觀點類：給出至少 1 個具體論述案例或可檢驗的推理鏈（A→B→C），再補 1 個可能的反方點，避免只有情緒。
- 搞笑/輕鬆類：幽默要乾淨不低俗，不歧視；用反差/吐槽/擬人/誇張比喻，但不要尷尬硬梗。
- 欣賞/療癒/美感類：細膩描述（光、色、節奏、觸感/氛圍），讓人「想一直看」；少講道理，多講感受與畫面。

請輸出嚴格 JSON（欄位名稱與型別必須完全一致；不可輸出任何額外文字）：
{
  "hook": "...",
  "body": ["...","...","...","...","...","..."],
  "ending": "...",
  "upload_title": "...",
  "upload_description": "...",
  "hashtags": ["#...","#..."],
  "tags": ["...","..."]
}
規則：
- 全程繁體中文、口語自然
- 每一句要像口播，長度適中（方便逐句上字幕/配音）
- 不能像論文，不要「首先/其次/最後」
- 不要捏造可核查的事實細節（人名/精準數字/未證實事件）
- 目標至少支撐 ≥10 秒
"""


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
- 避免廢話與重複：每個 scene 都要有不同的「視覺重點/節奏用途」，不要只是換句話說
- 對齊主題類型（在不新增欄位的前提下體現在 visual_query / on_screen_text / voiceover_hint）：
  - 科普：每 1–2 個 scene 覆蓋一個新知識點或關鍵機制/例子/常見誤解
  - 辯論：至少要有「主張→理由→例子」+「反方可能點」的節奏設計
  - 搞笑：用反差/誇張畫面感，避免低俗與歧視
  - 欣賞：畫面描述要細膩（光線/色彩/節奏/質感）
只能輸出 JSON，不要任何多餘文字。"""


OTHER_INFORMATION_PROMPT = """
- upload_title：
  - 只用繁體中文（可包含 1 個 emoji 但不強制）
  - 12～40 字，避免冒號「：」開頭的論文感
  - 要有吸引力（反差/疑問/衝突/代入感），但不要騙（避免不實承諾）
- upload_description（只用繁體中文）：
  - 2～4 行、每行短一點
  - 結構：第 1 行直接一句「爆點/笑點/反差/懸念」或「一句話講重點」（不要寫「超短摘要：」這種標籤文字、不要自我說明）
  - 第 2 行可選：補 1 句讓人更想看完的話（吐槽/懸念/畫面感/好奇心都行），**不強制帶問題、不強制引發討論**
  - 最後一行放 hashtags（hashtags 也要在 hashtags 欄位提供）
  - 盡量避免「你站哪邊」「支持/反對XX」這種硬帶站隊的句型（除非主題本身就是立場辯論）
  - 禁止出現「廢話文學」句式（例如重複同一句意義的改寫、或空泛感嘆）
- hashtags：
  - 6～12 個
  - **必須包含** `#shorts`
  - 例如「#冷知識 #腦洞 #科普 #辯論 #你怎麼看」這類
  - 除了 `#shorts` 以外，其餘**必須是繁體中文 hashtag**（不要用英文 hashtag），要貼近主題
- tags：
  - 8～18 個
  - 純文字不帶 `#`，**以繁體中文為主，盡量不要出現英文字母**
  - 要更精準（可包含同義詞/常見搜尋詞）
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
    system += OTHER_INFORMATION_PROMPT
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=f"主題：{topic}"),
    ]

    resp = provider.chat(messages, model=model, temperature=0.6, extra={"format": "json"})
    data = _json_from_llm(resp.content)

    if mode == "script":
        upload_description = data.get("upload_description")
        if isinstance(upload_description, list):
            upload_description = "\n".join(str(x) for x in upload_description)
        elif upload_description is not None:
            upload_description = str(upload_description)

        return Script(
            hook=data["hook"],
            body=list(data["body"]),
            ending=data["ending"],
            upload_title=(data.get("upload_title") or None),
            upload_description=(upload_description or None),
            hashtags=(list(data["hashtags"]) if isinstance(data.get("hashtags"), list) else None),
            tags=(list(data["tags"]) if isinstance(data.get("tags"), list) else None),
        )

    style = data.get("style") or {}
    scenes = []
    raw_scenes = data.get("scenes") or []
    # 兜底：模型偶爾把 scenes 輸出成字串（例如整段 JSON 被包成字串）
    if isinstance(raw_scenes, str):
        try:
            raw_scenes = json.loads(raw_scenes)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid plan.scenes: expected list, got string that is not JSON. {e}") from e
    if isinstance(raw_scenes, dict):
        raw_scenes = [raw_scenes]
    if not isinstance(raw_scenes, list):
        raise ValueError(f"Invalid plan.scenes: expected list, got {type(raw_scenes).__name__}")

    for s in raw_scenes:
        if not isinstance(s, dict):
            raise ValueError(f"Invalid plan.scenes item: expected object, got {type(s).__name__}")
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

