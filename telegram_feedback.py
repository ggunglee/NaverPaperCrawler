import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from config import (
    DATA_DIR,
    SAFE_DIR,
    ensure_app_dirs,
    load_body_keywords,
    load_env_values,
    load_exclude_keywords,
    normalize_keywords,
    save_body_keywords,
    save_exclude_keywords,
)


FEEDBACK_COMMANDS = (
    "/final",
    "/exclude",
    "/fix",
    "/important",
    "/include_keyword",
    "/include_keywords",
    "/exclude_keyword",
    "/exclude_keywords",
    "/remove_include_keyword",
    "/remove_exclude_keyword",
)
KEYWORD_COMMANDS = {
    "/include_keyword": ("include", "add"),
    "/include_keywords": ("include", "add"),
    "/exclude_keyword": ("exclude", "add"),
    "/exclude_keywords": ("exclude", "add"),
    "/remove_include_keyword": ("include", "remove"),
    "/remove_exclude_keyword": ("exclude", "remove"),
}
FEEDBACK_DB = DATA_DIR / "telegram_feedback.db"
FEEDBACK_JSON_DIR = SAFE_DIR / "feedback"


def parse_args():
    parser = argparse.ArgumentParser(description="Collect Telegram feedback commands for morning reports.")
    parser.add_argument("--chat-id", help="Only collect messages from this Telegram chat ID.")
    parser.add_argument("--json-out", type=Path, help="Optional JSON export path.")
    parser.add_argument(
        "--remind-if-empty",
        action="store_true",
        help="Send a reminder when no feedback command has been collected today.",
    )
    parser.add_argument("--reminder-text", default="이민경 피드백 내놓으라고")
    return parser.parse_args()


def telegram_credentials():
    env = load_env_values()
    token = env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id


def api_get(token, method, params=None):
    query = urllib.parse.urlencode(params or {})
    url = f"https://api.telegram.org/bot{token}/{method}"
    if query:
        url += "?" + query
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API failed: {method}")
    return data


def send_message(token, chat_id, text):
    if not chat_id or not text:
        return
    api_get(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        },
    )


def init_db(path=FEEDBACK_DB):
    ensure_app_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_messages (
                update_id INTEGER PRIMARY KEY,
                message_id INTEGER,
                chat_id TEXT,
                chat_title TEXT,
                sender TEXT,
                command TEXT,
                text TEXT NOT NULL,
                message_date TEXT,
                collected_at TEXT NOT NULL
            )
            """
        )


def latest_update_id(path=FEEDBACK_DB):
    if not path.exists():
        return None
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT MAX(update_id) FROM feedback_messages").fetchone()
    return row[0] if row and row[0] is not None else None


def has_feedback_today(path=FEEDBACK_DB, today=None):
    if not path.exists():
        return False
    today = today or datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM feedback_messages
            WHERE substr(COALESCE(message_date, collected_at), 1, 10) = ?
            LIMIT 1
            """,
            (today,),
        ).fetchone()
    return bool(row)


def parse_feedback(update, expected_chat_id=None):
    message = update.get("message") or update.get("edited_message") or {}
    text = (message.get("text") or "").strip()
    if not text.startswith(FEEDBACK_COMMANDS):
        return None
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if expected_chat_id and chat_id != str(expected_chat_id):
        return None
    command = text.split(maxsplit=1)[0].split("@", 1)[0]
    sender_info = message.get("from") or {}
    sender = sender_info.get("username") or " ".join(
        part for part in [sender_info.get("first_name"), sender_info.get("last_name")] if part
    )
    message_date = ""
    if message.get("date"):
        message_date = datetime.fromtimestamp(message["date"]).isoformat(timespec="seconds")
    return {
        "update_id": update["update_id"],
        "message_id": message.get("message_id"),
        "chat_id": chat_id,
        "chat_title": chat.get("title") or chat.get("username") or "",
        "sender": sender or "",
        "command": command,
        "text": text,
        "message_date": message_date,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }


def save_feedback(items, path=FEEDBACK_DB):
    init_db(path)
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO feedback_messages (
                update_id, message_id, chat_id, chat_title, sender, command,
                text, message_date, collected_at
            ) VALUES (
                :update_id, :message_id, :chat_id, :chat_title, :sender, :command,
                :text, :message_date, :collected_at
            )
            """,
            items,
        )
    return len(items)


def keyword_payload(text):
    command, _, payload = text.partition("\n")
    if not payload.strip():
        _, _, payload = text.partition(" ")
    return normalize_keywords(payload.replace(",", "\n").replace(";", "\n").splitlines())


def update_keyword_list(current, keywords, action):
    current = normalize_keywords(current)
    keywords = normalize_keywords(keywords)
    if action == "remove":
        remove_set = set(keywords)
        return [keyword for keyword in current if keyword not in remove_set]
    merged = current[:]
    seen = set(merged)
    for keyword in keywords:
        if keyword not in seen:
            merged.append(keyword)
            seen.add(keyword)
    return merged


def apply_keyword_commands(items):
    applied = []
    include_keywords = load_body_keywords()
    exclude_keywords = load_exclude_keywords()
    for item in items:
        command = item["command"]
        if command not in KEYWORD_COMMANDS:
            continue
        target, action = KEYWORD_COMMANDS[command]
        keywords = keyword_payload(item["text"])
        if not keywords:
            continue
        if target == "include":
            include_keywords = update_keyword_list(include_keywords, keywords, action)
            save_body_keywords(include_keywords)
        else:
            exclude_keywords = update_keyword_list(exclude_keywords, keywords, action)
            save_exclude_keywords(exclude_keywords)
        applied.append({"command": command, "target": target, "action": action, "keywords": keywords})
    return applied


def main():
    ensure_app_dirs()
    args = parse_args()
    token, configured_chat_id = telegram_credentials()
    chat_id = args.chat_id or configured_chat_id
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured.")
    offset = latest_update_id()
    params = {"timeout": 0, "allowed_updates": json.dumps(["message", "edited_message"])}
    if offset is not None:
        params["offset"] = offset + 1
    updates = api_get(token, "getUpdates", params).get("result", [])
    items = [item for item in (parse_feedback(update, chat_id) for update in updates) if item]
    save_feedback(items)
    applied_keywords = apply_keyword_commands(items)
    if updates:
        api_get(token, "getUpdates", {"offset": max(update["update_id"] for update in updates) + 1, "timeout": 0})
    if applied_keywords:
        lines = ["[아침보고 키워드 설정 반영]"]
        for item in applied_keywords:
            verb = "추가" if item["action"] == "add" else "삭제"
            target = "포함" if item["target"] == "include" else "배제"
            lines.append(f"- {target} 키워드 {verb}: {', '.join(item['keywords'])}")
        send_message(token, chat_id, "\n".join(lines))
    reminder_sent = False
    if args.remind_if_empty and not items and not has_feedback_today():
        send_message(token, chat_id, args.reminder_text)
        reminder_sent = True
    FEEDBACK_JSON_DIR.mkdir(parents=True, exist_ok=True)
    json_path = args.json_out or FEEDBACK_JSON_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_feedback.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"feedback": items, "applied_keywords": applied_keywords, "reminder_sent": reminder_sent}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"updates_seen={len(updates)} feedback_collected={len(items)} "
        f"keyword_changes={len(applied_keywords)} reminder_sent={int(reminder_sent)} json={json_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"telegram feedback failed: {exc}", file=sys.stderr)
        raise
