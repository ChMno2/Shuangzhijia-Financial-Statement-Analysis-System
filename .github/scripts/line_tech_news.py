"""
科技新聞 LINE 推播腳本（獨立 bot，與雙之家財報 agent 分離）
排程：每日 10:00 台灣時間

來源：Google News RSS（免費、不需 API key、支援關鍵字搜尋）
  https://news.google.com/rss/search?q=<關鍵字>&hl=zh-TW&gl=TW&ceid=TW:zh-Hant

所需環境變數（GitHub Secrets）：
  TECH_LINE_CHANNEL_ACCESS_TOKEN   科技新聞 bot 的 token
  TECH_LINE_TARGET_USER_ID         推送目標（個人 / 群組 ID）

關鍵字、推送則數可直接在下方 KEYWORDS / MAX_ITEMS 修改。
"""
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# ─────────────────────────────────────────
# 設定區（要改就改這裡）
# ─────────────────────────────────────────
KEYWORDS: list[str] = [
    "Anthropic Claude",        # 加 Anthropic 避開「Claude」單字噪音
    "Google Gemini AI",        # 加 AI 避開「Gemini」星座噪音
    "生成式AI",
    "AI agent",
    "LLM 量化",                # 模型量化
    "Vision Transformer",      # ViT
]

# 一次最多推送幾則新聞
MAX_ITEMS = 8

# 每個關鍵字最多取幾則（避免單一關鍵字洗版）
PER_KEYWORD_MAX = 2

# 只收最近多少小時內發布的新聞
RECENT_HOURS = 30

# ─────────────────────────────────────────


def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"❌ 缺少必要環境變數：{name}")
    return v


LINE_TOKEN = _env("TECH_LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = _env("TECH_LINE_TARGET_USER_ID")


def fetch_google_news_rss(keyword: str) -> list[dict]:
    """從 Google News RSS 抓某關鍵字的新聞清單"""
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({
            "q": keyword,
            "hl": "zh-TW",
            "gl": "TW",
            "ceid": "TW:zh-Hant",
        })
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_bytes = resp.read()
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"⚠️ 取 {keyword} RSS 失敗：{e}", flush=True)
        return []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"⚠️ {keyword} RSS 解析失敗：{e}", flush=True)
        return []

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_HOURS)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        description = item.findtext("description") or ""

        # 解析發布時間
        pub_dt = None
        if pub_date_raw:
            for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
                try:
                    pub_dt = datetime.strptime(pub_date_raw, fmt)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

        # 只收近 N 小時內的
        if pub_dt and pub_dt < cutoff:
            continue

        # 取媒體來源（<source url="...">CNBC</source>）
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""

        items.append({
            "title": html.unescape(title),
            "link": link,
            "source": source,
            "pub_dt": pub_dt,
            "keyword": keyword,
        })

    return items


def collect_all_news() -> list[dict]:
    """跑過所有關鍵字 → 去重 → 排序 → 取前 MAX_ITEMS 則"""
    seen_titles: set[str] = set()
    bucket: list[dict] = []

    for kw in KEYWORDS:
        print(f"取 [{kw}] 新聞 ...", flush=True)
        items = fetch_google_news_rss(kw)
        # 每個關鍵字限制 PER_KEYWORD_MAX 則
        count = 0
        for item in items:
            # 用標題前 30 字去重（同一則新聞被多家媒體轉載時，Google News 會列多筆）
            sig = item["title"][:30]
            if sig in seen_titles:
                continue
            seen_titles.add(sig)
            bucket.append(item)
            count += 1
            if count >= PER_KEYWORD_MAX:
                break
        print(f"   → 入選 {count} 則", flush=True)

    # 依發布時間排序（最新優先），無時間者排最後
    bucket.sort(
        key=lambda x: x["pub_dt"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return bucket[:MAX_ITEMS]


def format_message(items: list[dict]) -> str:
    today = datetime.now().strftime("%-m/%-d") if os.name != "nt" else datetime.now().strftime("%#m/%#d")
    weekday = ["一", "二", "三", "四", "五", "六", "日"][datetime.now().weekday()]
    lines = [f"📰 今日科技新聞（{today} 週{weekday}）"]
    lines.append("════════════")

    if not items:
        lines.append("⚠️ 今日無符合關鍵字的新聞")
        lines.append("（追蹤關鍵字：" + "、".join(KEYWORDS[:3]) + " ...）")
        return "\n".join(lines)

    for i, it in enumerate(items, 1):
        # 簡化標題（移除來源後綴 "- 媒體名"）
        title = re.sub(r"\s+-\s+[^-]+$", "", it["title"]).strip()
        source = it["source"] or "—"
        lines.append("")
        lines.append(f"{i}. {title}")
        lines.append(f"   📌 [{it['keyword']}] · {source}")
        if it["link"]:
            lines.append(f"   🔗 {it['link']}")

    return "\n".join(lines)


def push_line(text: str) -> None:
    print(f"推送到 LINE（{len(text)} 字）...", flush=True)
    data = json.dumps({
        "to": LINE_TARGET,
        "messages": [{"type": "text", "text": text[:4900]}],
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
    items = collect_all_news()
    msg = format_message(items)
    print("---- 訊息預覽 ----", flush=True)
    print(msg, flush=True)
    print("----------------", flush=True)
    push_line(msg)
    print("✅ 完成", flush=True)


if __name__ == "__main__":
    main()
