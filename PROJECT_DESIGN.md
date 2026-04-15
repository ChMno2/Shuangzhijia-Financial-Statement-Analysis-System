# 雙之家商業智慧平台 — 專案設計文件

> 版本：v1.0 | 日期：2026-04-15 | 狀態：設計階段

---

## 一、專案背景與目標

### 公司簡介
- **公司名稱**：雙之家（Sou no Ie）
- **業態**：日本進口商品零售店
- **商品類別**：服飾、醫藥品、食品、雜貨
- **營業點**：光復店、新埔店（多點管理）

### 核心痛點
| 痛點 | 現況 | 目標 |
|------|------|------|
| 資料分析耗時 | 手動查 Excel | AI 自動分析 |
| 進貨決策憑感覺 | 無數據支撐 | 結合銷售趨勢+外部資訊 |
| 看不懂市場趨勢 | 無情報來源 | AI 搜尋日本/台灣潮流 |
| 週報撰寫費力 | 手動整理 | AI 自動生成 |
| 資料外洩風險 | 無保護機制 | JWT 後台登入驗證 |

### 最終目標
打造一個 **AI 驅動的商業智慧平台**，讓非技術背景的店主能透過自然語言對話，獲得精準的商業洞察、進貨建議、市場趨勢分析，並自動生成週報。

---

## 二、系統現況（已完成）

### 技術架構
- **後端**：Python FastAPI + SQLite + Google Drive API
- **前端**：React + Vite + TailwindCSS + Recharts
- **AI**：Anthropic Claude API（claude-sonnet-4-6）
- **認證**：JWT Bearer Token（pbkdf2_sha256 密碼雜湊）

### 已實作功能
| 功能 | 狀態 |
|------|------|
| 後台登入系統（JWT） | ✅ 完成 |
| Google Drive Excel 讀取 | ✅ 完成 |
| 儀表板（營收、類別圓餅圖） | ✅ 完成 |
| 銷售報表（30/60/90天 + 自訂） | ✅ 完成 |
| 成本利潤分析 | ✅ 完成 |
| AI 問答（固定 context 版） | ✅ 完成（待升級） |
| AI 週報（含歷史儲存） | ✅ 完成（待升級） |
| 對話歷史持久化 | ✅ 完成 |
| 啟動自動抓取最新資料 | ✅ 完成 |
| 每小時自動更新 | ✅ 完成 |

### 現有 AI 問答限制
- 傳固定文字快照給 LLM，無法動態查詢
- 問題超出快照範圍就無法回答
- 無外部資訊（天氣、潮流、市場）

---

## 三、目標架構：Multi-Agent 商業智慧系統

### 架構總覽

```
使用者自然語言輸入
        ↓
┌────────────────────────────────────────────────┐
│            Orchestrator Agent（主控）            │
│                                                │
│  職責：                                        │
│  1. 理解問題意圖與複雜度                        │
│  2. 決定需要哪些子 Agent                        │
│  3. 規劃子 Agent 執行順序（處理相依關係）        │
│  4. 彙整所有結果                               │
│  5. 生成最終有原因、有數據的完整回答            │
└──┬───────┬────────┬────────┬────────┬──────────┘
   ↓       ↓        ↓        ↓        ↓
  [A1]   [A2]     [A3]     [A4]     [A5]
```

### 子 Agent 詳細設計

#### A1：內部資料 Agent
| 項目 | 說明 |
|------|------|
| 職責 | 查詢本地 SQLite，回答內部銷售相關問題 |
| 資料來源 | 本地 SQLite（由 Google Drive Excel 同步） |
| 使用工具 | `query_sales`、`compare_periods`、`get_trend`、`get_product_list` |
| 可回答 | 銷售額、數量、毛利率、商品排行、類別分析、地點比較 |

#### A2：天氣感知 Agent
| 項目 | 說明 |
|------|------|
| 職責 | 取得台灣天氣預報，結合歷史天氣與銷售相關性 |
| 資料來源 | OpenWeatherMap API |
| 使用工具 | `get_weather_forecast`、`get_weather_history` |
| 可回答 | 本週/下週天氣、哪種天氣下哪類商品熱銷 |

#### A3：市場研究 Agent
| 項目 | 說明 |
|------|------|
| 職責 | 搜尋台灣與全球市場資訊 |
| 資料來源 | Brave Search API / Serper |
| 使用工具 | `web_search(lang=zh)`、`fetch_url`、`summarize_page` |
| 可回答 | 台灣消費趨勢、熱銷品類、社群討論話題 |

