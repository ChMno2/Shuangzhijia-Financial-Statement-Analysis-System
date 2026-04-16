"""
Google Drive 資料存取模組 — 支援 Excel (.xlsx) 格式
"""
import os
import io
import re
from datetime import datetime
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_drive_service():
    # 優先從環境變數讀取（雲端部署用），否則從檔案讀取（本地開發用）
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        import json
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def download_excel() -> pd.ExcelFile:
    """從 Google Drive 下載 Excel 檔案並回傳 ExcelFile 物件"""
    service = get_drive_service()
    file_id = os.getenv("SPREADSHEET_ID")
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    return pd.ExcelFile(buf)


def parse_sheet_period(name: str):
    """
    將工作表名稱轉換為 (year, month_start) 元組，無法解析則回傳 None
    支援格式：YYYYMMDD（如 20260102）或 YYMMDD（如 200102）
    """
    name = name.strip()
    if re.fullmatch(r'\d{8}', name):            # 20260102
        y = int(name[:4])
        m = int(name[4:6])
        return (y, m)
    elif re.fullmatch(r'\d{6}', name):           # 200102
        y = int("20" + name[:2])
        m = int(name[2:4])
        return (y, m)
    return None


def get_recent_sheet_names(xl: pd.ExcelFile, months: int = 12) -> list:
    """取得最近 N 個月內的工作表名稱（依日期排序）"""
    today = datetime.today()
    cutoff_year = today.year
    cutoff_month = today.month - months

    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1

    result = []
    for name in xl.sheet_names:
        parsed = parse_sheet_period(name)
        if parsed is None:
            continue
        y, m = parsed
        if (y, m) >= (cutoff_year, cutoff_month):
            result.append((y, m, name))

    result.sort()
    return [r[2] for r in result]


def _parse_date_with_year(series: pd.Series, fallback_year: int) -> pd.Series:
    """
    解析日期欄，支援：
    - datetime 物件（直接使用）
    - 'M/D' 字串（補年份）
    - 'YYYY-MM-DD' 等標準格式
    """
    def _parse_one(v):
        if pd.isnull(v):
            return pd.NaT
        if isinstance(v, (datetime, pd.Timestamp)):
            return pd.Timestamp(v)
        s = str(v).strip()
        if not s or s.lower() in ("nan", "nat"):
            return pd.NaT
        # M/D 或 MM/DD 格式，補年份
        if re.fullmatch(r'\d{1,2}/\d{1,2}', s):
            try:
                return pd.Timestamp(f"{fallback_year}/{s}")
            except Exception:
                return pd.NaT
        try:
            return pd.Timestamp(s)
        except Exception:
            return pd.NaT

    return series.apply(_parse_one)


