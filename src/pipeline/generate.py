from __future__ import annotations

import json
import os
import re
from pathlib import Path

from src.llm.factory import get_default_model, get_provider
from src.llm.types import ChatMessage

from .types import Mode, Plan, PlanScene, Script


_PROMPT_CACHE: dict[str, str] = {}


def _repo_root() -> Path:
    # src/pipeline/generate.py -> src/pipeline -> src -> repo_root
    return Path(__file__).resolve().parents[2]


def _read_prompt_file(filename: str) -> str:
    # 允許用環境變數覆寫 prompt 目錄位置（方便之後做外掛/版本化）
    base = Path(os.environ.get("PROMPTS_DIR", str(_repo_root() / "prompts")))
    path = base / filename
    if not path.exists():
        raise FileNotFoundError(
            f"找不到 prompt 檔案：{path}. 請建立它，或設定環境變數 PROMPTS_DIR 指向 prompt 目錄。"
        )
    return path.read_text(encoding="utf-8").strip() + "\n"


def get_prompt(name: str) -> str:
    """
    name:
      - script_system
      - plan_system
      - other_information
    """
    mapping = {
        "script_system": "script_system_prompt.txt",
        "plan_system": "plan_system_prompt.txt",
        "other_information": "other_information_prompt.txt",
        "script_self_review": "script_self_review_prompt.txt",
    }
    if name not in mapping:
        raise ValueError(f"Unknown prompt name: {name}")
    if name not in _PROMPT_CACHE:
        _PROMPT_CACHE[name] = _read_prompt_file(mapping[name])
    return _PROMPT_CACHE[name]


SCRIPT_SYSTEM_PROMPT = get_prompt("script_system")


PLAN_SYSTEM_PROMPT = get_prompt("plan_system")


OTHER_INFORMATION_PROMPT = get_prompt("other_information")
SCRIPT_SELF_REVIEW_PROMPT = get_prompt("script_self_review")