#### A4：日本潮流 Agent
| 項目 | 說明 |
|------|------|
| 職責 | 專門搜尋日本流行趨勢（與本業最相關） |
| 資料來源 | 日語 Web 搜尋、日本電商/SNS |
| 使用工具 | `web_search(lang=ja)`、`fetch_url` |
| 可回答 | 日本當季流行服飾、熱銷食品、藥妝趨勢、SNS 爆款商品 |

#### A5：進貨建議 Agent（整合型）
| 項目 | 說明 |
|------|------|
| 職責 | 整合 A1+A2+A4 結果，輸出具體進貨建議 |
| 資料來源 | 接收其他 Agent 輸出 |
| 使用工具 | 無（純推理） |
| 可回答 | 具體進貨品項、建議數量、預期售價、進貨時機 |

#### A6：報表生成 Agent（整合型）
| 項目 | 說明 |
|------|------|
| 職責 | 將所有分析結果格式化為結構化報表 |
| 資料來源 | 接收所有子 Agent 輸出 |
| 使用工具 | 無（純生成） |
| 可回答 | 完整 Markdown 報表、可下載 PDF/MD |

---

## 四、問題情境與 Agent 協作流程

### 情境 1：「本週天氣如何？應該進什麼貨？」

```
Orchestrator 判斷需要：A1（歷史銷售）+ A2（天氣）+ A5（進貨建議）

執行順序（平行）：
  A1: 查過去同氣候週的銷售數據 ──┐
                                  ├──→ A5: 整合 → 「建議加購雨衣、暖身商品 X 件」
  A2: 取得本週天氣預報 ───────────┘
```

### 情境 2：「日本近期流行什麼？我們有沒有相關商品？」

```
執行順序：
  A4: 搜尋日本潮流 ─────────────────┐
                                     ├──→ Orchestrator 交叉比對 → 回答
  A1: 取得我們現有商品清單 ──────────┘
```

### 情境 3：「找出台灣熱銷的日本進口食品，我們沒賣過的，給我完整報表」

```
執行順序（部分依賴）：
  A3: 搜尋台灣熱銷日本食品 ──────────────┐
  A4: 確認日本那邊也熱門 ────────────────┤
  A1: 取得我們賣過的商品（用來排除）────── ┤
                                           ├──→ A6: 生成「新品引進機會報表」
  Orchestrator: 交叉比對，找出空缺商品 ────┘
```

### 情境 4：「幫我生成本週 AI 週報」

```
現況（單一 LLM 呼叫）→ 升級為 Multi-Agent：

  A1: 完整內部數據分析 ──────────┐
  A2: 本週天氣概況 ──────────────┤
  A3: 本週市場新聞 ──────────────┤──→ A6（報告撰寫 Agent）→ 週報
  A4: 日本近期潮流 ──────────────┘
```

---

## 五、Tool 完整清單

### 設計原則
> 少量、彈性、參數化。4~6 個通用工具覆蓋 90% 問題，LLM 自行決定呼叫方式與參數。

### 內部資料工具

| Tool 名稱 | 參數 | 回傳 |
|-----------|------|------|
| `query_sales` | `days`, `category`, `location`, `product`（模糊）, `group_by`, `sort_by`, `sort_order`, `limit` | 銷售明細陣列（含數量、毛利率） |
| `compare_periods` | `metric`, `days_a`, `days_b`, `group_by` | 兩期對比表 |
| `get_trend` | `target`（商品/類別）, `days`, `granularity`（week/month） | 時序趨勢資料 |
| `get_product_list` | `category`（可選） | 所有商品清單 |

### 外部資料工具

| Tool 名稱 | 參數 | 回傳 |
|-----------|------|------|
| `web_search` | `query`, `lang`（zh/ja/en）, `num_results` | 搜尋結果摘要清單 |
| `fetch_url` | `url` | 頁面純文字內容 |
| `get_weather_forecast` | `city`（預設台北）, `days` | 逐日天氣預報 |
| `get_weather_history` | `city`, `start_date`, `end_date` | 歷史天氣紀錄 |

### 分析工具（選配 Phase 4）

| Tool 名稱 | 參數 | 回傳 |
|-----------|------|------|
| `correlate_weather_sales` | `weather_data`, `category` | 天氣與銷售相關係數 |
| `estimate_restock` | `product`, `trend`, `weather` | 建議進貨數量 |

---

## 六、技術選型

