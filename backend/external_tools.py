"""
外部感知工具模組
Phase 2：天氣（Open-Meteo，免費無需 Key）
Phase 3：網路搜尋（Tavily API）+ 日本潮流查詢
"""
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ─────────────────────────────────────────
# 常數
# ─────────────────────────────────────────

CITY_COORDS = {
    "台北": (25.0330, 121.5654),
    "新北": (25.0120, 121.4659),
    "桃園": (24.9936, 121.3010),
    "台中": (24.1477, 120.6736),
    "台南": (22.9999, 120.2269),
    "高雄": (22.6273, 120.3014),
}

# weathercode → 中文描述
WEATHER_CODES = {
    0: "晴天", 1: "大致晴朗", 2: "部分多雲", 3: "陰天",
    45: "霧", 48: "霧淞",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "陣雨", 81: "中陣雨", 82: "大陣雨",
    95: "雷雨", 96: "雷雨夾冰雹", 99: "強雷雨夾冰雹",
}


# ─────────────────────────────────────────
# 天氣工具（Open-Meteo，完全免費）
# ─────────────────────────────────────────

def tool_get_weather_forecast(city="台北", days=7):
    """
    取得台灣城市未來天氣預報。
    不需要 API Key，使用 Open-Meteo 免費服務。
    """
    lat, lon = CITY_COORDS.get(city, CITY_COORDS["台北"])
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": [
                    "temperature_2m_max", "temperature_2m_min",
                    "precipitation_sum", "weathercode",
                    "precipitation_probability_max",
                ],
                "timezone": "Asia/Taipei",
                "forecast_days": min(int(days), 16),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("daily", {})
    except Exception as e:
        return {"error": f"天氣 API 呼叫失敗：{e}"}

    dates = data.get("time", [])
    forecast = []
    for i, date in enumerate(dates):
        code = data["weathercode"][i]
        forecast.append({
            "date": date,
            "desc": WEATHER_CODES.get(code, f"code:{code}"),
            "temp_max": data["temperature_2m_max"][i],
            "temp_min": data["temperature_2m_min"][i],
            "rain_mm": data["precipitation_sum"][i],
            "rain_prob_pct": data["precipitation_probability_max"][i],
        })

    # 天氣摘要
    rainy_days = sum(1 for f in forecast if f["rain_mm"] > 1)
    avg_max = round(sum(f["temp_max"] for f in forecast) / len(forecast), 1) if forecast else 0

    return {
        "city": city,
        "period": f"未來{len(forecast)}天",
        "summary": {
            "avg_max_temp": avg_max,
            "rainy_days": rainy_days,
            "weather_note": _weather_shopping_note(avg_max, rainy_days, len(forecast)),
        },
        "daily": forecast,
    }


def _weather_shopping_note(avg_max, rainy_days, total_days):
    """根據天氣生成購物行為預判"""
    notes = []
    if avg_max < 18:
        notes.append("低溫，暖身商品（衛生褲、發熱貼、感冒藥）需求預計上升")
    elif avg_max > 28:
        notes.append("高溫，清涼飲品、防曬、薄外套需求預計上升")
    if rainy_days >= total_days // 2:
        notes.append("多雨天氣，室內消費傾向增加，零食類銷售通常較好")
    if not notes:
        notes.append("天氣平穩，無特別明顯的天氣驅動購物需求")
    return "；".join(notes)


# ─────────────────────────────────────────
# 網路搜尋工具（Brave Search API）
# ─────────────────────────────────────────

def tool_web_search(query, lang="zh-TW", num_results=8):
    """
    使用 Tavily API 搜尋網路資訊（專為 AI Agent 設計，回傳已整理的純文字內容）。
    需要在 .env 設定 TAVILY_API_KEY。
    lang: zh-TW（繁中市場）| ja（日本市場）| en（全球英語）
    """
    if not TAVILY_API_KEY:
        return {
            "error": "尚未設定 TAVILY_API_KEY",
            "hint": "請至 https://app.tavily.com 申請免費 Key，填入 backend/.env",
        }

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)

        # 根據語言調整搜尋關鍵字前綴
        lang_prefix = {"ja": "日本語 ", "en": ""}.get(lang, "")
        full_query = lang_prefix + query

        resp = client.search(
            query=full_query,
            search_depth="advanced",
            max_results=min(int(num_results), 10),
            include_answer=True,      # Tavily 會額外生成一個 AI 摘要
        )
    except Exception as e:
        return {"error": f"搜尋失敗：{e}"}

    results = []
    for item in resp.get("results", []):
        results.append({
            "title":   item.get("title", ""),
            "url":     item.get("url", ""),
            "content": item.get("content", "")[:400],  # 取前400字，節省 token
            "score":   round(item.get("score", 0), 2),
        })

    return {
        "query":   full_query,
        "lang":    lang,
        "summary": resp.get("answer", ""),   # Tavily 的 AI 整合摘要
        "count":   len(results),
        "results": results,
    }


