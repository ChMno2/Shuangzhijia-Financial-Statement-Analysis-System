"""
雙之家 LINE 週報推送腳本
由 GitHub Actions 排程執行（見 .github/workflows/line-report.yml）

流程：
  1. 登入 Render 後端拿 JWT
  2. 取近期銷售摘要（/api/summary）
  3. 觸發 Claude 生成 AI 週報（/api/report/generate）
  4. 推送到 LINE（LINE_TARGET_USER_ID 指定的個人 / 群組）

所需環境變數（GitHub Secrets）：
  BACKEND_API_BASE           例：https://shuangzhijia-financial-statement.onrender.com
  BACKEND_USERNAME           admin
  BACKEND_PASSWORD           後台登入密碼
  LINE_CHANNEL_ACCESS_TOKEN  Messaging API 的 token
  LINE_TARGET_USER_ID        要推送給誰（U 開頭的字串）
"""
import json
import os
import sys
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
              body: dict | None = None, timeout: int = 180):
    headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode() or "null"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def login() -> str:
    print(f"[1/4] 登入 {API_BASE}（Render 冷啟動可能要 30~60 秒）...", flush=True)
    status, body = http_json(
        f"{API_BASE}/api/auth/login",
        method="POST",
        body={"username": USERNAME, "password": PASSWORD},
    )
    if status != 200 or not isinstance(body, dict) or "access_token" not in body:
        raise SystemExit(f"❌ 登入失敗 HTTP {status}：{body}")
    print("    ✓ 登入成功", flush=True)
    return body["access_token"]


def get_summary(token: str) -> dict:
    print("[2/4] 取得銷售摘要 /api/summary ...", flush=True)
    status, body = http_json(
        f"{API_BASE}/api/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200 or not isinstance(body, dict):
        raise SystemExit(f"❌ 取得 summary 失敗 HTTP {status}：{body}")
    return body


def generate_report(token: str) -> str:
    print("[3/4] 觸發 AI 週報生成（可能要 30~90 秒）...", flush=True)
    status, body = http_json(
        f"{API_BASE}/api/report/generate",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        body={},
        timeout=240,
    )
    if status != 200 or not isinstance(body, dict) or "content" not in body:
        raise SystemExit(f"❌ 生成週報失敗 HTTP {status}：{body}")
    print(f"    ✓ 週報生成完成（{len(body['content'])} 字）", flush=True)
    return body["content"]


def format_headline(summary: dict) -> str:
    def money(v):
        try:
            return f"NT$ {int(float(v)):,}"
        except (TypeError, ValueError):
            return f"NT$ {v}"

    growth = summary.get("week_growth", 0) or 0
    growth_emoji = "📈" if growth >= 0 else "📉"

    return (
        f"📊 雙之家本週速報\n"
        f"資料日期：{summary.get('data_latest_date', '—')}\n"
        f"────────────\n"
        f"💰 本週營收：{money(summary.get('this_week_revenue', 0))}\n"
        f"{growth_emoji} 較上週：{growth:+.1f}%\n"
        f"📅 本月累計：{money(summary.get('this_month_revenue', 0))}\n"
        f"🛒 近30天交易：{summary.get('total_transactions', 0):,} 筆\n"
        f"🏷️ 商品種類：{summary.get('unique_products', 0)} 種"
    )


def push_line(messages: list[str]) -> None:
    print(f"[4/4] 推送到 LINE（{len(messages)} 則）...", flush=True)
    # LINE 一次最多 5 則訊息、每則最多 5000 字元
    for i in range(0, len(messages), 5):
        batch = messages[i:i + 5]
        status, body = http_json(
            "https://api.line.me/v2/bot/message/push",
            method="POST",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            body={
                "to": LINE_TARGET,
                "messages": [{"type": "text", "text": m} for m in batch],
            },
            timeout=30,
        )
        if status != 200:
            raise SystemExit(f"❌ LINE 推送失敗 HTTP {status}：{body}")
    print("    ✓ 推送完成", flush=True)


def split_for_line(text: str, limit: int = 4500) -> list[str]:
    """LINE 單則 5000 字上限，保險起見切 4500"""
    if len(text) <= limit:
        return [text]
    chunks, buf = [], []
    cur_len = 0
    for line in text.split("\n"):
        if cur_len + len(line) + 1 > limit:
            chunks.append("\n".join(buf))
            buf, cur_len = [line], len(line) + 1
        else:
            buf.append(line)
            cur_len += len(line) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def main() -> None:
    token = login()
    summary = get_summary(token)
    report = generate_report(token)

    headline = format_headline(summary)
    body_text = f"📝 AI 週報分析\n────────────\n{report}"

    messages = [headline] + split_for_line(body_text)
    push_line(messages)
    print("✅ 完成", flush=True)


if __name__ == "__main__":
    main()