def _json_from_llm(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    candidate = text if start == -1 or end == -1 or end <= start else text[start : end + 1]
    return json.loads(candidate)


def _chat_json(provider, *, messages: list[ChatMessage], model: str, temperature: float, max_tries: int = 3) -> dict:
    last_err: Exception | None = None
    for _ in range(max_tries):
        try:
            r = provider.chat(messages, model=model, temperature=temperature, extra={"format": "json"})
            return _json_from_llm(r.content)
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("LLM JSON parse failed")

_QUALITY_CACHE: dict[str, dict] = {}


def _read_quality_rules_file(filename: str) -> dict:
    base = Path(os.environ.get("PROMPTS_DIR", str(_repo_root() / "prompts")))
    path = base / filename
    if not path.exists():
        raise FileNotFoundError(f"找不到品質規則檔案：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_quality_rules(name: str = "script_quality_rules") -> dict:
    mapping = {"script_quality_rules": os.environ.get("SCRIPT_QUALITY_RULES_FILE", "script_quality_rules.json")}
    if name not in mapping:
        raise ValueError(f"Unknown quality rules name: {name}")
    if name not in _QUALITY_CACHE:
        _QUALITY_CACHE[name] = _read_quality_rules_file(mapping[name])
    return _QUALITY_CACHE[name]


def _generic_patterns() -> list[str]:
    rules = get_quality_rules("script_quality_rules")
    pats = rules.get("generic_patterns") or []
    return [str(p) for p in pats]


def _is_script_metadata_bad(data: dict) -> bool:
    if not isinstance(data.get("upload_title"), str) or not data.get("upload_title", "").strip():
        return True
    if not isinstance(data.get("upload_description"), (str, list)) or not str(data.get("upload_description", "")).strip():
        return True
    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list) or not hashtags:
        return True
    tags = data.get("tags")
    if not isinstance(tags, list) or not tags:
        return True
    return False


def _is_script_generic(hook: str, body: list[str], ending: str) -> bool:
    if not isinstance(body, list) or len(body) != 6:
        return True
    if any(not (s or "").strip() for s in body):
        return True

    text = "\n".join([hook or "", *[str(x) for x in body], ending or ""])

    # 命中空話模板就不合格
    for p in _generic_patterns():
        if re.search(p, text):
            return True

    # body 過多弱開頭
    rules = get_quality_rules("script_quality_rules")
    weak_re = str(rules.get("weak_starts_regex") or "")
    if weak_re:
        weak_starts = sum(1 for s in body if re.match(weak_re, (s or "").strip()))
        if weak_starts >= 3:
            return True

    # 問句太多：容易灌水
    q_marks = text.count("？") + text.count("?")
    max_q = int(rules.get("max_question_marks_total") or 3)
    if q_marks > max_q:
        return True

    # 每句至少要有一個具體連接詞（避免只喊形容詞）
    evidence_tokens = [str(x) for x in (rules.get("evidence_tokens") or [])]
    require_each = bool(rules.get("require_evidence_token_each_line", True))
    if require_each and evidence_tokens:
        for s in body:
            if not any(tok in s for tok in evidence_tokens):
                return True

    # 重複句式（去掉標點後重複）
    norm = [re.sub(r"[，。！？!?、…\\s]", "", (s or "")) for s in body]
    if len(set(norm)) <= max(2, len(norm) - 3):
        return True

    min_unique = int(rules.get("min_unique_body_lines") or 4)
    if len(set(norm)) < min_unique:
        return True

    return False


def _script_from_data(data: dict) -> Script:
    body = data.get("body")
    if not isinstance(body, list) or len(body) != 6:
        raise ValueError(f"Invalid script.body: expected list with 6 items, got {type(body).__name__} len={len(body) if isinstance(body, list) else 'n/a'}")
    upload_description = data.get("upload_description")
    if isinstance(upload_description, list):
        upload_description = "\n".join(str(x) for x in upload_description)
    elif upload_description is not None:
        upload_description = str(upload_description)
    return Script(
        hook=str(data["hook"]),
        body=list(body),
        ending=str(data["ending"]),
        upload_title=(data.get("upload_title") or None),
        upload_description=((upload_description or None) if upload_description is not None else None),
        hashtags=(list(data["hashtags"]) if isinstance(data.get("hashtags"), list) else None),
        tags=(list(data["tags"]) if isinstance(data.get("tags"), list) else None),
    )


def _script_quality_score(data: dict) -> int:
    """
    分數越高越好（用於無法自評時的保底挑選）。
    """
    try:
        script = _script_from_data(data)
    except Exception:
        return -10_000

    score = 0
    if not _is_script_metadata_bad(data):
        score += 50
    if not _is_script_generic(script.hook, script.body, script.ending):
        score += 200

    # 連接詞越多越具體
    rules = get_quality_rules("script_quality_rules")
    evidence_tokens = [str(x) for x in (rules.get("evidence_tokens") or [])]
    text = "\n".join([script.hook, *script.body, script.ending])
    score += sum(text.count(tok) for tok in evidence_tokens)

    # 空話模板命中扣分
    for p in _generic_patterns():
        if re.search(p, text):
            score -= 80
    return score


def _generate_script_candidates(
    provider,
    *,
    model: str,
    topic: str,
    system: str,
    n: int,
    temperature: float,
) -> list[dict]:
    out: list[dict] = []
    for i in range(n):
        msgs = [
            ChatMessage(role="system", content=system),
            # 加一點點差異，讓模型更願意走不同寫法
            ChatMessage(role="user", content=f"主題：{topic}\n請給我版本 {i+1}。"),
        ]
        out.append(_chat_json(provider, messages=msgs, model=model, temperature=temperature, max_tries=3))
    return out


def _self_review_and_merge_script(
    provider,
    *,
    model: str,
    topic: str,
    candidates: list[dict],
    temperature: float,
) -> dict:
    review_user = json.dumps({"topic": topic, "candidates": candidates}, ensure_ascii=False)
    msgs = [
        ChatMessage(role="system", content=SCRIPT_SELF_REVIEW_PROMPT),
        ChatMessage(role="user", content=review_user),
    ]
    return _chat_json(provider, messages=msgs, model=model, temperature=temperature, max_tries=3)


def generate(topic: str, *, mode: Mode = "script", model: str | None = None) -> Script | Plan:
    provider = get_provider()
    model = model or get_default_model()

    system = (SCRIPT_SYSTEM_PROMPT if mode == "script" else PLAN_SYSTEM_PROMPT) + OTHER_INFORMATION_PROMPT
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=f"主題：{topic}"),
    ]

    if mode == "script":
        n = int(os.environ.get("SCRIPT_N_CANDIDATES", "3"))
        n = max(1, min(n, 6))

        # 先生成多個候選版本
        candidates = _generate_script_candidates(
            provider,
            model=model,
            topic=topic,
            system=system,
            n=n,
            temperature=0.7,
        )

        # 讓模型自評挑最佳/合併（最多 2 次，第二次更低溫、更強約束）
        merged: dict | None = None
        for t, extra_note in [(0.4, ""), (0.2, "\n注意：body 必須剛好 6 句；欄位不可缺；不可輸出任何多餘文字。")]:
            try:
                merged = _self_review_and_merge_script(
                    provider,
                    model=model,
                    topic=topic,
                    candidates=candidates,
                    temperature=t,
                )
                if extra_note:
                    # 若第一次失敗，補一個強提醒（不改 system prompt，避免維護分裂）
                    merged = _self_review_and_merge_script(
                        provider,
                        model=model,
                        topic=topic + extra_note,
                        candidates=candidates,
                        temperature=t,
                    )
                script = _script_from_data(merged)
                if not _is_script_metadata_bad(merged) and not _is_script_generic(script.hook, script.body, script.ending):
                    return script
            except Exception:
                merged = None

        # 校驗仍不合格：用本地打分挑候選保底（必須能通過 _script_from_data）
        best: dict | None = None
        best_score = -10_000_000
        for c in candidates:
            try:
                _script_from_data(c)
            except Exception:
                continue
            s = _script_quality_score(c)
            if s > best_score:
                best_score = s
                best = c
        if best is not None:
            return _script_from_data(best)

        # 最後保底：把原始 system prompt 再跑一次（避免全候選都壞掉）
        data = _chat_json(provider, messages=messages, model=model, temperature=0.6, max_tries=3)
        return _script_from_data(data)

    data = _chat_json(provider, messages=messages, model=model, temperature=0.6, max_tries=3)

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

