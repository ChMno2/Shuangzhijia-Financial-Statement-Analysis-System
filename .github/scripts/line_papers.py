"""
AI 論文每日精選 LINE 推播腳本（獨立 bot）
排程：每日 08:00 台灣時間

流程：
  1. 從 Semantic Scholar API 抓 2024~2026 年論文，
     涵蓋 AI agent / 模型量化 / Vision Transformer / 模型加速器 等主題
  2. 過濾頂刊頂會（CVPR、NeurIPS、ICML、ICLR、IEEE、arXiv 等）
  3. 依 influential citation 排序，取前 POOL_SIZE
  4. 以日期為 seed 隨機抽 TOP_N 篇（每天不同）
  5. 用 Gemini API 為每篇生成「兩段話」中文摘要（聚焦貢獻；免費）
  6. 推送到 LINE

所需環境變數（GitHub Secrets）：
  PAPERS_LINE_CHANNEL_ACCESS_TOKEN
  PAPERS_LINE_TARGET_USER_ID
  GEMINI_API_KEY                   到 https://aistudio.google.com/app/apikey 申請（免費）
  GEMINI_MODEL                     （選填）預設 gemini-2.0-flash
"""
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# ─────────────────────────────────────────
# 設定區
# ─────────────────────────────────────────
TOPIC_QUERIES = [
    "LLM agent autonomous",          # AI agent / 大模型代理
    "LLM model quantization",        # 模型量化
    "Vision Transformer ViT",        # ViT
    "deep learning accelerator NPU", # DLA / NPU
]

# 目標頂刊頂會（白名單；包含其一即收）
VENUE_WHITELIST = [
    "CVPR", "ICCV", "ECCV",          # 視覺三大
    "NeurIPS", "ICML", "ICLR",       # ML 三大
    "AAAI", "IJCAI",                 # AI 兩大
    "ACL", "EMNLP", "NAACL",         # NLP 三大
    "IEEE", "TPAMI", "PAMI",         # IEEE 系列
    "arXiv", "arxiv",                # 預印本
    "JMLR",
]

YEAR_RANGE = "2024-2026"   # Semantic Scholar 接受的格式
TOP_N = 5                   # 每天推幾篇
POOL_SIZE = 25              # 從前 N 篇隨機選（製造多樣性）
SEARCH_LIMIT_PER_TOPIC = 30 # 每主題撈幾篇


# ─────────────────────────────────────────


def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"❌ 缺少必要環境變數：{name}")
    return v


LINE_TOKEN = _env("PAPERS_LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = _env("PAPERS_LINE_TARGET_USER_ID")
GEMINI_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def http_get_json(url: str, headers: dict | None = None, timeout: int = 30,
                  max_retries: int = 4) -> dict | None:
    """GET JSON，遇到 429（rate limit）會指數退避重試"""
    headers = dict(headers or {})
    headers.setdefault("User-Agent", "shuangzhijia-papers-bot/1.0")
    delay = 5.0
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                print(f"⏳ 429 限速，等 {delay:.0f} 秒後重試 ({attempt + 1}/{max_retries})", flush=True)
                time.sleep(delay)
                delay *= 2  # 5, 10, 20 秒
                continue
            print(f"⚠️ GET 失敗 {url[:80]}：HTTP {e.code}", flush=True)
            return None
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"⚠️ GET 失敗 {url[:80]}：{e}", flush=True)
            return None
    return None


def search_semantic_scholar(query: str) -> list[dict]:
    """從 Semantic Scholar Graph API 搜尋論文"""
    fields = (
        "title,abstract,authors,year,venue,citationCount,"
        "influentialCitationCount,externalIds,openAccessPdf"
    )
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search?"
        + urllib.parse.urlencode({
            "query": query,
            "year": YEAR_RANGE,
            "limit": SEARCH_LIMIT_PER_TOPIC,
            "fields": fields,
        })
    )
    data = http_get_json(url)
    if not data:
        return []
    return data.get("data", []) or []


def in_whitelist(venue: str) -> bool:
    """檢查 venue 是否包含白名單中任一字串（不分大小寫）"""
    if not venue:
        return False
    v = venue.lower()
    return any(w.lower() in v for w in VENUE_WHITELIST)


# arXiv 篩選：只收 AI/ML/CV/NLP 相關類別（其他類別容易吃到無關論文）
AI_CATEGORIES = {"cs.AI", "cs.LG", "cs.CV", "cs.CL", "cs.NE", "cs.IR", "stat.ML"}

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def detect_venue_from_comment(comment: str) -> str:
    """從 arXiv 論文的 comment 欄解析「accepted to XXX」這類關鍵字"""
    if not comment:
        return "arXiv"
    cl = comment.lower()
    for v in VENUE_WHITELIST:
        if v.lower() == "arxiv":
            continue
        if v.lower() in cl:
            return v
    return "arXiv"


