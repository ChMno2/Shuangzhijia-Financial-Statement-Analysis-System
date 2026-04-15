"""
LLM 問答分析模組：使用 Claude API 針對商業資料進行自然語言分析
Phase 1 升級：加入 tool_use Agent，取代固定 context 問答
"""
import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

AGENT_SYSTEM_PROMPT = """你是雙之家的商業智慧分析師。雙之家販售日本進口商品（服飾、醫藥、食品、雜貨），有光復、新埔等營業點。

你擁有以下工具：
【內部資料】query_sales、compare_periods、get_trend、get_summary — 查詢完整銷售資料庫
【外部感知】get_weather_forecast — 取得台灣天氣預報
【網路搜尋】web_search — 搜尋台灣或全球市場資訊（lang=zh-TW 或 en）
【日本潮流】search_japan_trends — 查詢日本最新流行趨勢（自動使用日語搜尋）

使用原則：
- 先呼叫工具取得數據，再根據數據回答，不要憑空推測
- 問到銷售數據 → 用內部工具；問到天氣 → 用天氣工具；問到市場/潮流 → 用搜尋工具
- 複合問題（如「天氣+進貨建議」）可同時或依序呼叫多個工具

回答規則：
- 用繁體中文回答
- 不使用 emoji
- 直接回答，不加開場白或結尾客套語
- 數字精確到個位，必須引用工具回傳的實際數值
- 每個結論需說明原因（數量、毛利率、趨勢、天氣影響等）
- 引用網路搜尋結果時，說明資訊來源的標題
- 資料有限時，用現有資料盡量回答，末尾一句說明限制"""


