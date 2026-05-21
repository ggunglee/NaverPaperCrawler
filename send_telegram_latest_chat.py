import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime

from config import load_env_values


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
            return chat_id
    raise RuntimeError("No Telegram updates with chat id found.")


def send_message(token, chat_id, text):
    api_call(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        },
    )


def main():
    parser = argparse.ArgumentParser(description="Send a test message to the latest Telegram chat that contacted the bot.")
    parser.add_argument("--text", default=None, help="Message text to send.")
    args = parser.parse_args()
    token = telegram_token()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured.")
    chat_id = latest_chat_id(token)
    text = args.text or f"[아침보고 테스트] 최신 텔레그램 방 ID로 보낸 테스트 메시지입니다. {datetime.now().isoformat(timespec='seconds')}"
    send_message(token, chat_id, text)
    print("telegram_latest_chat_sent=1")


if __name__ == "__main__":
    main()
