"""
LLM 問答分析模組：使用 Claude 或 Gemini 針對商業資料進行自然語言分析
Phase 1 升級：加入 tool_use Agent，取代固定 context 問答
Phase 2：加入 Gemini 版本 agent（免費替代方案），由 LLM_PROVIDER 環境變數切換
"""
import os
import json
import urllib.error
import urllib.request
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# 預設 flash-lite：免費 RPD 1500（flash 才 250 容易被擋）
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

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
- 全部用繁體中文回答，包含搜尋到的日文/英文關鍵字、趨勢用語也要翻譯成中文，
  不要直接原文照抄（例如日文的「アースカラー」要寫成「大地色系」）
- 不使用 emoji
- 直接回答，不加開場白或結尾客套語
- 不要附上資料來源網站名稱、書名號引用或連結，只講結論本身
- 數字精確到個位，必須引用工具回傳的實際數值
- 每個結論需說明原因（數量、毛利率、趨勢、天氣影響等）
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


# ─────────────────────────────────────────
# Gemini 版本的 Agent（免費替代方案）
# ─────────────────────────────────────────

def _claude_tools_to_gemini(claude_tools: list) -> list:
    """把 Claude 的 tool definitions 轉成 Gemini functionDeclarations 格式"""
    out = []
    for t in claude_tools:
        out.append({
            "name": t["name"],
            "description": t["description"],
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        })
    return out


def _gemini_post(payload: dict, timeout: int = 60) -> dict:
    """呼叫 Gemini generateContent API"""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def analyze_with_agent_gemini(question: str, chat_history: list = None) -> str:
    """
    使用 Gemini function calling 的 Agent 版本（免費）
    - 同樣可用 query_sales / get_summary / get_weather_forecast / web_search 等工具
    - 適用於 LINE 雙向對話以節省 token 成本
    """
    if not GEMINI_API_KEY:
        return "（GEMINI_API_KEY 未設定，請在 Render 環境變數加上）"

    from sales_db import TOOL_DEFINITIONS, TOOL_FUNCTIONS
    from external_tools import EXTERNAL_TOOL_DEFINITIONS, EXTERNAL_TOOL_FUNCTIONS

    all_claude_tools = TOOL_DEFINITIONS + EXTERNAL_TOOL_DEFINITIONS
    all_functions = {**TOOL_FUNCTIONS, **EXTERNAL_TOOL_FUNCTIONS}
    gemini_tools = [{"functionDeclarations": _claude_tools_to_gemini(all_claude_tools)}]

    # 組對話歷史（Gemini 用 model 取代 assistant，parts: [{text}]）
    contents: list[dict] = []
    if chat_history:
        for msg in chat_history[-10:]:
            content = msg.get("content")
            if not isinstance(content, str):
                continue
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": content}]})
    contents.append({"role": "user", "parts": [{"text": question}]})

    base_payload = {
        "tools": gemini_tools,
        "systemInstruction": {"parts": [{"text": AGENT_SYSTEM_PROMPT}]},
        "generationConfig": {"maxOutputTokens": 2500, "temperature": 0.3},
    }

    for _ in range(8):  # 最多 8 輪工具呼叫
        try:
            response = _gemini_post({**base_payload, "contents": contents})
        except urllib.error.HTTPError as e:
            return f"（Gemini API 失敗 HTTP {e.code}：{e.read().decode()[:200]}）"
        except Exception as e:
            return f"（Gemini 呼叫失敗：{e}）"

        candidates = response.get("candidates") or []
        if not candidates:
            # 可能因 safety filter 被擋
            block_reason = response.get("promptFeedback", {}).get("blockReason", "未知")
            return f"（Gemini 沒有回應，blockReason={block_reason}）"

        parts = candidates[0].get("content", {}).get("parts") or []
        function_calls = [p["functionCall"] for p in parts if "functionCall" in p]

        if not function_calls:
            # 無工具呼叫 → 取出純文字當最終答案
            text_pieces = [p.get("text", "") for p in parts if "text" in p]
            return ("\n".join(t for t in text_pieces if t)).strip() or "（無回應）"

        # 把這輪 model 的工具呼叫加進對話
        contents.append({"role": "model", "parts": parts})

        # 執行工具、把結果回填
        tool_responses = []
        for fc in function_calls:
            name = fc.get("name")
            args = fc.get("args") or {}
            try:
                fn = all_functions.get(name)
                result = fn(**args) if fn else {"error": f"未知工具：{name}"}
            except Exception as e:
                result = {"error": str(e)}
            tool_responses.append({
                "functionResponse": {
                    "name": name,
                    "response": {"content": result},
                }
            })
        contents.append({"role": "function", "parts": tool_responses})

    return "分析過程超過工具呼叫上限，請換個方式問問看。"


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
    """
    自動生成本週營業週報（LINE 推送用）
    產出規則：純文字、無 markdown 符號、語句精簡、最後給進貨建議。
    """
    data_context = build_data_context(data)

    prompt = f"""請根據以下資料生成本週營業週報，給 LINE 訊息使用。

【格式限制 — 必須嚴格遵守】
- 純文字輸出，不可使用任何 markdown 符號：禁用 # * _ ` > [] ()
- 不要用 ** 或 __ 標記粗體 / 斜體（LINE 無法渲染）
- 每段用阿拉伯數字 + 頓號當小標（例：1、本週業績）
- 條列用「・」（中黑點）或數字編號，不要用 - 或 *
- 一句話講完就好，不要解釋過程，不要寫「綜上所述」「整體而言」等贅字
- 數字精確到個位並加千分位逗號（例：NT$ 167,280）
- 全文控制在 600 字以內

【內容結構】
1、核心數據一覽（本週營收、月累計、週成長率、近30天交易筆數）
2、銷售走勢（一兩句說明本週相對上週的趨勢與原因）
3、TOP 3 商品摘要（商品名 + 銷售額 + 是否有特別現象）
4、下週進貨建議（哪些品項該補、哪些可暫緩，每項一句話內含理由）

資料：
{data_context}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text

    # 雙重保險：即使模型違反指示，事後清掉常見 markdown 符號
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)   # **bold**
    text = re.sub(r'__(.+?)__', r'\1', text)       # __bold__
    text = re.sub(r'(?m)^\s*[#>]+\s*', '', text)   # # heading / > quote
    text = re.sub(r'(?m)^\s*[-\*]\s+', '・', text)  # - / * 條列符號
    text = re.sub(r'`([^`]+)`', r'\1', text)       # `code`
    return text.strip()