def analyze_with_agent(question: str, chat_history: list = None) -> str:
    """
    使用 Claude tool_use Agent 動態查詢資料庫與外部資訊回答問題。
    - 內部工具：query_sales、compare_periods、get_trend、get_summary（SQLite）
    - 外部工具：get_weather_forecast、web_search、search_japan_trends
    """
    from sales_db import TOOL_DEFINITIONS, TOOL_FUNCTIONS
    from external_tools import EXTERNAL_TOOL_DEFINITIONS, EXTERNAL_TOOL_FUNCTIONS

    all_tools = TOOL_DEFINITIONS + EXTERNAL_TOOL_DEFINITIONS
    all_functions = {**TOOL_FUNCTIONS, **EXTERNAL_TOOL_FUNCTIONS}

    messages = []
    if chat_history:
        for msg in chat_history[-10:]:
            if isinstance(msg.get("content"), str):
                messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    for _ in range(8):  # 最多 8 輪（外部搜尋可能需要多次）
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            system=AGENT_SYSTEM_PROMPT,
            tools=all_tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            texts = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(texts)

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        fn = all_functions.get(block.name)
                        result = fn(**block.input) if fn else {"error": f"未知工具：{block.name}"}
                    except Exception as e:
                        result = {"error": str(e)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "分析過程出現異常，請重試。"


def build_data_context(data: dict) -> str:
    """將報表資料轉為 LLM 可讀的文字上下文"""
    lines = []

    summary = data.get("summary", {})
    if summary:
        lines.append("=== 業績摘要（近 30 天資料）===")
        lines.append(f"本週營收：NT$ {summary.get('this_week_revenue', 0):,.0f}")
        lines.append(f"上週營收：NT$ {summary.get('last_week_revenue', 0):,.0f}")
        lines.append(f"週成長率：{summary.get('week_growth', 0)}%")
        lines.append(f"本月累計營收：NT$ {summary.get('this_month_revenue', 0):,.0f}")
        lines.append(f"近30天交易筆數：{summary.get('total_transactions', 0)} 筆")
        if summary.get("total_expense"):
            lines.append(f"近期支出合計：NT$ {summary.get('total_expense', 0):,.0f}")
        lines.append("")

    category_sales = data.get("category_sales", [])
    if category_sales:
        lines.append("=== 近30天各大類銷售 ===")
        for c in category_sales:
            lines.append(
                f"{c.get('category', '')}：NT$ {c.get('revenue', 0):,.0f}（{c.get('percentage', 0)}%）"
            )
        lines.append("")

    location_sales = data.get("location_sales", [])
    if location_sales:
        lines.append("=== 各營業點銷售 ===")
        for loc in location_sales:
            lines.append(
                f"{loc.get('location', '')}：NT$ {loc.get('revenue', 0):,.0f}（{loc.get('percentage', 0)}%）"
            )
        lines.append("")

    products = data.get("products", [])
    if products:
        lines.append("=== 近30天暢銷商品 TOP 20 ===")
        for p in products[:20]:
            lines.append(
                f"{p.get('品名', '')} | 類別：{p.get('category', '')} | "
                f"銷售額：NT${p.get('revenue', 0):,.0f} | 數量：{p.get('quantity', 0)}"
            )
        lines.append("")

    daily_sales = data.get("daily_sales", [])
    if daily_sales:
        lines.append("=== 近 7 天每日銷售 ===")
        for d in daily_sales[-7:]:
            lines.append(f"{d.get('date', '')}：NT$ {d.get('revenue', 0):,.0f}")

    expenses = data.get("expenses", [])
    if expenses:
        lines.append("")
        lines.append("=== 近期支出項目 ===")
        for e in expenses[:10]:
            lines.append(f"{e.get('item', '')}：NT$ {e.get('amount', 0):,.0f}")

    for period_key, label in [("period_60", "近60天"), ("period_90", "近90天")]:
        p = data.get(period_key, {})
        if not p:
            continue
        lines.append("")
        lines.append(f"=== {label}完整資料 ===")
        lines.append(f"總營收：NT$ {p.get('total_revenue', 0):,.0f}，交易筆數：{p.get('transactions', 0)}")
        for c in p.get("category_sales", []):
            lines.append(f"  {c.get('category', '')}：NT$ {c.get('revenue', 0):,.0f}（{c.get('percentage', 0)}%）")
        all_products = p.get("all_products", [])
        if all_products:
            lines.append(f"  全商品銷售明細（高至低，共 {len(all_products)} 項）：")
            for t in all_products:
                qty = t.get("quantity", "")
                margin = t.get("margin")
                margin_str = f" | 毛利率：{margin}%" if margin is not None else ""
                qty_str = f" | 數量：{qty}" if qty != "" else ""
                lines.append(f"    {t.get('品名', '')}：NT$ {t.get('revenue', 0):,.0f}{qty_str}{margin_str}")

    return "\n".join(lines)


def analyze_with_llm(question: str, data: dict, chat_history: list = None) -> str:
    """
    使用 Claude 回答使用者關於報表的問題

    Args:
        question: 使用者問題
        data: 完整的報表資料 dict
        chat_history: 對話歷史 [{"role": "user/assistant", "content": "..."}]
    """
    data_context = build_data_context(data)

    system_prompt = f"""你是雙之家的商業數據分析師。雙之家販售日本進口商品（服飾、醫藥、食品、雜貨），有光復、新埔等營業點。

規則：
- 用繁體中文回答
- 不使用 emoji
- 直接針對問題回答，不加開場白或結尾客套語
- 數字引用資料原文，精確到個位
- 針對每個分析結論，必須說明原因（引用數量、毛利率、趨勢等具體數據）
- 若問到商品表現，需列出：銷售額、銷售數量、毛利率（有資料時），並解釋為何表現好或差
- 資料有限時，用現有資料盡量回答，並在末尾一句說明限制

今天日期：{__import__('datetime').datetime.today().strftime('%Y/%m/%d')}

銷售資料：
{data_context}"""

    messages = []

    # 加入對話歷史
    if chat_history:
        for msg in chat_history[-10:]:  # 最多保留最近 10 輪
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    # 加入當前問題
    messages.append({"role": "user", "content": question})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=system_prompt,
        messages=messages
    )

    return response.content[0].text


def generate_weekly_report(data: dict) -> str:
    """自動生成本週營業週報"""
    data_context = build_data_context(data)

    prompt = f"""請根據以下資料，生成一份專業的本週營業週報，格式清晰，使用繁體中文。

包含以下部分：
1. 本週業績摘要（與上週比較）
2. 暢銷商品 TOP 3 分析
3. 各類別銷售表現
4. 需要注意的問題（如庫存不足）
5. 下週建議行動

資料：
{data_context}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text
