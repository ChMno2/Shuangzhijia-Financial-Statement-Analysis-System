"""
Google Sheets 資料存取模組

改用 Sheets API 直接讀取即時儲存格數值，不再透過 Drive API 下載匯出的
.xlsx 快照。原因：「總表」的營業點欄位是 Apps Script 自訂函數算出來的
（=IFERROR(@__xludf.DUMMYFUNCTION(...), ...)），Google 把這種檔案匯出成
.xlsx 時要先重新計算並凍結所有自訂函數結果，這個匯出快照對這份檔案來說
會嚴重落後（實測落後超過一整個工作天），導致抓不到當天最新資料。
Sheets API 讀的是試算表當下即時算好的結果，沒有這個匯出延遲問題。
"""
import os
import re
from datetime import datetime
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _load_credentials():
    # 優先從環境變數讀取（雲端部署用），否則從檔案讀取（本地開發用）
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        import json
        info = json.loads(creds_json)
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    return Credentials.from_service_account_file(creds_file, scopes=SCOPES)


def get_sheets_service():
    return build("sheets", "v4", credentials=_load_credentials())


def _quote_sheet_name(name: str) -> str:
    """A1 表示法裡工作表名稱含空白／特殊符號時需要用單引號包起來"""
    return "'" + name.replace("'", "''") + "'"


class _SheetsAdapter:
    """模仿 pd.ExcelFile 的介面（.sheet_names / .parse()），
    讓 get_recent_sheet_names() / load_all_sales() / load_all_expenses()
    不用跟著改，底層改成用 Sheets API 讀即時資料。"""

    def __init__(self, service, spreadsheet_id: str):
        self._service = service
        self._spreadsheet_id = spreadsheet_id
        meta = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id, fields="sheets.properties.title"
        ).execute()
        self.sheet_names = [
            s["properties"]["title"] for s in meta.get("sheets", [])
        ]

    def parse(self, sheet_name: str) -> pd.DataFrame:
        resp = self._service.spreadsheets().values().get(
            spreadsheetId=self._spreadsheet_id,
            range=_quote_sheet_name(sheet_name),
            valueRenderOption="FORMATTED_VALUE",
        ).execute()
        rows = resp.get("values", [])
        if not rows:
            return pd.DataFrame()
        header, *body = rows
        width = len(header)
        # Sheets API 會省略每列尾端的空白儲存格，把每列補／截到跟表頭一樣長，避免欄位對不齊
        body = [(r + [None] * (width - len(r)))[:width] for r in body]
        return pd.DataFrame(body, columns=header)


def download_excel() -> "_SheetsAdapter":
    """透過 Sheets API 讀取試算表，回傳模仿 pd.ExcelFile 介面的介接物件"""
    service = get_sheets_service()
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    return _SheetsAdapter(service, spreadsheet_id)


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


MASTER_SHEET_NAMES = {"總表", "總覽", "master", "Master", "MASTER"}


def _normalize_sheet_name(name: str) -> str:
    """容忍前後空白、方括號、書名號等修飾"""
    return name.strip().strip("[]【】「」「」").strip()


def get_recent_sheet_names(xl: "_SheetsAdapter", months: int = 12) -> list:
    """
    取得要讀的工作表名稱清單。
    優先順序：
      1) 若有「總表」之類的 master sheet → 只讀它（避免和日期分頁的舊資料重複）
      2) 否則 → 讀最近 N 個月的日期分頁（YYYYMMDD / YYMMDD 命名）
    對 master sheet 名稱會做容錯比對（前後空白、方括號等不影響匹配）。
    """
    # 1. 優先用 master sheet（容忍空白 / 方括號）
    print(f"[get_recent_sheet_names] 所有 sheet: {xl.sheet_names}", flush=True)
    for sheet in xl.sheet_names:
        if _normalize_sheet_name(sheet) in MASTER_SHEET_NAMES:
            print(f"[get_recent_sheet_names] 命中 master sheet：'{sheet}'", flush=True)
            return [sheet]  # 回傳原始名稱（含原本的空白／符號）給 xl.parse

    # 2. fallback：原本的日期分頁邏輯
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
    if result:
        return [r[2] for r in result]

    # 3. 都沒配對到，且整個檔案只有一個分頁（例如 Google 表單回覆試算表，
    #    表單回覆一直往下累積、不分月份分頁）→ 直接用它
    if len(xl.sheet_names) == 1:
        print(
            f"[get_recent_sheet_names] 無 master sheet／日期分頁可比對，"
            f"檔案只有一個分頁，直接使用：'{xl.sheet_names[0]}'",
            flush=True,
        )
        return list(xl.sheet_names)

    return []


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