def search_arxiv(topic: str, max_results: int = 30) -> list[dict]:
    """
    從 arXiv API 搜尋論文（無 rate limit、所有頂會論文都會放這）
    回傳已過濾的論文清單（normalized format）
    """
    # arXiv search syntax: '+' 在 search_query 內代表 AND
    plus_joined = "+AND+".join(f"all:{urllib.parse.quote(w)}" for w in topic.split())
    url = (
        f"http://export.arxiv.org/api/query"
        f"?search_query={plus_joined}"
        f"&start=0&max_results={max_results}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )

    req = urllib.request.Request(url, headers={"User-Agent": "shuangzhijia-papers-bot/1.0"})

    # arXiv 偶爾會 429（共用 IP 流量大）；指數退避重試
    xml_bytes = None
    delay = 5.0
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                xml_bytes = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                print(f"⏳ arXiv 429，等 {delay:.0f} 秒後重試 ({attempt + 1}/3)", flush=True)
                time.sleep(delay)
                delay *= 2  # 5, 10
                continue
            print(f"⚠️ arXiv HTTP 失敗：{e}", flush=True)
            return []
        except Exception as e:
            print(f"⚠️ arXiv 連線失敗：{e}", flush=True)
            return []

    if xml_bytes is None:
        return []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"⚠️ arXiv XML 解析失敗：{e}", flush=True)
        return []

    papers = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        title = (entry.findtext(f"{ATOM_NS}title") or "").strip().replace("\n", " ").replace("  ", " ")
        abstract = (entry.findtext(f"{ATOM_NS}summary") or "").strip().replace("\n", " ").replace("  ", " ")
        published = (entry.findtext(f"{ATOM_NS}published") or "").strip()
        id_str = (entry.findtext(f"{ATOM_NS}id") or "").strip()

        # 解析 arxiv ID（去掉版本號 v1/v2）
        arxiv_id = id_str.split("/abs/")[-1] if "/abs/" in id_str else id_str.rsplit("/", 1)[-1]
        arxiv_id_clean = re.sub(r"v\d+$", "", arxiv_id)

        # 發布時間
        published_dt = None
        if published:
            try:
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                published_dt = published_dt.replace(tzinfo=None)
            except ValueError:
                pass

        year = published_dt.year if published_dt else None

        # 年份過濾
        if year is None or year < 2024:
            continue

        # 類別過濾：必須包含至少一個 AI/ML 類別
        cats = [c.attrib.get("term") for c in entry.findall(f"{ATOM_NS}category")]
        if not any(c in AI_CATEGORIES for c in cats):
            continue

        # 從 comment 欄抓 venue（許多論文會註明 accepted to ...）
        comment_el = entry.find(f"{ARXIV_NS}comment")
        comment = comment_el.text if comment_el is not None and comment_el.text else ""
        venue = detect_venue_from_comment(comment)

        papers.append({
            "title": title,
            "abstract": abstract,
            "year": year,
            "venue": venue,
            "_venue": venue,
            "url": f"https://arxiv.org/abs/{arxiv_id_clean}",
            "published_dt": published_dt,
            "arxiv_id": arxiv_id_clean,
            "categories": cats,
            "_source": "arxiv",
        })

    return papers


def collect_papers() -> list[dict]:
    """跑所有主題 → 過濾 → 去重 → 排序（用 arXiv 為主要來源）"""
    seen: set[str] = set()
    bucket: list[dict] = []

    for idx, topic in enumerate(TOPIC_QUERIES):
        if idx > 0:
            time.sleep(5.0)  # arXiv 官方建議「至少 3 秒一次」，保守設 5 秒
        print(f"搜尋 [{topic}] (arXiv) ...", flush=True)
        papers = search_arxiv(topic, max_results=SEARCH_LIMIT_PER_TOPIC)

        kept = 0
        for p in papers:
            # 用 arxiv_id 去重（不同主題可能撈到同一篇）
            pid = p.get("arxiv_id") or p.get("title")
            if pid in seen:
                continue
            seen.add(pid)

            # 必須有摘要
            if not p.get("abstract"):
                continue

            p["_topic"] = topic
            bucket.append(p)
            kept += 1
        print(f"   → 入選 {kept} 篇", flush=True)

    # 排序：發布時間遞減（最新優先）
    bucket.sort(
        key=lambda p: p.get("published_dt") or datetime.min,
        reverse=True,
    )
    return bucket


