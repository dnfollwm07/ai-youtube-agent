# AI YouTube Agent（AIIS）工作空間說明

本儲存庫用於實作 **Autonomous AI Influencer Agent System（AIIS）** 的 MVP 到完整迭代版本：讓「AI 創作者智能體」在真實平台（優先 YouTube Shorts）中完成閉環：

**Trend → Topic/Strategy → Content → (Media) → Publish → Feedback → Strategy Update → Repeat**

> 重要：我們已決定**前期採用「人工審核後發佈（Human-in-the-loop）」**來降低平台政策/審核/風控與版權風險；當流程穩定後再逐步放權到抽樣審核，最終盡可能自動化。

---

## 1. 目標與原則

### 1.1 系統目標

- **自主發現潛在爆點話題**（Reddit / YouTube Trending / Google Trends 等訊號）
- **生成可發佈內容**（先腳本，後分鏡與影片）
- **發佈到 YouTube Shorts**
- **收集互動與回饋數據**（views/likes/comments，盡可能擴展到 retention）
- **基於回饋持續優化策略**（長期記憶 + 策略演化）

### 1.1.1 系統範圍

- **系統包含**：熱點數據採集、選題與內容策略決策、LLM 驅動內容生成、（後續）影片生成、YouTube 發佈、互動數據收集、評論/情緒分析、策略更新與長期記憶
- **系統不包含**：完全無監控的大規模生產部署；TikTok／抖音自動發佈（API 限制）；高成本 AI 影片模型訓練

### 1.2 核心理念

本專案的「核心資產」不是一次性的內容生成，而是能在真實環境裡持續循環的智能體系統：

- 真實發佈
- 真實回饋
- 持續優化

### 1.3 我們接受的現實約束

- 平台政策/審核/風控是環境的一部分，會影響曝光與穩定性
- 「大量量產發佈」**技術上可做**，但平台是否長期容忍、以及是否分發穩定**不保證**
- 最終目標應表述為：**在不觸發風控與版權風險的前提下，逐步提頻並提升長期指標**

---

## 2. 分期路線（按討論落地版）

### Phase 1：MVP 閉環（優先級最高）

目的：先跑通「發佈與回收數據」，讓後續迭代有真實回饋。

最小閉環：

- 趨勢／選題（可先手動或簡化為單源訊號）
- LLM 生成腳本（結構化：hook/body/ending）
- 簡單媒體合成（TTS + 單圖／簡單影片 + ffmpeg）
- **人工審核**（合規／版權／品質閘門）
- 上傳到 YouTube
- 拉取基礎指標與評論
- 進行最簡單的回饋總結與策略調整（啟發式即可）

### Phase 2：表現提升（更像「可競爭內容」）

- scene-based 分鏡輸出
- 自動素材檢索（如 Pexels）與多場景拼接
- 動態字幕、節奏、轉場模板多樣化
- 更系統的選題打分與內容風格探索

### Phase 3：學習系統（長期策略演化）

- 回饋建模：情緒／主題／embedding 聚類等
- 策略記憶：沉澱高表現模式、失敗模式、風格演進軌跡
- 自動實驗與對照：A/B（弱形式即可）+ 指標驅動的策略選擇

---

## 3. 目前儲存庫狀態

### 3.1 目錄與檔案

- `src/youtube_auth.py`：YouTube OAuth 授權與 `youtube` service 構建
- `main.py`：目前為空（後續會成為入口或 CLI／服務啟動點）
- `auth/client_secret.json`：Google OAuth 用戶端密鑰（**敏感檔案**）

### 3.2 YouTube 授權的關鍵行為

`src/youtube_auth.py` 會在本地生成／讀取 `token.pickle`（OAuth token 快取）以復用登入狀態。

---

## 4. 人工審核發佈（Human-in-the-loop）流程約定

### 4.1 為什麼要人工審核

