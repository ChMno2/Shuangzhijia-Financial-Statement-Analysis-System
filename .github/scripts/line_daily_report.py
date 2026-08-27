"""
雙之家 LINE 每日速報腳本（不呼叫 LLM）
排程：每日台灣時間 15:00 推送

GitHub Actions 的 schedule 觸發本身不保證準時（實測延遲從幾十分鐘到 2.5 小時都有），
所以 workflow 故意提早很多觸發，實際送達時間由本腳本的 wait_until_target() 精確控制：
不管 GHA 幾點真的開始跑這個 job，都會等到台灣時間 15:00 整才真正抓資料、推送。
手動用 workflow_dispatch 觸發時會略過等待，立即執行（方便測試）。

內容：
  - 當日營收、淨利、毛利率
  - 當日 TOP 3 商品 + 銷售金額
  - 本月累計營收 / 交易筆數（當月 1 號 ~ 今天），並拆分新埔（一二三）/ 光復（四五六日）
  - 明日預計準備商品：依過去 8 週同星期資料，相對近 16 週平常水準熱賣倍數最高的 2 個分類

所需環境變數（GitHub Secrets，同週報腳本可重用）：
  BACKEND_API_BASE / BACKEND_USERNAME / BACKEND_PASSWORD
  LINE_CHANNEL_ACCESS_TOKEN / LINE_TARGET_USER_ID
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TARGET_HOUR = 15
TARGET_MINUTE = 0
TAIPEI = ZoneInfo("Asia/Taipei")


def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"❌ 缺少必要環境變數：{name}")
    return v


API_BASE = _env("BACKEND_API_BASE").rstrip("/")
USERNAME = _env("BACKEND_USERNAME")
PASSWORD = _env("BACKEND_PASSWORD")
LINE_TOKEN = _env("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = _env("LINE_TARGET_USER_ID")


def http_json(url: str, method: str = "GET", headers: dict | None = None,
              body: dict | None = None, timeout: int = 120):
    headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait_until_target() -> None:
    """精確等到台灣時間 TARGET_HOUR:TARGET_MINUTE 才返回。

    排程觸發（schedule）才等待；手動觸發（workflow_dispatch）直接跳過，方便測試。
    若 GHA 排程延遲導致開始執行時已經超過目標時間，就不再等待，直接執行（盡快送達）。
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        print("[等待] 非排程觸發，略過等待，立即執行", flush=True)
        return

    now = datetime.now(TAIPEI)
    target = now.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
    if now >= target:
        print(f"[等待] 現在已是 {now:%H:%M:%S}，晚於目標 {TARGET_HOUR:02d}:{TARGET_MINUTE:02d}，直接執行", flush=True)
        return

    wait_seconds = (target - now).total_seconds()
    print(
        f"[等待] 現在 {now:%H:%M:%S}，等到台灣時間 {TARGET_HOUR:02d}:{TARGET_MINUTE:02d} 才推送"
        f"（約 {wait_seconds / 60:.0f} 分鐘）...",
        flush=True,
    )
    time.sleep(wait_seconds)


def login() -> str:
    print(f"[1/3] 登入 {API_BASE} ...", flush=True)
    status, body = http_json(
        f"{API_BASE}/api/auth/login",
        method="POST",
        body={"username": USERNAME, "password": PASSWORD},
    )
    if status != 200 or not isinstance(body, dict) or "access_token" not in body:
        raise SystemExit(f"❌ 登入失敗 HTTP {status}：{body}")
    return body["access_token"]