def _find_type_col(df: pd.DataFrame):
    """Google 表單回覆專用：找「支出 or 收入」這個標記欄（同時含這兩個字才算數，
    避免誤配到其他欄位）"""
    return next(
        (c for c in df.columns if "收入" in str(c) and "支出" in str(c)), None
    )


def _parse_form_responses_sales(df: pd.DataFrame, type_col, fallback_year: int):
    """
    解析 Google 表單回覆裡的「收入」列。

    這種表單沒有現成的「銷售總金額」欄，要用「單價 × 數量」自己算；
    「分類」也不是單一欄位，而是服飾/食品/醫藥/雜貨四個子問題各自一欄，
    只有對應大類那一欄會被填寫，取有值的那一欄當分類。
    「營業點」在這裡是表單直接勾選的答案（不是公式推算），比用星期幾猜測可靠。
    """
    date_col = next((c for c in df.columns if str(c).startswith("日期")), None)
    item_col = next((c for c in df.columns if "商品名" in str(c)), None)
    qty_col = next((c for c in df.columns if "數量" in str(c)), None)
    price_col = next((c for c in df.columns if "單價" in str(c)), None)
    cost_col = next(
        (c for c in df.columns if "成本" in str(c) and "費用" not in str(c)), None
    )
    loc_col = next((c for c in df.columns if "營業點" in str(c)), None)
    cat_col = next((c for c in df.columns if str(c) == "大類"), None)
    subcat_cols = [c for c in df.columns if "請問是「" in str(c)]

    if date_col is None or item_col is None or qty_col is None or price_col is None:
        return None

    income = df[df[type_col].astype(str).str.strip() == "收入"].copy()
    if income.empty:
        return None

    income["_date"] = _parse_date_with_year(income[date_col], fallback_year)
    qty = pd.to_numeric(income[qty_col], errors="coerce")
    price = pd.to_numeric(income[price_col], errors="coerce")
    income["_sales"] = price * qty

    income = income[
        income["_date"].notna() & income["_sales"].notna() & (income["_sales"] > 0)
    ].copy()
    if income.empty:
        return None

    if cost_col is not None:
        unit_cost = pd.to_numeric(income[cost_col], errors="coerce")
        qty = pd.to_numeric(income[qty_col], errors="coerce")
        income["_cost"] = unit_cost * qty
    else:
        income["_cost"] = float("nan")

    if subcat_cols:
        def _first_subcat(row):
            for c in subcat_cols:
                v = row.get(c)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return None
        income["分類"] = income.apply(_first_subcat, axis=1)
    else:
        income["分類"] = None

    rename = {item_col: "品名"}
    if cat_col is not None:
        rename[cat_col] = "大類"
    if loc_col is not None:
        rename[loc_col] = "營業點"
    income = income.rename(columns=rename)

    keep = ["_date", "_sales", "_cost", "品名", "分類"]
    keep += [c for c in ("大類", "營業點") if c in income.columns]
    return income[keep].copy()