在帳號早期，平台對異常自動化行為更敏感；同時內容與素材更容易踩合規／版權雷。人工審核能顯著降低：

- 內容政策風險（誤導、敏感、攻擊性、危險行為等）
- 版權／復用內容風險（音樂、影片素材、搬運剪輯）
- 自動化風控風險（新號高頻模板化發佈）

### 4.2 審核角色的邊界（「最小干預」）

人工審核者只做「發佈閘門」，盡量不替 AI 做創作決策：

- 允許發佈／退回修改
- 刪除或改寫少量高風險句子（合規需要時）
- 確認素材／音樂來源可用（授權／可商用）
- 不重新選題
- 不重寫腳本（除非必須合規）

### 4.3 建議的最小審核清單（10 條以內）

1. 是否涉及仇恨／騷擾／暴力／自殘／未成年／性暗示／危險挑戰等高風險內容
2. 是否包含明確誤導性的醫療／財務結論或保證性承諾
3. 標題／字幕是否誇張到可能構成欺騙性（clickbait 過界）
4. 是否使用了未授權音樂／他人影片片段／可疑素材
5. 是否大量重複模板（標題、描述、字幕樣式過於一致）
6. 是否有明顯事實錯誤（能快速校驗的）
7. 是否包含個人隱私資訊（電話號碼、住址等）
8. 是否包含可能導致被檢舉的攻擊性措辭
9. 影片時長與畫面比例是否滿足 Shorts 的常見規範
10. 是否「像創作者」而不是「像機器批量投放」（節奏、表現自然度）

---

## 5. 規劃中的模組邊界（用於後續實作與提問對齊）

> 下面是概念模組，未必已全部落地到程式碼結構；用於我們後續討論時統一口徑。

- **Trend Collection Layer**：採集熱點訊號（Reddit/YouTube/Trends）
- **Topic & Strategy Agent**：選題與敘事角度決策（LLM + heuristic scoring）
- **Topic & Strategy Agent**：選題與敘事角度決策（LLM + heuristic scoring）
- **Content Creation Agent**：生成腳本／分鏡（結構化輸出）
- **Media Generation Pipeline**：TTS、素材檢索、ffmpeg 合成、字幕與轉場
- **Publishing Agent**：YouTube 上傳與發佈管理
- **Feedback Collection Layer**：拉取 views/likes/comments 等
- **Feedback Learning Agent**：從回饋歸納規律、提出下一輪策略
- **Strategy Memory**：長期記錄（topic 歷史、指標、策略演化）

---

## 6. 安全與憑證約定（非常重要）

### 6.1 本儲存庫包含敏感檔案

`auth/client_secret.json` 與執行時生成的 `token.pickle` 都屬於敏感資訊。

約定：

- **不要把敏感檔案提交到公開儲存庫**
- 分享程式碼時請先移除／替換為示例檔案（如 `client_secret.example.json`）
- 任何日誌／報錯輸出也不要把 token 內容列印出來

---

## 7. 未來建議的目錄規劃（可逐步演進）

（僅作為後續落地時的方向）

- `src/agents/`：strategy/content/feedback 等 agent
- `src/integrations/`：youtube、reddit、trends、pexels 等外部 API
- `src/pipeline/`：media 生成與 ffmpeg 組裝
- `src/storage/`：SQLite/PG、記憶與指標儲存
- `src/scheduler/`：任務調度（cron/APScheduler）
- `data/`：本地資料庫、快取（不入庫）
- `outputs/`：生成的影片與中間產物（不入庫）

---

## 8. 我們後續溝通的「預設前提」

當你在本工作空間繼續問我問題時，預設前提為：

- 按 `draft.txt` 的 AIIS 藍圖推進
- 採用分期迭代（Phase 1 → 2 → 3）
- Phase 1 期間使用 **人工審核後發佈（human-in-the-loop）**
- 目標是「可持續迭代與真實回饋」，而非一次性爆款或無限量產

