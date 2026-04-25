import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.llm.factory import get_default_model, get_provider
from src.llm.types import ChatMessage


PROMPT = """你是一位「擅長抓住網路爆點的網紅創作者」（短影音腳本作者 + 節奏導演）。
你的任務是：針對使用者給的主題，生成一支能博得流量的短影音口播腳本，風格要像在跟觀眾講八卦/時事熱議，語氣有張力、有情緒帶動、能引發評論區討論，但不得捏造明確可核查的事實細節（避免造謠）。

腳本長度要求：
- 目標至少支撐「≥20 秒」短影片（口播節奏自然，不要一句就結束）。
- hook 必須像 0-1 秒就能抓住人（反差、疑問、衝突、驚訝、代入感其一即可）。
- body 需要足夠資訊密度與轉折，讓觀眾願意看完並留言。
- ending 要強 CTA（引導留言/站隊/投票式提問），避免空泛收尾。

輸出格式（只能輸出 JSON，不能有任何額外文字；欄位名稱與型別必須完全一致）：
{
  "hook": "一句話爆點開場（繁體中文）",
  "body": [
    "第1句：延伸爆點/丟出關鍵衝突",
    "第2句：補一個背景或常識（不可瞎編具體數字/人名細節）",
    "第3句：提出一個更尖銳的反問或轉折",
    "第4句：帶入觀眾視角（你可能也遇過...）",
    "第5句：給一個簡短結論/立場（可偏主觀，但要像網紅）",
    "第6句：收束並鋪墊留言戰場"
  ],
  "ending": "一句話強 CTA，讓人想留言（繁體中文）"
}

語言：全程使用繁體中文。"""


def main():
    parser = argparse.ArgumentParser(description="LLM 冒煙測試（預設走 Ollama 本地）")
    parser.add_argument("--topic", required=True, help="主題，例如：AI 取代工作")
    parser.add_argument("--provider", default=None, help="provider（預設讀 LLM_PROVIDER）")
    parser.add_argument("--model", default=None, help="model（預設讀 LLM_MODEL 或 llama3）")
    args = parser.parse_args()

    provider = get_provider(args.provider)
    model = args.model or get_default_model()

    messages = [
        ChatMessage(role="system", content=PROMPT),
        ChatMessage(role="user", content=f"主題：{args.topic}"),
    ]

    resp = provider.chat(messages, model=model, temperature=0.4, extra={"format": "json"})
    print(resp.content)

    # Best-effort: Ollama/模型偶爾會在 JSON 後追加解釋文字；這裡嘗試抽出第一段 JSON 物件再驗證
    text = resp.content.strip()
    start = text.find("{")
    end = text.rfind("}")
    candidate = text if start == -1 or end == -1 or end <= start else text[start : end + 1]

    try:
        json.loads(candidate)
    except json.JSONDecodeError:
        raise SystemExit("輸出不是合法 JSON（請調整 prompt 或模型），或改用更嚴格的輸出格式約束。")


if __name__ == "__main__":
    main()

