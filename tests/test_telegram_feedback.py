import telegram_feedback as tf
from config import telegram_recipient_ids


def test_keywords_command_is_parsed_as_feedback():
    item = tf.parse_feedback(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "text": "/keywords",
                "chat": {"id": 123},
                "from": {"username": "tester"},
            },
        },
        expected_chat_id="123",
    )

    assert item["command"] == "/keywords"
    assert tf.keyword_status_commands([item]) == [item]


def test_feedback_parser_accepts_any_configured_chat_id():
    update = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "text": "/final\n내용",
            "chat": {"id": -100},
        },
    }

    assert tf.parse_feedback(update, expected_chat_id=["123", "-100"])["chat_id"] == "-100"
    assert tf.parse_feedback(update, expected_chat_id=["123"]) is None


def test_group_chat_is_sent_first_and_can_be_group_only():
    env = {
        "TELEGRAM_CHAT_ID": "private",
        "TELEGRAM_CHAT_IDS": "private,backup",
        "TELEGRAM_GROUP_CHAT_ID": "group",
    }

    assert telegram_recipient_ids(env) == ["group", "private", "backup"]
    env["TELEGRAM_GROUP_ONLY"] = "true"
    assert telegram_recipient_ids(env) == ["group"]


def test_keyword_status_message_lists_include_and_empty_exclude(monkeypatch):
    monkeypatch.setattr(tf, "load_body_keywords", lambda: ["특검", "서울 검찰"])
    monkeypatch.setattr(tf, "load_exclude_keywords", lambda: [])

    message = tf.keyword_status_message()

    assert "포함 키워드" in message
    assert "- 특검" in message
    assert "- 서울 검찰" in message
    assert "- (없음)" in message
