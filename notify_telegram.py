import argparse
import json
import os
import urllib.parse
import urllib.request

from config import load_env_values, telegram_recipient_ids


def parse_args():
    parser = argparse.ArgumentParser(description="Send an operational Telegram notification.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--chat-id")
    return parser.parse_args()


def telegram_credentials():
    env = load_env_values()
    token = env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    return token, telegram_recipient_ids(env)


def send_message(token, chat_id, text):
    if not token or not chat_id:
        print("telegram_notification_skipped=unconfigured")
        return 0
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chat_ids = chat_id if isinstance(chat_id, (list, tuple, set)) else [chat_id]
    for recipient in chat_ids:
        payload = urllib.parse.urlencode(
            {
                "chat_id": recipient,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError("Telegram notification failed.")
    print(f"telegram_notification_sent={len(chat_ids)}")
    return 0


def main():
    args = parse_args()
    token, configured_chat_id = telegram_credentials()
    chat_id = [args.chat_id] if args.chat_id else configured_chat_id
    text = f"{args.title}\n\n{args.message}"
    return send_message(token, chat_id, text)


if __name__ == "__main__":
    raise SystemExit(main())
