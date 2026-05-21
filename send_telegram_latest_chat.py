import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from config import SAFE_DIR, load_env_values

LATEST_CHAT_PATH = SAFE_DIR / "telegram_latest_chat_id.txt"


def telegram_token():
    env = load_env_values()
    return env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")


def api_call(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    if params:
        data = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API failed: {method}")
    return payload


def update_chat_id(update):
    message = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
        or {}
    )
    chat = message.get("chat") or {}
    return chat.get("id")


def latest_chat_id(token):
    updates = api_call(token, "getUpdates", {"timeout": 0}).get("result", [])
    for update in reversed(updates):
        chat_id = update_chat_id(update)
        if chat_id:
            LATEST_CHAT_PATH.parent.mkdir(parents=True, exist_ok=True)
            LATEST_CHAT_PATH.write_text(str(chat_id), encoding="utf-8")
            return chat_id
    if LATEST_CHAT_PATH.exists():
        stored = LATEST_CHAT_PATH.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    raise RuntimeError("No Telegram updates with chat id found.")


def send_message(token, chat_id, text):
    chunks = split_telegram_message(text)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"[아침보고 {index}/{len(chunks)}]\n" if len(chunks) > 1 else ""
        api_call(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": prefix + chunk,
                "disable_web_page_preview": "true",
            },
        )


def split_telegram_message(text, limit=3800):
    text = text.strip()
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    chunks = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = block
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def report_path(report_date):
    reports_dir = SAFE_DIR / "reports"
    if report_date == "today":
        report_date = datetime.now().strftime("%Y%m%d")
    candidates = [
        reports_dir / f"{report_date}_initial_morning_report.md",
        reports_dir / f"{report_date}_morning_report.md",
    ]
    for path in candidates:
        if path.exists():
            return path
    matches = sorted(reports_dir.glob(f"{report_date}*_morning_report.md"))
    if matches:
        return matches[-1]
    raise RuntimeError(f"No morning report found for {report_date}.")


def main():
    parser = argparse.ArgumentParser(description="Send a test message to the latest Telegram chat that contacted the bot.")
    parser.add_argument("--text", default=None, help="Message text to send.")
    parser.add_argument("--latest-report", action="store_true", help="Send the latest morning report for the date.")
    parser.add_argument("--report-date", default="today", help="Report date YYYYMMDD or today.")
    args = parser.parse_args()
    token = telegram_token()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured.")
    chat_id = latest_chat_id(token)
    if args.latest_report:
        path = report_path(args.report_date)
        text = path.read_text(encoding="utf-8")
    else:
        text = args.text or f"[아침보고 테스트] 최신 텔레그램 방 ID로 보낸 테스트 메시지입니다. {datetime.now().isoformat(timespec='seconds')}"
    send_message(token, chat_id, text)
    print("telegram_latest_chat_sent=1")


if __name__ == "__main__":
    main()
