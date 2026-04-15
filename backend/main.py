"""
FastAPI 後端主程式 — 雙之家日記帳分析系統
"""
import os
import sqlite3
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, status
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
from llm_analyzer import analyze_with_llm, analyze_with_agent, generate_weekly_report
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

    has_creds = os.path.exists(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
