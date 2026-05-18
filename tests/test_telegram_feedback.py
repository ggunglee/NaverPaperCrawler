import telegram_feedback as tf


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


def test_keyword_status_message_lists_include_and_empty_exclude(monkeypatch):
    monkeypatch.setattr(tf, "load_body_keywords", lambda: ["특검", "서울 검찰"])
    monkeypatch.setattr(tf, "load_exclude_keywords", lambda: [])

    message = tf.keyword_status_message()

    assert "포함 키워드" in message
    assert "- 특검" in message
    assert "- 서울 검찰" in message
    assert "- (없음)" in message