def fetch_daily(token: str) -> dict:
    print("[2/3] 取得當日速報資料 ...", flush=True)
    status, body = http_json(
        f"{API_BASE}/api/line/daily",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200 or not isinstance(body, dict):
        raise SystemExit(f"❌ 取得速報失敗 HTTP {status}：{body}")
    return body


def money(v) -> str:
    try:
        return f"NT$ {int(float(v)):,}"
    except (TypeError, ValueError):
        return "NT$ —"


def format_message(d: dict) -> str:
    lines = [f"📊 雙之家每日速報"]
    lines.append(f"資料日期：{d.get('date', '—')}")
    lines.append("────────────")

    if not d.get("has_data"):
        lines.append("⚠️ 今日尚未有任何銷售紀錄")
        lines.append("（請確認媽媽是否已在 Google Sheet 登錄當日資料）")
        return "\n".join(lines)

    lines.append(f"💰 今日營收：{money(d.get('revenue', 0))}")

    profit = d.get("profit")
    margin = d.get("margin")
    if profit is not None:
        margin_str = f"（毛利率 {margin}%）" if margin is not None else ""
        lines.append(f"💵 今日淨利：{money(profit)} {margin_str}".rstrip())
    else:
        lines.append("💵 今日淨利：— (缺成本資料)")

    # 後端更新後回傳 month_to_date_*；若後端尚未重啟仍回傳 last_30_days_*，
    # 此時優雅退回顯示近 30 天，避免出現誤導的 NT$ 0
    if "month_to_date_revenue" in d:
        cum_label = "本月累計"
        cum_rev = d.get("month_to_date_revenue", 0)
        cum_tx = d.get("month_to_date_transactions", 0)
    else:
        cum_label = "近30天累計"
        cum_rev = d.get("last_30_days_revenue", 0)
        cum_tx = d.get("last_30_days_transactions", 0)
    lines.append(f"📅 {cum_label}：{money(cum_rev)}（{cum_tx:,} 筆）")

    if "guangfu_month_to_date_revenue" in d:
        lines.append(
            f"　├ 光復累計：{money(d.get('guangfu_month_to_date_revenue', 0))}"
            f"（{d.get('guangfu_month_to_date_transactions', 0):,} 筆）"
        )
        lines.append(
            f"　└ 新埔累計：{money(d.get('xinpu_month_to_date_revenue', 0))}"
            f"（{d.get('xinpu_month_to_date_transactions', 0):,} 筆）"
        )

    top = d.get("top_products") or []
    if top:
        lines.append("")
        lines.append("🏆 今日 TOP 3 商品")
        for i, p in enumerate(top, 1):
            lines.append(f"  {i}. {p.get('name', '')} — {money(p.get('revenue', 0))}")

    recommended = d.get("recommended_categories") or []
    if recommended:
        lines.append("")
        lines.append(f"🎒 明日（{d.get('tomorrow_date', '—')}）預計準備")
        for i, c in enumerate(recommended, 1):
            lift = c.get("lift")
            lift_str = f"（較平常熱銷 {lift} 倍）" if lift is not None else ""
            lines.append(f"  {i}. {c.get('category', '')} {lift_str}".rstrip())
        lines.append("　（依過去 8 週同星期資料分析）")

    return "\n".join(lines)


def push_line(text: str) -> None:
    print(f"[3/3] 推送到 LINE ...", flush=True)
    status, body = http_json(
        "https://api.line.me/v2/bot/message/push",
        method="POST",
        headers={"Authorization": f"Bearer {LINE_TOKEN}"},
        body={"to": LINE_TARGET, "messages": [{"type": "text", "text": text}]},
        timeout=30,
    )
    if status != 200:
        raise SystemExit(f"❌ LINE 推送失敗 HTTP {status}：{body}")
    print("    ✓ 推送完成", flush=True)


def main() -> None:
    wait_until_target()

    token = login()
    daily = fetch_daily(token)

    # 沒出攤 / 當日沒銷售資料 → 不推播
    # （媽媽沒填當日 Excel 或當日營收為 0 都跳過，避免推「今日營收 NT$ 0」這種無意義訊息）
    if not daily.get("has_data") or float(daily.get("revenue") or 0) == 0:
        print(f"✋ 今日 {daily.get('date')} 無銷售資料（has_data={daily.get('has_data')}, "
              f"revenue={daily.get('revenue')}），跳過推送", flush=True)
        return

    msg = format_message(daily)
    print("---- 訊息預覽 ----", flush=True)
    print(msg, flush=True)
    print("----------------", flush=True)
    push_line(msg)
    print("✅ 完成", flush=True)


if __name__ == "__main__":
    main()
