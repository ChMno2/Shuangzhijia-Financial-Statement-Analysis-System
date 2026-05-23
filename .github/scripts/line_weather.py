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
from datetime import datetime, timedelta, timezone

# 強制以台北時區判斷「今天/明天」，避免 GHA runner 用 UTC 時跨日錯算
# （凌晨 4 點 Taiwan 在 UTC 還是「昨天」，+1 天會變成今天而非明天）
TAIPEI_TZ = timezone(timedelta(hours=8))


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)


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


def _parse_cwa_time(s: str) -> datetime | None:
    """CWA 時間字串 e.g. '2026-05-20T18:00:00+08:00' → naive datetime（去掉時區）"""
    if not s:
        return None
    try:
        # Python 3.11+ 支援 +08:00 ISO 格式；保險起見手動切掉
        return datetime.fromisoformat(s.replace("+08:00", ""))
    except ValueError:
        return None


def fetch_township_weather(dataset_id: str, township: str, day_offset: int = 1) -> dict | None:
    """
    取得指定鄉鎮的單日天氣
    day_offset: 0=今天、1=明天、2=後天 ...
    """
    data = http_get_json(
        f"{CWA_BASE}/{dataset_id}",
        {"Authorization": CWA_KEY, "LocationName": township, "format": "JSON"},
    )
    try:
        loc = data["records"]["Locations"][0]["Location"][0]
        elements = {e["ElementName"]: e for e in loc["WeatherElement"]}
    except (KeyError, IndexError):
        return None

    # 目標日 = 今天（台北時區）+ day_offset，整個日曆日（00:00 ~ 24:00）
    target_day = (now_taipei() + timedelta(days=day_offset)).date()
    day_start = datetime.combine(target_day, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    def in_target_day(t: datetime) -> bool:
        return day_start <= t < day_end

    def pick_in_day(times: list, value_key: str) -> str | None:
        """從 Time 序列中取「目標日」期間第一筆有效值"""
        for t in times:
            ts = _parse_cwa_time(t.get("DataTime") or t.get("StartTime"))
            if ts is None or not in_target_day(ts):
                continue
            val = (t.get("ElementValue") or [{}])[0].get(value_key)
            if val not in (None, "", "-99"):
                return val
        return None

    def collect_in_day(times: list, value_key: str) -> list[float]:
        """收集「目標日」這個區間內的所有數值（給溫度抓最高最低用）"""
        out = []
        for t in times:
            ts = _parse_cwa_time(t.get("DataTime") or t.get("StartTime"))
            if ts is None or not in_target_day(ts):
                continue
            val = (t.get("ElementValue") or [{}])[0].get(value_key)
            try:
                out.append(float(val))
            except (TypeError, ValueError):
                continue
        return out

    # 最高/最低溫（從多筆「溫度」中過濾出目標日）
    temps = collect_in_day(elements.get("溫度", {}).get("Time", []), "Temperature")
    max_temp = str(int(max(temps))) if temps else None
    min_temp = str(int(min(temps))) if temps else None

    # 取目標日的代表值
    humidity = pick_in_day(elements.get("相對濕度", {}).get("Time", []), "RelativeHumidity")
    pop = pick_in_day(
        elements.get("3小時降雨機率", {}).get("Time", []),
        "ProbabilityOfPrecipitation",
    )
    weather = pick_in_day(elements.get("天氣現象", {}).get("Time", []), "Weather") or "—"

    return {
        "max_temp": max_temp,
        "min_temp": min_temp,
        "humidity": humidity,
        "pop": pop,
        "weather": weather,
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
    # 預設預報「明天」（day_offset=1）；可由環境變數 WEATHER_DAY_OFFSET 覆寫
    day_offset = int(os.environ.get("WEATHER_DAY_OFFSET", "1"))
    target = now_taipei() + timedelta(days=day_offset)
    label_map = {0: "今日", 1: "明日", 2: "後天"}
    day_label = label_map.get(day_offset, f"+{day_offset}日")
    date_str = target.strftime("%-m/%-d") if os.name != "nt" else target.strftime("%#m/%#d")
    weekday = ["一", "二", "三", "四", "五", "六", "日"][target.weekday()]
    lines = [f"☀️ {day_label}天氣預報（{date_str} 週{weekday}）"]
    lines.append("════════════")

    for label, dataset_id, township in LOCATIONS:
        print(f"取 {label} 天氣（{day_label}）...", flush=True)
        try:
            w = fetch_township_weather(dataset_id, township, day_offset=day_offset)
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
