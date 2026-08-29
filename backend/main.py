"""
FastAPI 後端主程式 — 雙之家日記帳分析系統
"""
import os
import sqlite3
import asyncio
import base64
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import pandas as pd
import io

load_dotenv()

# ─────────────────────────────────────────
# SQLite 週報資料庫
# ─────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "reports.db")

def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()

_init_db()

from google_sheets import download_excel, get_recent_sheet_names, load_all_sales, load_all_expenses
from data_processor import build_dashboard_data, get_daily_detail, get_profit_report, build_period_summary
from llm_analyzer import analyze_with_llm, analyze_with_agent, analyze_with_agent_gemini, generate_weekly_report
from auth import verify_password, create_token, get_current_user, ADMIN_USERNAME, ADMIN_PASSWORD_HASH
from sales_db import init_sales_db, sync_from_dataframe

init_sales_db()

AUTO_REFRESH_MINUTES = int(os.getenv("AUTO_REFRESH_MINUTES", "60"))


async def _auto_refresh_loop():
    """背景任務：每隔 AUTO_REFRESH_MINUTES 分鐘自動從 Google Drive 抓最新資料"""
    while True:
        await asyncio.sleep(AUTO_REFRESH_MINUTES * 60)
        try:
            get_data(force_refresh=True)
            latest = _cached_sales_df["_date"].max() if _cached_sales_df is not None and not _cached_sales_df.empty else "?"
            print(f"[自動更新] 資料已更新，最新日期：{latest}")
        except Exception as e:
            print(f"[自動更新失敗] {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時強制從 Google Drive 抓最新資料
    print("[啟動] 正在從 Google Drive 載入最新資料...")
    try:
        get_data(force_refresh=True)
        if _cached_sales_df is not None and not _cached_sales_df.empty:
            latest = _cached_sales_df["_date"].max()
            print(f"[啟動] 資料載入完成，最新日期：{latest}，共 {len(_cached_sales_df)} 筆")
        else:
            print("[啟動] 使用示範資料")
    except Exception as e:
        print(f"[啟動] 載入失敗，使用示範資料：{e}")

    # 啟動自動更新背景任務
    task = asyncio.create_task(_auto_refresh_loop())
    print(f"[啟動] 已開啟自動更新，每 {AUTO_REFRESH_MINUTES} 分鐘重新抓取一次")
    yield
    task.cancel()


app = FastAPI(title="雙之家商業後台分析系統", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全域快取
_cached_data: dict = None
_cached_sales_df: pd.DataFrame = None


def load_data_from_drive() -> dict:
    """從 Google Drive 下載並處理資料，同步寫入 SQLite"""
    xl = download_excel()
    recent_sheets = get_recent_sheet_names(xl, months=12)
    sales_df = load_all_sales(xl, recent_sheets)
    expense_df = load_all_expenses(xl, recent_sheets)
    # 同步到本地 SQLite
    sync_from_dataframe(sales_df, expense_df)
    return build_dashboard_data(sales_df, expense_df), sales_df


def get_data(force_refresh: bool = False) -> dict:
    global _cached_data, _cached_sales_df

    has_creds = os.path.exists(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")) or bool(os.getenv("GOOGLE_CREDENTIALS_JSON"))

    if force_refresh or _cached_data is None:
        if has_creds:
            try:
                _cached_data, _cached_sales_df = load_data_from_drive()
                print(f"[OK] 已從 Google Drive 載入資料，近30天 {_cached_data['summary']['total_transactions']} 筆交易")
            except Exception as e:
                print(f"[WARN] 讀取失敗，使用示範資料：{e}")
                _cached_data = _get_demo_data()
        else:
            _cached_data = _get_demo_data()

    return _cached_data


def _get_demo_data() -> dict:
    """示範資料（僅在無法連線時使用）"""
    import random
    from datetime import datetime, timedelta
    today = datetime.today()
    daily = []
    for i in range(30):
        d = today - timedelta(days=29 - i)
        rev = random.randint(12000, 35000)
        daily.append({"date": d.strftime("%Y-%m-%d"), "revenue": rev})

    return {
        "summary": {
            "this_week_revenue": 95000,
            "last_week_revenue": 88000,
            "week_growth": 8.0,
            "this_month_revenue": 380000,
            "total_transactions": 420,
            "total_expense": 25000,
        },
        "daily_sales": daily,
        "category_sales": [
            {"category": "服飾", "revenue": 180000, "percentage": 47.4},
            {"category": "醫藥", "revenue": 90000, "percentage": 23.7},
            {"category": "食品", "revenue": 65000, "percentage": 17.1},
            {"category": "雜貨", "revenue": 45000, "percentage": 11.8},
        ],
        "products": [
            {"品名": "示範商品A", "revenue": 12000, "quantity": 15, "category": "服飾"},
        ],
        "location_sales": [],
        "expenses": [],
    }


# ─────────────────────────────────────────
# API 端點
# ─────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "雙之家商業後台 API", "status": "running"}


# ─── 登入（公開，不需 Token）────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
def login(req: LoginRequest):
    if req.username != ADMIN_USERNAME or not verify_password(req.password, ADMIN_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="帳號或密碼錯誤",
        )
    token = create_token(req.username)
    return {"access_token": token, "token_type": "bearer", "username": req.username}

@app.get("/api/auth/me")
def me(user: str = Depends(get_current_user)):
    return {"username": user}


# ─── 以下所有 API 皆需登入 ──────────────────
@app.get("/api/dashboard")
def get_dashboard(user: str = Depends(get_current_user)):
    return get_data()


@app.get("/api/products")
def get_products(user: str = Depends(get_current_user)):
    data = get_data()
    return {"products": data.get("products", [])}


@app.get("/api/sales/daily")
def get_daily_sales(
    days: int = 30,
    start_date: str = None,
    end_date: str = None,
    top_products: bool = False,
    user: str = Depends(get_current_user),
):
    get_data()
    if _cached_sales_df is None or _cached_sales_df.empty:
        return {"daily_sales": []}
    detail = get_daily_detail(_cached_sales_df, days=days,
                               start_date=start_date, end_date=end_date)
    if not top_products:
        for row in detail:
            row.pop("top_products", None)
    return {"daily_sales": detail}


@app.get("/api/sales/category")
def get_category_sales(user: str = Depends(get_current_user)):
    data = get_data()
    return {"category_sales": data.get("category_sales", [])}


@app.get("/api/sales/location")
def get_location_sales(user: str = Depends(get_current_user)):
    data = get_data()
    return {"location_sales": data.get("location_sales", [])}


@app.get("/api/summary")
def get_summary(user: str = Depends(get_current_user)):
    data = get_data()
    return data.get("summary", {})


@app.get("/api/profit")
def get_profit(
    days: int = 30,
    start_date: str = None,
    end_date: str = None,
    user: str = Depends(get_current_user),
):
    get_data()
    if _cached_sales_df is None or _cached_sales_df.empty:
        return {}
    return get_profit_report(_cached_sales_df, days=days,
                              start_date=start_date, end_date=end_date)


@app.get("/api/expenses")
def get_expenses(user: str = Depends(get_current_user)):
    data = get_data()
    return {"expenses": data.get("expenses", [])}


class ChatRequest(BaseModel):
    question: str
    history: Optional[list] = []


@app.post("/api/chat")
def chat_with_data(req: ChatRequest, user: str = Depends(get_current_user)):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="問題不能為空")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return {"answer": "⚠️ 尚未設定 ANTHROPIC_API_KEY。\n請在 backend/.env 填入 Claude API Key 後重啟服務。"}
    # Phase 1：使用 Agent + tool_use 動態查詢 SQLite，取代固定 context
    answer = analyze_with_agent(req.question, req.history)

    # 儲存這輪對話到資料庫
    now = datetime.now().isoformat()
    con = sqlite3.connect(DB_PATH)
    con.execute("INSERT INTO chat_messages (role, content, created_at) VALUES (?, ?, ?)",
                ("user", req.question, now))
    con.execute("INSERT INTO chat_messages (role, content, created_at) VALUES (?, ?, ?)",
                ("assistant", answer, now))
    con.commit()
    con.close()

    return {"answer": answer}


@app.get("/api/chat/history")
def get_chat_history(limit: int = 100, user: str = Depends(get_current_user)):
    """取得最近的對話歷史"""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT role, content, created_at FROM chat_messages ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    con.close()
    messages = [{"role": r[0], "content": r[1], "created_at": r[2]} for r in reversed(rows)]
    return {"messages": messages}


@app.delete("/api/chat/history")
def clear_chat_history(user: str = Depends(get_current_user)):
    """清空所有對話記錄"""
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM chat_messages")
    con.commit()
    con.close()
    return {"message": "已清空對話記錄"}


@app.post("/api/report/generate")
def generate_report(user: str = Depends(get_current_user)):
    """生成週報並儲存到資料庫"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        raise HTTPException(status_code=400, detail="請先設定 ANTHROPIC_API_KEY")
    data = get_data()
    content = generate_weekly_report(data)
    now = datetime.now()
    title = f"{now.strftime('%Y/%m/%d')} 週報"
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(
        "INSERT INTO reports (title, content, created_at) VALUES (?, ?, ?)",
        (title, content, now.isoformat())
    )
    report_id = cur.lastrowid
    con.commit()
    con.close()
    return {"id": report_id, "title": title, "content": content, "created_at": now.isoformat()}


@app.get("/api/reports")
def list_reports(user: str = Depends(get_current_user)):
    """取得所有週報列表（不含內容）"""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT id, title, created_at, substr(content, 1, 100) as preview FROM reports ORDER BY id DESC"
    ).fetchall()
    con.close()
    return [{"id": r[0], "title": r[1], "created_at": r[2], "preview": r[3]} for r in rows]


@app.get("/api/reports/{report_id}")
def get_report(report_id: int, user: str = Depends(get_current_user)):
    """取得單一週報完整內容"""
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT id, title, content, created_at FROM reports WHERE id = ?", (report_id,)
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404, detail="報告不存在")
    return {"id": row[0], "title": row[1], "content": row[2], "created_at": row[3]}


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: int, user: str = Depends(get_current_user)):
    """刪除週報"""
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    con.commit()
    con.close()
    return {"message": "已刪除"}


# 保留舊端點相容性
@app.get("/api/report/weekly")
def get_weekly_report(user: str = Depends(get_current_user)):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return {"report": "⚠️ 請先設定 ANTHROPIC_API_KEY 才能使用 AI 週報功能。"}
    data = get_data()
    report = generate_weekly_report(data)
    return {"report": report}


@app.post("/api/upload")
async def upload_excel(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    global _cached_data
    if not file.filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="請上傳 .xlsx/.xls/.csv 檔案")
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content)) if file.filename.endswith(".csv") else pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失敗：{e}")
    return {"message": f"已接收 {len(df)} 列資料（{file.filename}）", "rows": len(df)}


@app.post("/api/refresh")
def refresh_data(user: str = Depends(get_current_user)):
    """強制從 Google Drive 重新下載"""
    data = get_data(force_refresh=True)
    s = data.get("summary", {})
    return {
        "message": "資料已更新",
        "this_month_revenue": s.get("this_month_revenue", 0),
        "total_transactions": s.get("total_transactions", 0),
    }


# ─────────────────────────────────────────
# LINE Bot Webhook（雙向對話：用戶在 LINE 問 → Claude 回答 → 回傳到 LINE）
# ─────────────────────────────────────────
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# 暫存最近一次 webhook 看到的訊息來源（用來協助找出群組 ID）
_last_line_source: dict = {"source": None, "received_at": None, "text": None}


def _verify_line_signature(body: bytes, signature: str | None) -> bool:
    """驗證 LINE webhook 簽章"""
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


def _strip_markdown(text: str) -> str:
    """清除 markdown 符號（LINE 無法渲染粗體斜體）"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?m)^\s*[#>]+\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*]\s+", "・", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


def _line_call(url: str, payload: dict, timeout: int = 15) -> tuple[int, str]:
    """呼叫 LINE Messaging API"""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _line_reply(reply_token: str, text: str) -> tuple[int, str]:
    return _line_call(LINE_REPLY_URL, {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    })


def _line_push(target_id: str, text: str) -> tuple[int, str]:
    return _line_call(LINE_PUSH_URL, {
        "to": target_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    })


def _process_line_event(event: dict) -> None:
    """處理單一 LINE webhook 事件 — 同步函式，由 BackgroundTasks 在 threadpool 執行"""
    global _last_line_source

    src = event.get("source", {}) or {}
    # 更新「最近來源」紀錄（協助使用者找出群組 ID）
    _last_line_source = {
        "source": src,
        "received_at": datetime.now().isoformat(),
        "text": (event.get("message") or {}).get("text") if event.get("type") == "message" else None,
    }

    if event.get("type") != "message":
        return

    msg = event.get("message") or {}
    if msg.get("type") != "text":
        return

    reply_token = event.get("replyToken", "")
    question = (msg.get("text") or "").strip()
    if not question or not reply_token:
        return

    # 簡單問候 / 求助訊息 — 不浪費 API token
    quick_replies = {
        "hi": "您好！我是雙之家後台小幫手，可以問我任何銷售相關問題。",
        "hello": "您好！我是雙之家後台小幫手，可以問我任何銷售相關問題。",
        "你好": "您好！我是雙之家後台小幫手，可以問我任何銷售相關問題。",
        "help": "可以問我：\n・本週賣最好的商品是什麼？\n・這個月各營業點的銷售比較\n・下週天氣會影響哪個品類？",
        "說明": "可以問我：\n・本週賣最好的商品是什麼？\n・這個月各營業點的銷售比較\n・下週天氣會影響哪個品類？",
    }
    if question.lower() in quick_replies:
        _line_reply(reply_token, quick_replies[question.lower()])
        return

    # 呼叫 AI 分析（含 SQL/天氣/搜尋工具）
    # 以 LLM_PROVIDER 環境變數切換引擎：
    #   gemini → Gemini 2.0 Flash（免費）
    #   其他 / 未設定 → Claude（預設、最高品質）
    provider = os.getenv("LLM_PROVIDER", "claude").lower()
    try:
        if provider == "gemini":
            answer = analyze_with_agent_gemini(question, [])
        else:
            answer = analyze_with_agent(question, [])
        answer = _strip_markdown(answer)
        if not answer:
            answer = "（沒有回應，請換個方式問問看）"
    except Exception as e:
        answer = f"⚠️ 分析時發生錯誤：{str(e)[:300]}"

    status_code, body = _line_reply(reply_token, answer)
    if status_code != 200:
        # Reply token 可能過期；fallback 用 push
        target = src.get("groupId") or src.get("roomId") or src.get("userId")
        if target:
            _line_push(target, answer)


@app.post("/api/line/webhook")
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str | None = Header(default=None, alias="X-Line-Signature"),
):
    """LINE Messaging API webhook 入口（必須在 ~10 秒內回 200）"""
    body = await request.body()

    # LINE 平台「Verify webhook」按鈕會送一個沒有 events 的空請求；
    # 也允許簽章驗證失敗時回 200 不要崩，但事件就不處理
    if not _verify_line_signature(body, x_line_signature):
        # 不直接 403 — 避免 LINE Console 的 verify 按鈕誤判
        return {"status": "signature_invalid"}

    try:
        payload = json.loads(body.decode() or "{}")
    except json.JSONDecodeError:
        return {"status": "invalid_json"}

    for event in payload.get("events", []):
        background_tasks.add_task(_process_line_event, event)

    return {"status": "ok"}


@app.get("/api/line/last-source")
def get_last_line_source(user: str = Depends(get_current_user)):
    """
    取得最近一次 webhook 收到的訊息來源 — 用來找出群組 ID。
    用法：把 bot 邀進群組 → 群組裡傳一句話 → 呼叫這支 API → 拿到 groupId。
    """
    return _last_line_source


@app.get("/api/line/daily")
def line_daily_brief(user: str = Depends(get_current_user)):
    """
    LINE 每日速報專用 endpoint — 一次拿完所有必要資料：
    - 「今日」（呼叫當下的日期）的營收、淨利、毛利率
    - 該日 TOP 3 商品 + 個別銷售金額
    - 本月累計營收 / 交易筆數（當月 1 號 ~ 今天），並拆分光復／新埔累計
      （優先用「營業點」欄位實際填答，缺資料才退回星期幾規則估計）
    - 明日預計準備商品：取「明天」這個星期幾，過去 8 週同星期資料中，
      相對近 16 週平常水準熱賣倍數（lift）最高的 2 個分類（優先用細分類，無則退回大類），
      並附上每個分類底下具體賣最好的 1-2 個品項

    若今日 Google Sheet 沒有對應日期的紀錄 → has_data=False，
    line_daily_report 腳本會跳過推送（避免推「資料日期：5/20」這種誤導）
    """
    # 強制刷新確保抓到 Google Sheet 上的最新資料
    get_data(force_refresh=True)
    if _cached_sales_df is None or _cached_sales_df.empty:
        raise HTTPException(status_code=503, detail="尚無銷售資料")

    df = _cached_sales_df
    # 「今日」=呼叫當下的日期；不 fallback 到資料最新日期
    target_date = pd.Timestamp(datetime.today().date())

    today_df = df[df["_date"].dt.date == target_date.date()]
    today_revenue = float(today_df["_sales"].sum()) if not today_df.empty else 0.0

    # 該日淨利（有成本資料才能算）
    today_profit = None
    today_margin = None
    if "_cost" in today_df.columns:
        cost_rows = today_df[today_df["_cost"].notna() & (today_df["_cost"] > 0)]
        if not cost_rows.empty:
            cost_total = float(cost_rows["_cost"].sum())
            cost_basis_revenue = float(cost_rows["_sales"].sum())
            today_profit = round(cost_basis_revenue - cost_total, 0)
            if cost_basis_revenue > 0:
                today_margin = round(
                    (cost_basis_revenue - cost_total) / cost_basis_revenue * 100, 1
                )

    # 該日 TOP 3 商品
    top3 = []
    if "品名" in today_df.columns and not today_df.empty:
        top = today_df.groupby("品名")["_sales"].sum().nlargest(3)
        for name, rev in top.items():
            top3.append({"name": str(name), "revenue": round(float(rev), 0)})

    # 本月累計（當月 1 號 ~ 今天）
    month_start = target_date.replace(day=1)
    mtd = df[(df["_date"] >= month_start) & (df["_date"] <= target_date)]
    mtd_revenue = round(float(mtd["_sales"].sum()), 0) if not mtd.empty else 0.0
    mtd_transactions = int(len(mtd))

    # 本月累計依營業點拆分。優先用「營業點」欄位的實際填答（表單直接勾選，最準確）；
    # 該欄位缺資料時才退回星期幾規則（週一～三＝新埔，週四～日＝光復）當估計值。
    guangfu_revenue = xinpu_revenue = 0.0
    guangfu_transactions = xinpu_transactions = 0
    if not mtd.empty:
        if "營業點" in mtd.columns and mtd["營業點"].notna().any():
            guangfu_mask = mtd["營業點"] == "光復"
            xinpu_mask = mtd["營業點"] == "新埔"
        else:
            mtd_weekday = mtd["_date"].dt.dayofweek
            xinpu_mask = mtd_weekday.isin([0, 1, 2])  # 一二三
            guangfu_mask = mtd_weekday.isin([3, 4, 5, 6])  # 四五六日
        guangfu_revenue = round(float(mtd.loc[guangfu_mask, "_sales"].sum()), 0)
        guangfu_transactions = int(guangfu_mask.sum())
        xinpu_revenue = round(float(mtd.loc[xinpu_mask, "_sales"].sum()), 0)
        xinpu_transactions = int(xinpu_mask.sum())

    # 明日預計準備商品：找出「明天這個星期幾」相對平常明顯熱賣的類別，
    # 而不是單純看總金額最高（那樣永遠只會選出服飾/醫藥這種天天都最大宗的類別，沒有指引意義）。
    #
    # 作法：
    #   1. 分類粒度優先用「分類」（較細，如：保暖衣物、襪子），沒有資料才退回「大類」
    #   2. weekday_share = 該類別在「明天星期幾」過去 8 次出現時的營收佔比
    #      baseline_share = 該類別在近 16 週（112 天，= 2 倍樣本窗）所有營業日的營收佔比（=「平常」水準）
    #      lift = weekday_share / baseline_share，倍數越高代表該類別在這個星期幾特別熱賣
    #   3. 只出現 1 天的類別視為樣本不足；baseline 佔比 < 0.5% 視為太冷門、比值容易失真，都排除
    WEEKDAY_SAMPLE_WEEKS = 8
    BASELINE_WEEKS = WEEKDAY_SAMPLE_WEEKS * 2

    tomorrow_date = target_date + pd.Timedelta(days=1)
    recommended_categories = []

    cat_col = None
    if "分類" in df.columns and df["分類"].notna().any():
        cat_col = "分類"
    elif "大類" in df.columns:
        cat_col = "大類"

    if cat_col:
        past_same_weekday = [
            tomorrow_date - pd.Timedelta(days=7 * k) for k in range(1, WEEKDAY_SAMPLE_WEEKS + 1)
        ]
        past_dates = {d.date() for d in past_same_weekday}
        weekday_pool = df[df["_date"].dt.date.isin(past_dates)]

        baseline_start = target_date - pd.Timedelta(days=7 * BASELINE_WEEKS)
        baseline_pool = df[(df["_date"] > baseline_start) & (df["_date"] <= target_date)]

        if not weekday_pool.empty and not baseline_pool.empty:
            weekday_cat_rev = weekday_pool.groupby(cat_col)["_sales"].sum()
            weekday_cat_days = weekday_pool.groupby(cat_col)["_date"].nunique()
            weekday_total = float(weekday_cat_rev.sum())

            baseline_cat_rev = baseline_pool.groupby(cat_col)["_sales"].sum()
            baseline_total = float(baseline_cat_rev.sum())

            candidates = []
            if weekday_total > 0 and baseline_total > 0:
                for cat, rev in weekday_cat_rev.items():
                    if weekday_cat_days.get(cat, 0) < 2:
                        continue
                    baseline_share = float(baseline_cat_rev.get(cat, 0.0)) / baseline_total
                    if baseline_share < 0.005:
                        continue
                    weekday_share = float(rev) / weekday_total
                    candidates.append({
                        "category": str(cat),
                        "revenue": round(float(rev), 0),
                        "lift": round(weekday_share / baseline_share, 2),
                    })

            candidates.sort(key=lambda c: c["lift"], reverse=True)
            recommended_categories = candidates[:2]

            # 每個推薦分類底下，具體要多備哪些品項：
            # 直接看「這個分類 × 明天星期幾」這個縮小範圍內賣最好的 1-2 個品名（原始金額排名即可，
            # 不再疊一層 lift 比值——品項粒度樣本本來就更小，雙重比值只會放大雜訊）
            if "品名" in weekday_pool.columns:
                for c in recommended_categories:
                    cat_pool = weekday_pool[weekday_pool[cat_col] == c["category"]]
                    top_items = cat_pool.groupby("品名")["_sales"].sum().nlargest(2)
                    c["top_items"] = [str(name) for name in top_items.index]

    return {
        "date": str(target_date.date()),
        "revenue": round(today_revenue, 0),
        "profit": today_profit,
        "margin": today_margin,
        "top_products": top3,
        "month_start": str(month_start.date()),
        "month_to_date_revenue": mtd_revenue,
        "month_to_date_transactions": mtd_transactions,
        "guangfu_month_to_date_revenue": guangfu_revenue,
        "guangfu_month_to_date_transactions": guangfu_transactions,
        "xinpu_month_to_date_revenue": xinpu_revenue,
        "xinpu_month_to_date_transactions": xinpu_transactions,
        "tomorrow_date": str(tomorrow_date.date()),
        "recommended_categories": recommended_categories,
        "has_data": not today_df.empty,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
