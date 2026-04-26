from __future__ import annotations

import json
import os
import re
from pathlib import Path

from src.llm.factory import get_default_model, get_provider
from src.llm.types import ChatMessage

from .types import Mode, Plan, PlanScene, Script


_PROMPT_CACHE: dict[str, str] = {}
_CONFIG_CACHE: dict[str, dict] = {}


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


def _read_config_file(filename: str) -> dict:
    base = Path(os.environ.get("PROMPTS_DIR", str(_repo_root() / "prompts")))
    path = base / filename
    if not path.exists():
        raise FileNotFoundError(f"找不到設定檔：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_config(name: str = "prompts_config") -> dict:
    """
    統一配置入口（prompt 檔名、次數限制、溫度、重試等）。
    預設讀 prompts/config.json，可用環境變數 PROMPTS_CONFIG_FILE 覆寫檔名。
    """
    mapping = {"prompts_config": os.environ.get("PROMPTS_CONFIG_FILE", "config.json")}
    if name not in mapping:
        raise ValueError(f"Unknown config name: {name}")
    if name not in _CONFIG_CACHE:
        _CONFIG_CACHE[name] = _read_config_file(mapping[name])
    return _CONFIG_CACHE[name]


def _cfg(path: str, default=None):
    cur = get_config("prompts_config")
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def get_prompt(name: str) -> str:
    """
    name:
      - script_system
      - plan_system
      - other_information
    """
    mapping = {
        "script_system": str(_cfg("paths.script_system_prompt", "script_system_prompt.txt")),
        "plan_system": str(_cfg("paths.plan_system_prompt", "plan_system_prompt.txt")),
        "other_information": str(_cfg("paths.other_information_prompt", "other_information_prompt.txt")),
        "script_self_review": str(_cfg("paths.script_self_review_prompt", "script_self_review_prompt.txt")),
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
            # 可選：呼叫預算（避免無止境重試/連鎖）
            # budget = {"remaining": int}
            budget = getattr(_chat_json, "_budget", None)
            if isinstance(budget, dict) and isinstance(budget.get("remaining"), int):
                if budget["remaining"] <= 0:
                    raise RuntimeError("LLM call budget exhausted")
                budget["remaining"] -= 1
            r = provider.chat(messages, model=model, temperature=temperature, extra={"format": "json"})
            return _json_from_llm(r.content)
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("LLM JSON parse failed")


def _script_json_max_tries() -> int:
    v = _cfg("script.json_parse_retry.max_tries", 3)
    try:
        v = int(v)
    except Exception:
        v = 3
    return max(1, min(v, 8))

_QUALITY_CACHE: dict[str, dict] = {}


def _read_quality_rules_file(filename: str) -> dict:
    base = Path(os.environ.get("PROMPTS_DIR", str(_repo_root() / "prompts")))
    path = base / filename
    if not path.exists():
        raise FileNotFoundError(f"找不到品質規則檔案：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_quality_rules(name: str = "script_quality_rules") -> dict:
    mapping = {
        "script_quality_rules": os.environ.get(
            "SCRIPT_QUALITY_RULES_FILE",
            str(_cfg("paths.script_quality_rules", "script_quality_rules.json")),
        )
    }
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
    if not isinstance(body, list):
        raise ValueError(f"Invalid script.body: expected list, got {type(body).__name__}")
    body = [str(x).strip() for x in body if str(x).strip()]
    # 容錯：模型偶爾會輸出 >6 句或 <6 句，這裡先做最佳努力正規化，避免整條流程直接崩潰。
    if len(body) > 6:
        # 保留前 5 句，把剩下的合併成第 6 句
        tail = "；".join(body[5:]).strip("；")
        body = [*body[:5], tail or body[5]]
    elif len(body) < 6:
        # 先嘗試把較長的句子用常見標點拆開補足
        parts: list[str] = []
        for s in body:
            # 先用較強斷點拆
            for p in re.split(r"[。！？!?；;]+", s):
                p = p.strip()
                if p:
                    parts.append(p)
        body = parts
        # 仍不足就用最後一句做輕量補齊（避免空字串）
        while len(body) < 6 and body:
            body.append(body[-1])
        body = body[:6]
    if len(body) != 6:
        raise ValueError(f"Invalid script.body after normalize: expected 6 items, got {len(body)}")
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
        out.append(
            _chat_json(
                provider,
                messages=msgs,
                model=model,
                temperature=temperature,
                max_tries=_script_json_max_tries(),
            )
        )
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
    return _chat_json(
        provider,
        messages=msgs,
        model=model,
        temperature=temperature,
        max_tries=_script_json_max_tries(),
    )


def generate(topic: str, *, mode: Mode = "script", model: str | None = None) -> Script | Plan:
    provider = get_provider()
    model = model or get_default_model()

    system = (SCRIPT_SYSTEM_PROMPT if mode == "script" else PLAN_SYSTEM_PROMPT) + OTHER_INFORMATION_PROMPT
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=f"主題：{topic}"),
    ]

    if mode == "script":
        # 呼叫上限（避免候選 * 重試 + 自評 * 重試 造成大量請求）
        # 估算：每個候選最多 max_tries 次；自評最多 max_tries 次；再加少量保底
        max_calls = int(os.environ.get("SCRIPT_MAX_LLM_CALLS", str(_cfg("script.max_llm_calls", 12))))
        max_calls = max(3, min(max_calls, 60))
        _chat_json._budget = {"remaining": max_calls}  # type: ignore[attr-defined]

        n = int(os.environ.get("SCRIPT_N_CANDIDATES", str(_cfg("script.n_candidates", 3))))
        n = max(1, min(n, 6))

        candidates: list[dict] = []
        try:
            # 先生成多個候選版本
            candidates = _generate_script_candidates(
                provider,
                model=model,
                topic=topic,
                system=system,
                n=n,
                temperature=float(_cfg("script.candidate_temperature", 0.7)),
            )
        except Exception:
            candidates = []

        # 若候選不足（例如 budget 用完或解析一直失敗），直接走保底一次生成
        if not candidates:
            data = _chat_json(
                provider,
                messages=messages,
                model=model,
                temperature=0.6,
                max_tries=min(2, _script_json_max_tries()),
            )
            return _script_from_data(data)

        # 讓模型自評挑最佳/合併（可配置開關；避免請求爆炸，品質規則已在自評 prompt 內）
        if bool(_cfg("script.self_review.enabled", True)):
            try:
                merged = _self_review_and_merge_script(
                    provider,
                    model=model,
                    topic=topic,
                    candidates=candidates,
                    temperature=float(_cfg("script.self_review.temperature", 0.35)),
                )
                script = _script_from_data(merged)
                if not _is_script_metadata_bad(merged) and not _is_script_generic(script.hook, script.body, script.ending):
                    return script
            except Exception:
                pass

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
        data = _chat_json(
            provider,
            messages=messages,
            model=model,
            temperature=0.6,
            max_tries=min(2, _script_json_max_tries()),
        )
        return _script_from_data(data)

    data = _chat_json(provider, messages=messages, model=model, temperature=0.6, max_tries=_script_json_max_tries())

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