def tool_search_japan_trends(category="服飾", keywords=None):
    """
    專門搜尋日本近期流行趨勢。
    整合多個日語關鍵字搜尋，回傳整理後的潮流資訊。
    category: 服飾 | 食品 | 醫藥 | 雜貨 | 美妝
    """
    cat_keyword_map = {
        "服飾": ["2026年春夏 ファッション トレンド", "今年 人気 レディース ファッション"],
        "食品": ["2026年 話題 食品 ランキング", "今 売れてる 日本 お菓子 輸出"],
        "醫藥": ["日本 人気 サプリ ドラッグストア ランキング", "2026 健康食品 ブーム"],
        "雜貨": ["日本 雑貨 人気 トレンド 2026", "日本 生活用品 話題"],
        "美妝": ["日本 コスメ 人気 2026", "ドラッグストア コスメ ランキング"],
    }

    queries = cat_keyword_map.get(category, cat_keyword_map["服飾"])
    if keywords:
        queries.insert(0, keywords)

    all_results = []
    for q in queries[:2]:  # 最多搜尋 2 個關鍵字組，節省 Tavily 用量
        result = tool_web_search(query=q, lang="ja", num_results=5)
        if "results" in result:
            all_results.extend(result["results"])

    # 去重（同 URL）
    seen, unique = set(), []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    return {
        "category": category,
        "search_queries": queries[:2],
        "total_results": len(unique),
        "results": unique[:10],
        "note": "以上為日本最新網路搜尋結果，請根據標題與描述判斷潮流趨勢",
    }


# ─────────────────────────────────────────
# Tool 對應表 & Claude Schema 定義
# ─────────────────────────────────────────

EXTERNAL_TOOL_FUNCTIONS = {
    "get_weather_forecast":  tool_get_weather_forecast,
    "web_search":            tool_web_search,
    "search_japan_trends":   tool_search_japan_trends,
}

EXTERNAL_TOOL_DEFINITIONS = [
    {
        "name": "get_weather_forecast",
        "description": (
            "取得台灣城市未來天氣預報（免費，無需 Key）。"
            "可用來判斷天氣對銷售的影響，以及建議本週應主打哪類商品。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "enum": ["台北", "新北", "桃園", "台中", "台南", "高雄"],
                    "description": "城市，預設台北",
                },
                "days": {"type": "integer", "description": "預報天數（1-16），預設7"},
            },
        },
    },
    {
        "name": "web_search",
        "description": (
            "搜尋網路上的最新資訊。"
            "lang=zh-TW 搜尋繁中市場，lang=ja 搜尋日本市場，lang=en 搜尋全球英語資訊。"
            "可用於查詢台灣消費趨勢、市場新聞、熱銷商品等。"
        ),
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query":       {"type": "string", "description": "搜尋關鍵字"},
                "lang":        {"type": "string", "enum": ["zh-TW", "ja", "en"], "description": "搜尋語言"},
                "num_results": {"type": "integer", "description": "結果數量，預設8"},
            },
        },
    },
    {
        "name": "search_japan_trends",
        "description": (
            "專門查詢日本近期流行趨勢，自動組合日語關鍵字進行搜尋。"
            "可查詢服飾、食品、醫藥、雜貨、美妝等類別在日本的最新流行資訊，"
            "用於判斷是否有值得引進的新商品。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["服飾", "食品", "醫藥", "雜貨", "美妝"],
                    "description": "查詢的商品類別",
                },
                "keywords": {
                    "type": "string",
                    "description": "額外的日語關鍵字（選填）",
                },
            },
        },
    },
]
