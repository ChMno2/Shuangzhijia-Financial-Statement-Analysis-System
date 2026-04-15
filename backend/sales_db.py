"""
本地 SQLite 銷售資料庫管理 + Agent 查詢工具
Phase 1：取代記憶體快取，支援動態 Tool 查詢
"""
import sqlite3
import os
from datetime import datetime, timedelta

SALES_DB_PATH = os.path.join(os.path.dirname(__file__), "sales.db")


# ─────────────────────────────────────────
# 初始化 & 同步
# ─────────────────────────────────────────

def init_sales_db():
    con = sqlite3.connect(SALES_DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS sales (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            date       TEXT NOT NULL,
            product    TEXT NOT NULL,
            category   TEXT,
            location   TEXT,
            revenue    REAL DEFAULT 0,
            quantity   INTEGER DEFAULT 0,
            unit_price REAL,
            cost       REAL,
            sheet_name TEXT
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            date   TEXT,
            item   TEXT,
            amount REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sync_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at   TEXT NOT NULL,
            latest_date TEXT,
            total_rows  INTEGER,
            status      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sales_date     ON sales(date);
        CREATE INDEX IF NOT EXISTS idx_sales_category ON sales(category);
        CREATE INDEX IF NOT EXISTS idx_sales_product  ON sales(product);
        CREATE INDEX IF NOT EXISTS idx_sales_location ON sales(location);
    """)
    con.commit()
    con.close()


def sync_from_dataframe(sales_df, expense_df=None):
    """將 pandas DataFrame 完整同步到 SQLite（全量更新）"""
    con = sqlite3.connect(SALES_DB_PATH)
    con.execute("DELETE FROM sales")

    rows_inserted = 0
    for _, row in sales_df.iterrows():
        date_val = row.get("_date")
        if date_val is None:
            continue
        date_str = str(date_val)[:10]

        cost = row.get("_cost")
        try:
            cost_val = float(cost) if cost is not None and str(cost) not in ("nan", "NaT", "None") else None
        except (ValueError, TypeError):
            cost_val = None

        con.execute("""
            INSERT INTO sales (date, product, category, location, revenue, quantity, unit_price, cost, sheet_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date_str,
            str(row.get("品名", "") or ""),
            str(row.get("大類", "") or "") or None,
            str(row.get("營業點", "") or "") or None,
            float(row.get("_sales", 0) or 0),
            int(row.get("銷售數量", 0) or 0),
            float(row.get("單價", 0)) if row.get("單價") else None,
            cost_val,
            str(row.get("_sheet", "") or "") or None,
        ))
        rows_inserted += 1

    if expense_df is not None and not expense_df.empty:
        con.execute("DELETE FROM expenses")
        for _, row in expense_df.iterrows():
            date_val = row.get("_date")
            date_str = str(date_val)[:10] if date_val else None
            con.execute(
                "INSERT INTO expenses (date, item, amount) VALUES (?, ?, ?)",
                (date_str, str(row.get("支出項目", "") or ""), float(row.get("_amount", 0) or 0))
            )

    latest_date = str(sales_df["_date"].max())[:10] if not sales_df.empty else None
    con.execute(
        "INSERT INTO sync_log (synced_at, latest_date, total_rows, status) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), latest_date, rows_inserted, "success")
    )
    con.commit()
    con.close()
    print(f"[SQLite] 已同步 {rows_inserted} 筆，最新日期：{latest_date}")
    return rows_inserted


def get_db_latest_date():
    con = sqlite3.connect(SALES_DB_PATH)
    row = con.execute("SELECT MAX(date) FROM sales").fetchone()
    con.close()
    return row[0] if row else None


# ─────────────────────────────────────────
# 工具函式
# ─────────────────────────────────────────

def _cutoff(con, days):
    latest = con.execute("SELECT MAX(date) FROM sales").fetchone()[0]
    if not latest:
        return "2000-01-01"
    latest_dt = datetime.fromisoformat(latest)
    return (latest_dt - timedelta(days=days)).strftime("%Y-%m-%d")


def tool_query_sales(days=30, category=None, location=None, product=None,
                     group_by="product", sort_by="revenue", sort_order="desc", limit=30):
    """
    查詢銷售資料。
    group_by: product | category | location | date
    sort_by:  revenue | quantity | margin_pct | transactions
    sort_order: desc（最高）| asc（最低）
    """
    con = sqlite3.connect(SALES_DB_PATH)
    con.row_factory = sqlite3.Row

    cutoff = _cutoff(con, days)
    where, params = ["date >= ?"], [cutoff]

    if category:
        where.append("category = ?")
        params.append(category)
    if location:
        where.append("location LIKE ?")
        params.append(f"%{location}%")
    if product:
        where.append("product LIKE ?")
        params.append(f"%{product}%")

    where_str = " AND ".join(where)
    group_cols = {
        "product":  "product, category, location",
        "category": "category",
        "location": "location",
        "date":     "date",
    }.get(group_by, "product, category")

    valid_sort = {"revenue", "quantity", "margin_pct", "transactions"}
    sort_col = sort_by if sort_by in valid_sort else "revenue"
    order = "ASC" if sort_order.lower() == "asc" else "DESC"

    sql = f"""
        SELECT {group_cols},
               ROUND(SUM(revenue), 0) AS revenue,
               SUM(quantity)          AS quantity,
               ROUND(AVG(
                 CASE WHEN cost > 0 AND cost IS NOT NULL
                      THEN (revenue - cost) / NULLIF(revenue, 0) * 100
                 END), 1)             AS margin_pct,
               COUNT(*)               AS transactions
        FROM   sales
        WHERE  {where_str}
        GROUP  BY {group_cols}
        ORDER  BY {sort_col} {order}
        LIMIT  {int(limit)}
    """
    rows = con.execute(sql, params).fetchall()
    result = [dict(r) for r in rows]
    con.close()

    return {
        "meta": {
            "period": f"近 {days} 天",
            "filters": {k: v for k, v in
                        {"category": category, "location": location, "product": product}.items() if v},
            "group_by": group_by,
            "sorted_by": f"{sort_by} {sort_order}",
            "count": len(result),
        },
        "data": result,
    }


def tool_compare_periods(metric="revenue", days_a=30, days_b=60, group_by="category"):
    """比較兩個時間段的銷售差異，找出成長或衰退。"""
    con = sqlite3.connect(SALES_DB_PATH)
    con.row_factory = sqlite3.Row

    cutoff_a = _cutoff(con, days_a)
    cutoff_b = _cutoff(con, days_b)
    grp = {"category": "category", "location": "location", "product": "product"}.get(group_by, "category")

    def fetch(cutoff):
        sql = f"""
            SELECT {grp} AS name,
                   ROUND(SUM(revenue), 0) AS revenue,
                   SUM(quantity) AS quantity,
                   COUNT(*) AS transactions
            FROM sales WHERE date >= ? AND {grp} IS NOT NULL
            GROUP BY {grp}
        """
        return {r["name"]: dict(r) for r in con.execute(sql, [cutoff]).fetchall()}

    data_a, data_b = fetch(cutoff_a), fetch(cutoff_b)
    con.close()

    result = []
    for k in sorted(set(data_a) | set(data_b)):
        a, b = data_a.get(k, {}), data_b.get(k, {})
        rev_a = a.get("revenue", 0) or 0
        rev_b = b.get("revenue", 0) or 0
        change = round((rev_a - rev_b) / rev_b * 100, 1) if rev_b > 0 else None
        result.append({
            "name": k,
            f"近{days_a}天營收": rev_a,
            f"近{days_b}天營收": rev_b,
            "營收變化%": change,
            f"近{days_a}天數量": a.get("quantity", 0),
            f"近{days_b}天數量": b.get("quantity", 0),
        })

    result.sort(key=lambda x: x[f"近{days_a}天營收"], reverse=True)
    return {"period_a": f"近{days_a}天", "period_b": f"近{days_b}天", "group_by": group_by, "data": result}


def tool_get_trend(target, target_type="category", days=90, granularity="week"):
    """
    取得商品、類別或地點的銷售趨勢。
    target_type: category | product | location
    granularity: day | week | month
    """
    con = sqlite3.connect(SALES_DB_PATH)
    con.row_factory = sqlite3.Row

    cutoff = _cutoff(con, days)
    fmt = {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m"}.get(granularity, "%Y-%W")
    col = {"category": "category", "product": "product", "location": "location"}.get(target_type, "category")

    sql = f"""
        SELECT strftime(?, date) AS period,
               ROUND(SUM(revenue), 0) AS revenue,
               SUM(quantity) AS quantity
        FROM   sales
        WHERE  date >= ? AND {col} LIKE ?
        GROUP  BY period
        ORDER  BY period
    """
    rows = con.execute(sql, [fmt, cutoff, f"%{target}%"]).fetchall()
    con.close()

    return {
        "target": target,
        "target_type": target_type,
        "granularity": granularity,
        "period": f"近{days}天",
        "data": [dict(r) for r in rows],
    }


def tool_get_summary(days=30):
    """取得整體業績摘要，含各類別佔比與毛利率。"""
    con = sqlite3.connect(SALES_DB_PATH)
    con.row_factory = sqlite3.Row

    cutoff = _cutoff(con, days)

    main = dict(con.execute("""
        SELECT ROUND(SUM(revenue), 0)   AS total_revenue,
               SUM(quantity)            AS total_quantity,
               COUNT(*)                 AS transactions,
               COUNT(DISTINCT product)  AS unique_products,
               MIN(date)                AS from_date,
               MAX(date)                AS to_date,
               ROUND(AVG(
                 CASE WHEN cost > 0 AND cost IS NOT NULL
                      THEN (revenue - cost) / NULLIF(revenue, 0) * 100
                 END), 1)               AS avg_margin_pct
        FROM   sales WHERE date >= ?
    """, [cutoff]).fetchone())

    cats = [dict(r) for r in con.execute("""
        SELECT category,
               ROUND(SUM(revenue), 0) AS revenue,
               SUM(quantity) AS quantity
        FROM   sales WHERE date >= ? AND category IS NOT NULL
        GROUP  BY category ORDER BY revenue DESC
    """, [cutoff]).fetchall()]

    exp = con.execute("SELECT ROUND(SUM(amount), 0) AS total FROM expenses").fetchone()
    con.close()

    total = main.get("total_revenue") or 1
    for c in cats:
        c["revenue_pct"] = round(c["revenue"] / total * 100, 1)

    return {
        **main,
        "period": f"近{days}天",
        "category_breakdown": cats,
        "total_expense": dict(exp)["total"] if exp else 0,
    }


# ─────────────────────────────────────────
# Tool 對應表 & Claude Schema 定義
# ─────────────────────────────────────────

TOOL_FUNCTIONS = {
    "query_sales":     tool_query_sales,
    "compare_periods": tool_compare_periods,
    "get_trend":       tool_get_trend,
    "get_summary":     tool_get_summary,
}

TOOL_DEFINITIONS = [
    {
        "name": "query_sales",
        "description": (
            "查詢銷售資料。可依時間範圍、類別、地點、商品名稱篩選，"
            "支援按商品/類別/地點/日期分組，可用 sort_order=asc 找最差商品。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days":       {"type": "integer", "description": "查詢最近幾天，預設30"},
                "category":   {"type": "string",  "description": "商品大類：服飾/食品/醫藥/雜貨"},
                "location":   {"type": "string",  "description": "營業點：光復/新埔"},
                "product":    {"type": "string",  "description": "商品名稱（模糊搜尋）"},
                "group_by":   {"type": "string",  "enum": ["product", "category", "location", "date"]},
                "sort_by":    {"type": "string",  "enum": ["revenue", "quantity", "margin_pct", "transactions"]},
                "sort_order": {"type": "string",  "enum": ["desc", "asc"], "description": "desc最高/asc最低"},
                "limit":      {"type": "integer", "description": "回傳筆數，預設30"},
            },
        },
    },
    {
        "name": "compare_periods",
        "description": "比較兩個時間段的銷售差異，找出成長或衰退的類別/商品/地點。",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric":   {"type": "string", "enum": ["revenue", "quantity"]},
                "days_a":   {"type": "integer", "description": "近期天數（短），預設30"},
                "days_b":   {"type": "integer", "description": "對比天數（長），預設60"},
                "group_by": {"type": "string",  "enum": ["category", "location", "product"]},
            },
        },
    },
    {
        "name": "get_trend",
        "description": "查看特定商品、類別或地點的銷售趨勢走向（逐週/月變化）。",
        "input_schema": {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target":      {"type": "string", "description": "商品名、類別名或地點名"},
                "target_type": {"type": "string", "enum": ["category", "product", "location"]},
                "days":        {"type": "integer", "description": "查詢天數，預設90"},
                "granularity": {"type": "string",  "enum": ["day", "week", "month"]},
            },
        },
    },
    {
        "name": "get_summary",
        "description": "取得整體業績摘要，含總營收、交易筆數、平均毛利率、各類別佔比。",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "查詢最近幾天，預設30"},
            },
        },
    },
]