def gemini_summarize(title: str, abstract: str) -> str:
    """請 Gemini 用兩段繁中說明這篇論文的核心貢獻（免費 API）"""
    prompt = (
        f"請用繁體中文，分成兩段說明這篇論文的核心貢獻。\n\n"
        f"標題：{title}\n\n"
        f"摘要：{abstract[:1800]}\n\n"
        f"撰寫規則：\n"
        f"・第一段：論文解決的問題 + 提出的方法（1~2 句）\n"
        f"・第二段：與既有方法相比最有特色的貢獻 / 突破 / 影響（1~2 句）\n"
        f"・全文純文字，禁用 markdown 符號（# * _ > ` 等），LINE 無法渲染\n"
        f"・兩段加總不超過 220 字\n"
        f"・若摘要為英文，請翻譯成中文，不可直接照貼英文"
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    )
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 500,
            "temperature": 0.3,
        },
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        # Gemini 回應結構：candidates[0].content.parts[0].text
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # 雙重保險：清掉 markdown 殘留
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"(?m)^\s*[#>]+\s*", "", text)
        text = re.sub(r"(?m)^\s*[-*]\s+", "・", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        return text
    except Exception as e:
        return f"（摘要失敗：{e}）原始摘要：{abstract[:200]}"


def get_paper_url(p: dict) -> str:
    """取論文連結（normalized 格式 → 直接拿 url）"""
    if p.get("url"):
        return p["url"]
    if p.get("arxiv_id"):
        return f"https://arxiv.org/abs/{p['arxiv_id']}"
    return ""


def format_message(papers: list[dict]) -> str:
    today = datetime.now().strftime("%-m/%-d") if os.name != "nt" else datetime.now().strftime("%#m/%#d")
    weekday = ["一", "二", "三", "四", "五", "六", "日"][datetime.now().weekday()]
    lines = [f"📚 AI 論文每日精選（{today} 週{weekday}）"]
    lines.append("════════════════")

    if not papers:
        lines.append("⚠️ 今日無符合條件的新論文")
        return "\n".join(lines)

    for i, p in enumerate(papers, 1):
        title = (p.get("title") or "").strip()
        venue = p.get("_venue", "arXiv")
        year = p.get("year", "—")
        url = get_paper_url(p)
        summary = p.get("_summary", "")

        # 發布日期顯示 YYYY-MM-DD
        pub_dt = p.get("published_dt")
        date_str = pub_dt.strftime("%Y-%m-%d") if pub_dt else str(year)

        lines.append("")
        lines.append(f"━━ {i}. {title}")
        lines.append(f"📌 {venue} · {date_str}")
        lines.append(f"🔗 {url}")
        lines.append("")
        lines.append(summary)

    return "\n".join(lines)


def push_line(text: str) -> None:
    # LINE 單訊息 5000 字上限，必要時分段
    chunks = []
    if len(text) <= 4800:
        chunks = [text]
    else:
        # 用論文分隔線「━━」切
        parts = text.split("\n━━ ")
        cur = parts[0]
        for part in parts[1:]:
            block = "\n━━ " + part
            if len(cur) + len(block) > 4800:
                chunks.append(cur)
                cur = block.lstrip("\n")
            else:
                cur += block
        if cur:
            chunks.append(cur)

    print(f"推送到 LINE（{len(chunks)} 則 / 共 {len(text)} 字）...", flush=True)
    for chunk in chunks:
        data = json.dumps({
            "to": LINE_TARGET,
            "messages": [{"type": "text", "text": chunk}],
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
    candidates = collect_papers()
    print(f"全部候選：{len(candidates)} 篇", flush=True)
    if not candidates:
        push_line(format_message([]))
        return

    # 取前 POOL_SIZE，用日期當 seed 隨機選 TOP_N（每天不同但同一天執行多次結果一致）
    pool = candidates[:POOL_SIZE]
    seed = int(datetime.now().strftime("%Y%m%d"))
    random.seed(seed)
    selected = random.sample(pool, min(TOP_N, len(pool)))
    print(f"今日選出：{len(selected)} 篇", flush=True)

    # 逐篇 Gemini 摘要
    for i, p in enumerate(selected, 1):
        print(f"  [{i}/{len(selected)}] 摘要 {p.get('title', '')[:50]}...", flush=True)
        p["_summary"] = gemini_summarize(p["title"], p["abstract"])

    msg = format_message(selected)
    print("---- 訊息預覽 ----", flush=True)
    print(msg, flush=True)
    print("----------------", flush=True)
    push_line(msg)
    print("✅ 完成", flush=True)


if __name__ == "__main__":
    main()
