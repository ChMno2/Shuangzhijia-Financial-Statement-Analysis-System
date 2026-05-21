"""
雙之家 LINE 每日速報腳本（不呼叫 LLM）
排程：每日 16:00 台灣時間 推送

內容：
  - 當日營收、淨利、毛利率
  - 當日 TOP 3 商品 + 銷售金額
  - 近 30 天累計營收 / 交易筆數

所需環境變數（GitHub Secrets，同週報腳本可重用）：
  BACKEND_API_BASE / BACKEND_USERNAME / BACKEND_PASSWORD
  LINE_CHANNEL_ACCESS_TOKEN / LINE_TARGET_USER_ID
"""
import json
import os
import urllib.error
import urllib.request


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

    lines.append(
        f"📅 近30天累計：{money(d.get('last_30_days_revenue', 0))}"
        f"（{d.get('last_30_days_transactions', 0):,} 筆）"
    )

    top = d.get("top_products") or []
    if top:
        lines.append("")
        lines.append("🏆 今日 TOP 3 商品")
        for i, p in enumerate(top, 1):
            lines.append(f"  {i}. {p.get('name', '')} — {money(p.get('revenue', 0))}")

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