def _parse_legacy_sheet_sales(df: pd.DataFrame, fallback_year: int):
    """解析舊格式工作表（日期分頁 / 總表 IMPORTRANGE 匯總）的銷售資料"""
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
        return None

    df = df.copy()
    df["_date"] = _parse_date_with_year(df[date_col], fallback_year)
    df["_sales"] = pd.to_numeric(df[sales_col], errors="coerce")
    sales_df = df[df["_date"].notna() & df["_sales"].notna() & (df["_sales"] > 0)].copy()

    if sales_df.empty:
        return None

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
    return sales_df


def load_all_sales(xl: "_SheetsAdapter", sheet_names: list) -> pd.DataFrame:
    """
    讀取多個工作表的銷售資料並合併。

    Google 表單回覆試算表（有「支出 or 收入」欄）走 _parse_form_responses_sales；
    舊格式（日期分頁 / 總表 IMPORTRANGE 匯總）走 _parse_legacy_sheet_sales。
    """
    frames = []
    for name in sheet_names:
        try:
            df = xl.parse(name)
        except Exception:
            continue

        parsed_period = parse_sheet_period(name)
        fallback_year = parsed_period[0] if parsed_period else datetime.today().year

        type_col = _find_type_col(df)
        if type_col is not None:
            sales_df = _parse_form_responses_sales(df, type_col, fallback_year)
        else:
            sales_df = _parse_legacy_sheet_sales(df, fallback_year)

        if sales_df is None or sales_df.empty:
            continue

        sales_df["sheet"] = name
        frames.append(sales_df)

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    # 過濾明顯錯誤的日期（合理範圍：2000年以後）
    merged["_date"] = pd.to_datetime(merged["_date"], errors="coerce")
    merged = merged[merged["_date"] >= "2000-01-01"]
    return merged


def _parse_form_responses_expenses(df: pd.DataFrame, type_col):
    """解析 Google 表單回覆裡的「支出」列（成本費用列表 / 實際花費兩欄）"""
    expense_col = next((c for c in df.columns if "成本費用列表" in str(c)), None)
    amount_col = next((c for c in df.columns if "實際花費" in str(c)), None)
    if expense_col is None or amount_col is None:
        return None

    expense_df = df[df[type_col].astype(str).str.strip() == "支出"].copy()
    if expense_df.empty:
        return None

    expense_df["_amount"] = pd.to_numeric(expense_df[amount_col], errors="coerce")
    expense_df = expense_df[
        expense_df[expense_col].notna()
        & expense_df["_amount"].notna()
        & (expense_df["_amount"] > 0)
    ]
    if expense_df.empty:
        return None

    expense_df = expense_df.rename(columns={expense_col: "支出項目"})
    expense_df["金額"] = expense_df["_amount"]
    return expense_df[["支出項目", "金額", "_amount"]].copy()


def _parse_legacy_sheet_expenses(df: pd.DataFrame):
    """解析舊格式工作表的支出資料"""
    expense_col = None
    for col in df.columns:
        if "支出項目" in str(col):
            expense_col = col
            break
    if expense_col is None:
        return None

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
        return None

    expense_df = df[df[expense_col].notna()].copy()
    expense_df["_amount"] = pd.to_numeric(expense_df[amount_col], errors="coerce")
    expense_df = expense_df[expense_df["_amount"].notna() & (expense_df["_amount"] > 0)]
    if expense_df.empty:
        return None
    expense_df = expense_df.rename(columns={expense_col: "支出項目", amount_col: "金額"})
    return expense_df[["支出項目", "金額", "_amount"]].copy()


def load_all_expenses(xl: "_SheetsAdapter", sheet_names: list) -> pd.DataFrame:
    """讀取多個工作表的支出資料"""
    frames = []
    for name in sheet_names:
        try:
            df = xl.parse(name)
        except Exception:
            continue

        type_col = _find_type_col(df)
        if type_col is not None:
            expense_df = _parse_form_responses_expenses(df, type_col)
        else:
            expense_df = _parse_legacy_sheet_expenses(df)

        if expense_df is None or expense_df.empty:
            continue
        expense_df["sheet"] = name
        frames.append(expense_df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