| 元件 | 選用方案 | 理由 |
|------|---------|------|
| AI 核心 | Anthropic Claude API（claude-sonnet-4-6） | 已有 API Key，支援 tool_use |
| Agent 框架 | Claude 原生 tool_use（無需外部框架） | 最少依賴，最穩定 |
| 本地資料庫 | SQLite | 輕量、無需伺服器、支援 SQL 查詢 |
| 資料來源 | Google Drive API（Excel 同步） | 現有設定 |
| 網路搜尋 | Brave Search API（免費方案） | 支援多語言、日語搜尋 |
| 天氣資料 | OpenWeatherMap API（免費方案） | 有台灣城市、7天預報 |
| 後端框架 | FastAPI（現有） | 維持不變 |
| 前端框架 | React + Vite + TailwindCSS（現有） | 維持不變 |
| 週報儲存 | SQLite（現有 reports.db） | 已實作 |
| 對話歷史 | SQLite（現有 chat_messages） | 已實作 |

---

## 七、資料庫設計（SQLite 升級）

### 現有（記憶體快取）→ 目標（本地持久化）

```sql
-- 銷售主表
CREATE TABLE sales (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        DATE    NOT NULL,
  product     TEXT    NOT NULL,
  category    TEXT,
  location    TEXT,
  revenue     REAL,
  quantity    INTEGER,
  unit_price  REAL,
  cost        REAL,
  margin_pct  REAL,
  sheet_name  TEXT,
  synced_at   TEXT
);

-- 支出表
CREATE TABLE expenses (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  date     DATE,
  item     TEXT,
  amount   REAL,
  category TEXT
);

-- 同步紀錄
CREATE TABLE sync_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  synced_at     TEXT NOT NULL,
  latest_date   TEXT,
  total_rows    INTEGER,
  status        TEXT
);

-- 索引（加速查詢）
CREATE INDEX idx_sales_date     ON sales(date);
CREATE INDEX idx_sales_category ON sales(category);
CREATE INDEX idx_sales_product  ON sales(product);
CREATE INDEX idx_sales_location ON sales(location);
```

### 同步策略
- **啟動時**：比對 sync_log 最新日期，只補新資料（增量）
- **每小時**：同上，增量更新
- **手動刷新**：`/api/refresh` 強制完整重新同步

---

## 八、實作路線圖

### Phase 1：資料層升級（基礎）
- [ ] 現有 pandas DataFrame → 寫入 SQLite
- [ ] 實作增量同步邏輯
- [ ] 設計並測試 4 個內部查詢 Tool
- [ ] 單 Agent + Tool 呼叫（取代固定 context）
- **預期效益**：AI 問答精準度大幅提升，可查任意時間範圍、任意商品

### Phase 2：外部感知（天氣 + 搜尋）
- [ ] 串接 OpenWeatherMap API
- [ ] 串接 Brave Search API
- [ ] 實作 `web_search`、`get_weather_forecast` 工具
- [ ] 測試天氣+銷售關聯問答
- **預期效益**：可回答「這週應該主打什麼商品」

### Phase 3：日本潮流 Agent
- [ ] 設計日語搜尋策略（關鍵字、目標網站）
- [ ] 實作 A4 日本潮流 Agent
- [ ] 與 A1 內部資料交叉比對
- **預期效益**：可回答「日本現在流行什麼，我們有沒有賣」

### Phase 4：完整 Multi-Agent + 週報升級
- [ ] 實作 Orchestrator Agent（主控層）
- [ ] 整合所有子 Agent
- [ ] 週報升級為 Multi-Agent 版（A1+A2+A3+A4 → A6）
- [ ] 新品引進機會報表功能
- **預期效益**：完整商業智慧平台

---

## 九、成本估算

### API 費用（月估）

| 服務 | 方案 | 月費 |
|------|------|------|
| Anthropic Claude | 按用量（sonnet-4-6） | 依使用量，約 $5–20 USD |
| Brave Search API | Free tier（2,000次/月） | $0 |
| OpenWeatherMap | Free tier（1,000次/日） | $0 |
| Google Drive API | Free（現有） | $0 |

### Token 節省估算
- **現況**（固定 context）：每次問答約 3,000–5,000 tokens
- **升級後**（Agent + Tool）：每次問答約 1,000–2,000 tokens（視問題複雜度）
- **節省比例**：約 40–60%

---

## 十、PPT 簡報大綱建議

1. **封面**：雙之家商業智慧平台 2.0
2. **背景與問題**：現有痛點、為何需要 AI
3. **系統現況**：已完成功能展示
4. **技術架構**：現有架構圖
5. **升級目標**：Multi-Agent 架構圖
6. **Agent 設計**：各子 Agent 職責與工具
7. **問題情境演示**：3 個使用情境流程圖
8. **技術選型**：選型表格與理由
9. **實作路線圖**：Phase 1–4 甘特圖
10. **成本效益分析**：ROI 估算
11. **Demo 截圖**：現有系統畫面

---

*文件更新紀錄*
- 2026-04-15：初版建立，涵蓋架構設計討論內容
