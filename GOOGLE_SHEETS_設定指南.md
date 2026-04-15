# Google Sheets 開通權限指南

## 步驟 1：建立 Google Cloud 專案

1. 前往 https://console.cloud.google.com/
2. 點選左上角「選取專案」→「新增專案」
3. 輸入專案名稱（例如：`mom-analytics`）→ 點「建立」

---

## 步驟 2：啟用 Google Sheets API

1. 在左側選單點「API 和服務」→「程式庫」
2. 搜尋 `Google Sheets API`
3. 點進去 → 點「啟用」

---

## 步驟 3：建立服務帳戶（Service Account）

1. 左側選單點「API 和服務」→「憑證」
2. 點「建立憑證」→「服務帳戶」
3. 填入帳戶名稱（例如：`sheets-reader`）→ 點「建立並繼續」
4. 角色選「Editor」→ 點「繼續」→ 點「完成」

---

## 步驟 4：下載 JSON 金鑰

1. 在憑證頁面，點剛建立的服務帳戶
2. 點「金鑰」分頁 → 「新增金鑰」→「建立新的金鑰」
3. 選「JSON」格式 → 點「建立」
4. 檔案會自動下載（例如 `mom-analytics-xxxxx.json`）
5. **將此檔案複製到** `backend/` 資料夾，並更名為 `credentials.json`

---

## 步驟 5：分享 Google Sheets 給服務帳戶

1. 打開你的 Google Sheets
2. 點右上角「共用」按鈕
3. 在「新增使用者」欄位，輸入服務帳戶的 email
   - email 格式像這樣：`sheets-reader@mom-analytics.iam.gserviceaccount.com`
   - 可在 Google Cloud Console → 憑證 → 服務帳戶頁面找到
4. 設定為「檢視者」權限 → 點「傳送」

---

## 步驟 6：取得 Spreadsheet ID

Google Sheets 的網址格式：
```
https://docs.google.com/spreadsheets/d/【這裡就是 Spreadsheet ID】/edit
```

例如：
```
https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit
                                        ↑ 複製這段
```

---

## 步驟 7：設定 .env 檔案

編輯 `backend/.env`：

```
GOOGLE_CREDENTIALS_FILE=credentials.json
SPREADSHEET_ID=貼上你的 Spreadsheet ID
ANTHROPIC_API_KEY=你的 Claude API Key
```

---

## Google Sheets 欄位格式建議

### 工作表一：「銷售記錄」
| 日期 | 商品名稱 | 類別 | 數量 | 單價 | 金額 |
|------|---------|------|------|------|------|
| 2024-04-01 | 有機蘋果 | 水果 | 5 | 120 | 600 |

### 工作表二：「商品資料」
| id | name | category | price | stock | sold |
|----|------|----------|-------|-------|------|
| P001 | 有機蘋果 | 水果 | 120 | 150 | 89 |

---

## 取得 Anthropic API Key

1. 前往 https://console.anthropic.com/
2. 註冊 / 登入帳號
3. 點「API Keys」→「Create Key」
4. 複製 key 貼到 `backend/.env` 的 `ANTHROPIC_API_KEY=`

---

## 完成後啟動系統

```bash
# 方法一：一鍵啟動
./start.sh

# 方法二：分別啟動
# 後端
cd backend && python3 -m uvicorn main:app --reload --port 8000

# 前端（新終端機）
cd frontend && npm run dev
```

開啟瀏覽器：http://localhost:5173