def load_all_sales(xl: pd.ExcelFile, sheet_names: list) -> pd.DataFrame:
    """
    讀取多個工作表的銷售資料並合併
    銷售列判斷：日期欄不為 NaN 且 銷售總金額 不為 NaN
    """
    frames = []
    for name in sheet_names:
        try:
            df = xl.parse(name)
        except Exception:
            continue

        # 從工作表名稱推算年份（供日期補全用）
        parsed_period = parse_sheet_period(name)
        fallback_year = parsed_period[0] if parsed_period else datetime.today().year

        # 找「日期」欄
        date_col = None
        for col in df.columns:
            if isinstance(col, datetime):
                date_col = col
                break
            if str(col).startswith("日期"):
                date_col = col
                break
        if date_col is None and len(df.columns) > 0:
            date_col = df.columns[0]

        # 找銷售總金額欄
        sales_col = None
        for col in df.columns:
            if "銷售總金額" in str(col):
                sales_col = col
                break

        if date_col is None or sales_col is None:
            continue

        df = df.copy()
        df["_date"] = _parse_date_with_year(df[date_col], fallback_year)
        df["_sales"] = pd.to_numeric(df[sales_col], errors="coerce")
        sales_df = df[df["_date"].notna() & df["_sales"].notna() & (df["_sales"] > 0)].copy()

        if sales_df.empty:
            continue

        # 標準化欄位名稱
        col_rename = {}
        for col in df.columns:
            cs = str(col)
            if "大類" in cs:
                col_rename[col] = "大類"
            elif "分類" in cs and "大類" not in cs:
                col_rename[col] = "分類"
            elif "品名" in cs:
                col_rename[col] = "品名"
            elif cs in ["單價", "銷售單價"]:
                col_rename[col] = "單價"
            elif "銷售數量" in cs:
                col_rename[col] = "銷售數量"
            elif "營業點" in cs:
                col_rename[col] = "營業點"
            elif "進貨總成本" in cs:
                col_rename[col] = "進貨總成本"
            elif "進貨單價（台幣）" in cs:
                col_rename[col] = "進貨單價（台幣）"
            elif "銷售成本" in cs:
                col_rename[col] = "銷售成本"
            elif "銷售淨利" in cs:
                col_rename[col] = "銷售淨利"

        sales_df = sales_df.rename(columns=col_rename)

        # 建立統一成本欄 _cost（優先順序：銷售成本 > 進貨總成本 > 進貨單價×數量）
        # 都無資料則為 NaN（標記為表單未填寫）
        cost_series = pd.Series([float("nan")] * len(sales_df), index=sales_df.index)

        # 1. 銷售成本（最新工作表格式）— 銷售成本為單位成本，需乘以銷售數量
        if "銷售成本" in sales_df.columns:
            v = pd.to_numeric(sales_df["銷售成本"], errors="coerce")
            if "銷售數量" in sales_df.columns:
                qty = pd.to_numeric(sales_df["銷售數量"], errors="coerce")
                calc = v * qty
            else:
                calc = v
            mask = calc.notna() & (calc > 0)
            cost_series[mask] = calc[mask]

        # 2. 進貨總成本（舊格式直接記錄總成本）
        if "進貨總成本" in sales_df.columns:
            v = pd.to_numeric(sales_df["進貨總成本"], errors="coerce")
            mask = v.notna() & (v > 0) & cost_series.isna()
            cost_series[mask] = v[mask]

        # 3. 進貨單價（台幣）× 銷售數量（舊格式用單價記錄）
        if "進貨單價（台幣）" in sales_df.columns and "銷售數量" in sales_df.columns:
            unit = pd.to_numeric(sales_df["進貨單價（台幣）"], errors="coerce")
            qty = pd.to_numeric(sales_df["銷售數量"], errors="coerce")
            calc = unit * qty
            mask = calc.notna() & (calc > 0) & cost_series.isna()
            cost_series[mask] = calc[mask]

        sales_df["_cost"] = cost_series
        sales_df["sheet"] = name
        frames.append(sales_df)

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    # 過濾明顯錯誤的日期（合理範圍：2000年以後）
    merged["_date"] = pd.to_datetime(merged["_date"], errors="coerce")
    merged = merged[merged["_date"] >= "2000-01-01"]
    return merged


def load_all_expenses(xl: pd.ExcelFile, sheet_names: list) -> pd.DataFrame:
    """讀取多個工作表的支出資料"""
    frames = []
    for name in sheet_names:
        try:
            df = xl.parse(name)
        except Exception:
            continue

        expense_col = None
        for col in df.columns:
            if "支出項目" in str(col):
                expense_col = col
                break
        if expense_col is None:
            continue

        # 找金額欄（優先台幣）
        amount_col = None
        for col in df.columns:
            cs = str(col)
            if "金額（NT)" in cs or "金額（台幣)" in cs or cs == "金額":
                amount_col = col
                break
        if amount_col is None:
            for col in df.columns:
                if "金額" in str(col) and "日幣" not in str(col) and "¥" not in str(col):
                    amount_col = col
                    break

        if amount_col is None:
            continue

        expense_df = df[df[expense_col].notna()].copy()
        expense_df["_amount"] = pd.to_numeric(expense_df[amount_col], errors="coerce")
        expense_df = expense_df[expense_df["_amount"].notna() & (expense_df["_amount"] > 0)]
        expense_df = expense_df.rename(columns={expense_col: "支出項目", amount_col: "金額"})
        expense_df["sheet"] = name
        frames.append(expense_df[["支出項目", "金額", "_amount", "sheet"]])

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
