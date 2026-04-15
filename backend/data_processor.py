"""
資料處理模組：將雙之家日記帳 Excel 轉為後台報表格式
"""
import pandas as pd
from datetime import datetime, timedelta


def _filter_by_range(df: pd.DataFrame, days: int = None,
                     start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """依天數或起迄日期篩選 DataFrame"""
    latest = df["_date"].max()

    if start_date and end_date:
        s = pd.Timestamp(start_date)
        e = pd.Timestamp(end_date) + timedelta(days=1)
        return df[(df["_date"] >= s) & (df["_date"] < e)]
    elif days:
        cutoff = latest - timedelta(days=days)
        return df[df["_date"] >= cutoff]
    else:
        cutoff = latest - timedelta(days=30)
        return df[df["_date"] >= cutoff]


def build_dashboard_data(sales_df: pd.DataFrame, expense_df: pd.DataFrame = None) -> dict:
    """建立完整儀表板資料（以資料最新日期為基準）"""
    if sales_df.empty:
        return {}

    # 以資料最新日期為基準
    latest = sales_df["_date"].max()
    ref = latest.to_pydatetime() if hasattr(latest, "to_pydatetime") else latest

    week_start = ref - timedelta(days=ref.weekday())
    last_week_start = week_start - timedelta(days=7)
    month_start = ref.replace(day=1)

    this_week = sales_df[sales_df["_date"] >= week_start]
    last_week = sales_df[(sales_df["_date"] >= last_week_start) & (sales_df["_date"] < week_start)]
    this_month = sales_df[sales_df["_date"] >= month_start]
    last_30 = sales_df[sales_df["_date"] >= ref - timedelta(days=30)]

    this_week_rev = float(this_week["_sales"].sum())
    last_week_rev = float(last_week["_sales"].sum())
    this_month_rev = float(this_month["_sales"].sum())
    week_growth = round((this_week_rev - last_week_rev) / last_week_rev * 100, 1) if last_week_rev > 0 else 0.0

    # 每日銷售（近30天）
    daily = (last_30.groupby(last_30["_date"].dt.date)["_sales"].sum().reset_index())
    daily.columns = ["date", "revenue"]
    daily["date"] = daily["date"].astype(str)
    daily_list = daily.sort_values("date").to_dict(orient="records")

    # 類別銷售佔比（近30天）
    category_list = []
    if "大類" in last_30.columns:
        cat = last_30.groupby("大類")["_sales"].sum().reset_index()
        cat.columns = ["category", "revenue"]
        total = cat["revenue"].sum()
        cat["percentage"] = (cat["revenue"] / total * 100).round(1)
        category_list = cat.sort_values("revenue", ascending=False).to_dict(orient="records")

    # 商品排行（近30天）
    products_list = build_products_list(last_30)

    # 營業點分析（近30天）
    location_list = []
    if "營業點" in last_30.columns:
        loc = last_30.groupby("營業點")["_sales"].sum().reset_index()
        loc.columns = ["location", "revenue"]
        total_loc = loc["revenue"].sum()
        loc["percentage"] = (loc["revenue"] / total_loc * 100).round(1)
        location_list = loc.sort_values("revenue", ascending=False).to_dict(orient="records")

    # 支出摘要
    total_expense = 0.0
    expense_list = []
    if expense_df is not None and not expense_df.empty:
        total_expense = float(expense_df["_amount"].sum())
        exp_group = expense_df.groupby("支出項目")["_amount"].sum().reset_index()
        exp_group.columns = ["item", "amount"]
        expense_list = exp_group.sort_values("amount", ascending=False).head(20).to_dict(orient="records")

    # 商品種類數
    unique_products = int(last_30["品名"].nunique()) if "品名" in last_30.columns else 0

    return {
        "summary": {
            "this_week_revenue": this_week_rev,
            "last_week_revenue": last_week_rev,
            "week_growth": week_growth,
            "this_month_revenue": this_month_rev,
            "total_transactions": len(last_30),
            "total_expense": total_expense,
            "unique_products": unique_products,
            "data_latest_date": str(ref.date()),
        },
        "daily_sales": daily_list,
        "category_sales": category_list,
        "products": products_list,
        "location_sales": location_list,
        "expenses": expense_list,
    }


def build_period_summary(sales_df: pd.DataFrame, days: int) -> dict:
    """建立指定天數的完整銷售摘要（供 AI 問答使用，含全商品明細與毛利率）"""
    if sales_df.empty:
        return {}
    df = _filter_by_range(sales_df, days=days)
    if df.empty:
        return {}

    total_revenue = float(df["_sales"].sum())
    transactions = len(df)

    # 類別銷售
    category_list = []
    if "大類" in df.columns:
        cat = df.groupby("大類")["_sales"].sum().reset_index()
        cat.columns = ["category", "revenue"]
        total = cat["revenue"].sum()
        cat["percentage"] = (cat["revenue"] / total * 100).round(1)
        category_list = cat.sort_values("revenue", ascending=False).to_dict(orient="records")

    # 全商品明細（含數量、毛利率）
    products_list = []
    if "品名" in df.columns:
        agg = {"_sales": "sum"}
        if "銷售數量" in df.columns:
            agg["銷售數量"] = "sum"
        if "大類" in df.columns:
            agg["大類"] = "first"

        prod = df.groupby("品名").agg(agg).reset_index()
        prod = prod.rename(columns={"_sales": "revenue", "銷售數量": "quantity", "大類": "category"})

        # 加入成本與毛利率
        has_cost = "_cost" in df.columns and df["_cost"].notna().sum() > 0
        if has_cost:
            cost_df = df[df["_cost"].notna() & (df["_cost"] > 0)]
            if not cost_df.empty:
                cost_agg = {"_cost": "sum", "_sales": "sum"}
                prod_cost = cost_df.groupby("品名").agg(cost_agg).reset_index()
                prod_cost = prod_cost.rename(columns={"_cost": "cost", "_sales": "cost_revenue"})
                prod = prod.merge(prod_cost, on="品名", how="left")
                mask = prod["cost_revenue"].notna() & (prod["cost_revenue"] > 0)
                prod.loc[mask, "margin"] = (
                    (prod.loc[mask, "cost_revenue"] - prod.loc[mask, "cost"])
                    / prod.loc[mask, "cost_revenue"] * 100
                ).round(1)

        prod["revenue"] = prod["revenue"].round(0)
        prod = prod.sort_values("revenue", ascending=False)

        # NaN → None
        for col in ["cost", "cost_revenue", "margin"]:
            if col in prod.columns:
                prod[col] = prod[col].where(prod[col].notna(), None)

        products_list = prod.to_dict(orient="records")

    return {
        "days": days,
        "total_revenue": round(total_revenue, 0),
        "transactions": transactions,
        "category_sales": category_list,
        "all_products": products_list,   # 全部商品，高到低排序
    }


def build_products_list(df: pd.DataFrame) -> list:
    """從銷售 DataFrame 建立商品排行"""
    if df.empty or "品名" not in df.columns:
        return []

    agg = {"_sales": "sum"}
    if "銷售數量" in df.columns:
        agg["銷售數量"] = "sum"
    if "大類" in df.columns:
        agg["大類"] = "first"

    prod = df.groupby("品名").agg(agg).reset_index()
    prod = prod.rename(columns={"_sales": "revenue", "銷售數量": "quantity", "大類": "category"})
    prod["revenue"] = prod["revenue"].round(0)
    return prod.sort_values("revenue", ascending=False).head(50).to_dict(orient="records")


def get_daily_detail(sales_df: pd.DataFrame, days: int = 30,
                     start_date: str = None, end_date: str = None) -> list:
    """
    取得每日銷售明細，含每日 TOP2 商品
    """
    df = _filter_by_range(sales_df, days, start_date, end_date)
    if df.empty:
        return []

    result = []
    has_product = "品名" in df.columns

    for date_val, grp in df.groupby(df["_date"].dt.date):
        revenue = float(grp["_sales"].sum())
        qty = int(grp["銷售數量"].sum()) if "銷售數量" in grp.columns else None

        top2 = []
        if has_product:
            top = grp.groupby("品名")["_sales"].sum().nlargest(2)
            for name, rev in top.items():
                top2.append({"name": str(name), "revenue": float(rev)})

        row = {"date": str(date_val), "revenue": revenue, "top_products": top2}
        if qty is not None:
            row["quantity"] = qty
        result.append(row)

    return sorted(result, key=lambda x: x["date"])


def get_profit_report(sales_df: pd.DataFrame, days: int = 30,
                      start_date: str = None, end_date: str = None) -> dict:
    """
    利潤分析報表：
    - 有 銷售成本/銷售淨利 欄位時使用實際成本
    - 否則僅回傳銷售額供參考
    """
    df = _filter_by_range(sales_df, days, start_date, end_date)
    if df.empty:
        return {}

    # _cost 欄位由 google_sheets.py 統一建立（銷售成本 > 進貨總成本 > 進貨單價×數量）
    has_cost = bool("_cost" in df.columns and df["_cost"].notna().sum() > 0)
    has_profit = bool("銷售淨利" in df.columns and df["銷售淨利"].notna().sum() > 0)

    # 有成本記錄的列（_cost > 0）
    cost_df = df[df["_cost"].notna() & (df["_cost"] > 0)].copy() if has_cost else pd.DataFrame()
    cost_rows = len(cost_df)
    total_rows = len(df)

    # ─── 各大類利潤 ─────────────────────────
    category_profit = []
    if "大類" in df.columns:
        for cat, grp in df.groupby("大類"):
            revenue = float(grp["_sales"].sum())
            qty = int(grp["銷售數量"].sum()) if "銷售數量" in grp.columns else 0
            avg_price = revenue / qty if qty > 0 else 0

            row = {
                "category": cat,
                "revenue": round(revenue, 0),
                "quantity": qty,
                "avg_price": round(avg_price, 1),
            }

            if has_cost and not cost_df.empty and "大類" in cost_df.columns:
                grp_cost = cost_df[cost_df["大類"] == cat]
                if not grp_cost.empty:
                    cost_val = float(grp_cost["_cost"].sum())
                    cost_revenue = float(grp_cost["_sales"].sum())
                    row["cost"] = round(cost_val, 0)
                    row["cost_coverage"] = len(grp_cost)
                    row["profit"] = round(cost_revenue - cost_val, 0)
                    if cost_revenue > 0:
                        row["margin"] = round((cost_revenue - cost_val) / cost_revenue * 100, 1)

            category_profit.append(row)

        category_profit.sort(key=lambda x: x["revenue"], reverse=True)

    # ─── 各商品利潤 TOP 20 ───────────────────
    product_profit = []
    if "品名" in df.columns:
        agg_all = {"_sales": "sum"}
        if "銷售數量" in df.columns:
            agg_all["銷售數量"] = "sum"
        if "大類" in df.columns:
            agg_all["大類"] = "first"

        prod_all = df.groupby("品名").agg(agg_all).reset_index()
        prod_all = prod_all.rename(columns={"_sales": "revenue", "銷售數量": "quantity", "大類": "category"})

        # 合併成本（從有 _cost 的列）
        if has_cost and not cost_df.empty:
            agg_cost = {"_cost": "sum", "_sales": "sum"}
            prod_cost = cost_df.groupby("品名").agg(agg_cost).reset_index()
            prod_cost = prod_cost.rename(columns={"_cost": "cost", "_sales": "cost_revenue"})
            prod_all = prod_all.merge(prod_cost, on="品名", how="left")

            mask = prod_all["cost_revenue"].notna() & (prod_all["cost_revenue"] > 0)
            prod_all.loc[mask, "profit"] = prod_all.loc[mask, "cost_revenue"] - prod_all.loc[mask, "cost"]
            prod_all.loc[mask, "margin"] = (
                prod_all.loc[mask, "profit"] / prod_all.loc[mask, "cost_revenue"] * 100
            ).round(1)

        prod_all["revenue"] = prod_all["revenue"].round(0)
        prod_all = prod_all.sort_values("revenue", ascending=False).head(20)
        product_profit = prod_all.to_dict(orient="records")

        # NaN → None（JSON 安全）
        for p in product_profit:
            for k, v in list(p.items()):
                if isinstance(v, float) and (v != v):
                    p[k] = None

    # ─── 整體摘要 ────────────────────────────
    total_revenue = float(df["_sales"].sum())

    summary = {
        "total_revenue": round(total_revenue, 0),
        "has_cost_data": has_cost,
        "transactions": total_rows,
        "cost_coverage_rows": cost_rows,
        "cost_coverage_pct": round(cost_rows / total_rows * 100, 1) if total_rows > 0 else 0,
    }

    if has_cost and not cost_df.empty:
        cost_total = float(cost_df["_cost"].sum())
        cost_rev_total = float(cost_df["_sales"].sum())
        summary["total_cost"] = round(cost_total, 0)
        summary["cost_basis_revenue"] = round(cost_rev_total, 0)
        summary["total_profit"] = round(cost_rev_total - cost_total, 0)
        summary["overall_margin"] = round((cost_rev_total - cost_total) / cost_rev_total * 100, 1) if cost_rev_total > 0 else 0

    return {
        "summary": summary,
        "category_profit": category_profit,
        "product_profit": product_profit,
    }
