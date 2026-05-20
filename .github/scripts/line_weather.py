"""
雙之家 LINE 每日天氣預報腳本
排程：每日 04:00 台灣時間 推送

資料來源：中央氣象署（CWA）Open Data
  - F-D0047-069 / F-D0047-071：新北市 / 台北市 鄉鎮天氣預報（每 3 小時，未來 1 週）
  - W-C0033-001：天氣特報（含颱風警報）

地點：
  - 新北市板橋區（新埔捷運站附近）
  - 台北市信義區（市政府捷運站附近）

所需環境變數：
  CWA_API_KEY                  到 https://opendata.cwa.gov.tw 申請（免費）
  LINE_CHANNEL_ACCESS_TOKEN
  LINE_TARGET_USER_ID
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta


def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"❌ 缺少必要環境變數：{name}")
    return v


CWA_KEY = _env("CWA_API_KEY")
LINE_TOKEN = _env("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = _env("LINE_TARGET_USER_ID")

CWA_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

# (顯示名稱, dataset ID, 鄉鎮名)
LOCATIONS = [
    ("新北板橋（新埔捷運）", "F-D0047-069", "板橋區"),
    ("台北信義（市政府捷運）", "F-D0047-061", "信義區"),
]


def http_get_json(url: str, params: dict, timeout: int = 30):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_township_weather(dataset_id: str, township: str) -> dict | None:
    """取得指定鄉鎮的今日天氣（取最近 24 小時內的代表預報）"""
    data = http_get_json(
        f"{CWA_BASE}/{dataset_id}",
        {"Authorization": CWA_KEY, "LocationName": township, "format": "JSON"},
    )
    try:
        loc = data["records"]["Locations"][0]["Location"][0]
        elements = {e["ElementName"]: e for e in loc["WeatherElement"]}
    except (KeyError, IndexError):
        return None

    # 取「最早一筆未結束」的時間段做代表（即「現在或接下來最近的 3 小時」）
    now = datetime.now()
    target_end = now + timedelta(hours=24)

    def pick(element_name: str) -> str | None:
        el = elements.get(element_name)
        if not el:
            return None
        for t in el.get("Time", []):
            start = datetime.fromisoformat(t.get("StartTime", "").replace("+08:00", ""))
            if start > target_end:
                break
            val = t.get("ElementValue", [{}])[0]
            # 取第一個 value 欄位（不同元素 key 不一樣）
            for k, v in val.items():
                if v and v != "-99":
                    return v
        return None

    # 今天高低溫：用 MaxT / MinT（鄉鎮預報用「最高溫度」/「最低溫度」/「平均相對濕度」）
    today_max = pick("最高溫度") or pick("溫度")
    today_min = pick("最低溫度") or pick("溫度")
    humidity = pick("平均相對濕度") or pick("相對濕度")
    pop = pick("12小時降雨機率") or pick("3小時降雨機率") or pick("6小時降雨機率")
    weather = pick("天氣現象") or pick("天氣預報綜合描述") or "—"
    comfort = pick("舒適度指數") or pick("最大舒適度指數") or ""

    return {
        "max_temp": today_max,
        "min_temp": today_min,
        "humidity": humidity,
        "pop": pop,
        "weather": weather,
        "comfort": comfort,
    }


def fetch_typhoon_warning() -> str | None:
    """檢查目前是否有颱風警報；有的話回傳簡述，否則回 None"""
    try:
        data = http_get_json(
            f"{CWA_BASE}/W-C0033-001",
            {"Authorization": CWA_KEY, "format": "JSON"},
        )
        records = data.get("records", {}).get("record", [])
        typhoon_msgs = []
        for r in records:
            content = r.get("contents", {}).get("content", {}).get("contentText", "")
            hazards = r.get("hazardConditions", {}).get("hazards", {}).get("hazard", [])
            for h in hazards:
                phenomena = h.get("info", {}).get("phenomena", "")
                if "颱風" in phenomena or "typhoon" in phenomena.lower():
                    typhoon_msgs.append(phenomena)
            if "颱風" in content and not typhoon_msgs:
                typhoon_msgs.append(content[:50])
        if typhoon_msgs:
            return " / ".join(set(typhoon_msgs))
    except Exception as e:
        print(f"⚠️ 颱風 API 失敗，略過：{e}", flush=True)
    return None


def build_advice(w: dict) -> str:
    """根據天氣資料給穿著／攜帶建議"""
    advice = []

    try:
        pop = int(w.get("pop") or 0)
    except (ValueError, TypeError):
        pop = 0
    try:
        max_t = int(w.get("max_temp") or 0)
        min_t = int(w.get("min_temp") or 0)
    except (ValueError, TypeError):
        max_t = min_t = 0

    if pop >= 70:
        advice.append("務必帶傘")
    elif pop >= 40:
        advice.append("帶把折傘備用")

    if max_t >= 32:
        advice.append("炎熱注意防曬補水")
    elif max_t >= 28:
        advice.append("白天偏熱，穿透氣衣物")
    if min_t <= 14 and min_t > 0:
        advice.append("早晚較冷，注意保暖")
    elif min_t <= 18 and min_t > 0 and max_t - min_t >= 8:
        advice.append("早晚溫差大，加件薄外套")

    if not advice:
        advice.append("天氣舒適")
    return "、".join(advice)


def format_message() -> str:
    today = datetime.now().strftime("%-m/%-d") if os.name != "nt" else datetime.now().strftime("%#m/%#d")
    weekday = ["一", "二", "三", "四", "五", "六", "日"][datetime.now().weekday()]
    lines = [f"☀️ 今日天氣預報（{today} 週{weekday}）"]
    lines.append("════════════")

    for label, dataset_id, township in LOCATIONS:
        print(f"取 {label} 天氣 ...", flush=True)
        try:
            w = fetch_township_weather(dataset_id, township)
        except Exception as e:
            lines.append(f"📍 {label}")
            lines.append(f"⚠️ 取得失敗：{e}")
            lines.append("")
            continue

        if not w:
            lines.append(f"📍 {label}")
            lines.append("⚠️ 無資料")
            lines.append("")
            continue

        lines.append("")
        lines.append(f"📍 {label}")
        lines.append(f"  天氣：{w['weather']}")
        if w.get("min_temp") and w.get("max_temp"):
            lines.append(f"  🌡️ 溫度：{w['min_temp']}~{w['max_temp']}°C")
        elif w.get("max_temp"):
            lines.append(f"  🌡️ 溫度：{w['max_temp']}°C")
        if w.get("humidity"):
            lines.append(f"  💧 濕度：{w['humidity']}%")
        if w.get("pop"):
            lines.append(f"  ☔ 降雨機率：{w['pop']}%")
        lines.append(f"  💡 建議：{build_advice(w)}")

    # 颱風警報
    typhoon = fetch_typhoon_warning()
    lines.append("")
    lines.append("════════════")
    if typhoon:
        lines.append(f"🌀 颱風警報：{typhoon}")
        lines.append("⚠️ 請注意門窗安全")
    else:
        lines.append("🌀 颱風動態：目前無警報")

    return "\n".join(lines)


def push_line(text: str) -> None:
    print("推送到 LINE ...", flush=True)
    data = json.dumps({
        "to": LINE_TARGET,
        "messages": [{"type": "text", "text": text}],
    }).encode()
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=data,
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"    ✓ HTTP {resp.status}", flush=True)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"❌ LINE 推送失敗 HTTP {e.code}：{e.read().decode()}")


def main() -> None:
    msg = format_message()
    print("---- 訊息預覽 ----", flush=True)
    print(msg, flush=True)
    print("----------------", flush=True)
    push_line(msg)
    print("✅ 完成", flush=True)


if __name__ == "__main__":
    main()
