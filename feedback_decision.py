import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from config import SAFE_DIR, ensure_app_dirs
from telegram_feedback import send_message, telegram_credentials


STATE_PATH = SAFE_DIR / "feedback_review_state.json"
RULES_PATH = SAFE_DIR / "feedback_rules.json"


STOP_TERMS = {
    "단독",
    "속보",
    "종합",
    "영상",
    "오늘",
    "내일",
    "관련",
    "기자",
    "뉴스",
    "연합뉴스",
    "뉴시스",
    "뉴스1",
    "조선",
    "경향",
    "국민",
    "동아",
    "문화",
    "서울",
    "중앙",
    "한국",
    "헤럴드경제",
    "채널A",
    "TV조선",
}


LEGAL_HINT_TERMS = {
    "국가배상",
    "구상권",
    "정보공개",
    "정보공개청구",
    "불송치",
    "기록반환",
    "기소유예",
    "무혐의",
    "대법",
    "대법원",
    "파기환송",
    "법원",
    "검찰",
    "법무부",
    "특검",
    "공수처",
    "판결",
    "소송",
    "손해배상",
    "구속",
    "압수수색",
    "기소",
    "불기소",
    "약식기소",
    "재판",
    "헌재",
    "헌법재판소",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Send and apply feedback-review decisions.")
    parser.add_argument("--mode", choices=["propose", "apply"], required=True)
    parser.add_argument("--feedback-json", type=Path, required=True)
    parser.add_argument("--review-json", type=Path, required=True)
    parser.add_argument("--report-date", default="today")
    return parser.parse_args()


def report_date_value(value):
    if value == "today":
        return datetime.now().strftime("%Y%m%d")
    return value


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def state_for_date(state, report_date):
    dates = state.setdefault("dates", {})
    return dates.setdefault(report_date, {})


def suggestion_label(suggestion):
    mapping = {
        "force_include_candidate": "포함 강화 후보",
        "force_exclude_or_demote_candidate": "배제/강등 후보",
        "summary_style_candidate": "요약 방식 후보",
    }
    return mapping.get(suggestion.get("type"), suggestion.get("type", "후보"))


def build_proposal_message(review):
    suggestions = review.get("suggested_rule_changes") or []
    lines = [
        "[피드백 반영 확인]",
        "",
        "오늘 최종본과 초안을 비교했습니다.",
        "",
        f"- 초안 기사: {review.get('draft_item_count', 0)}건",
        f"- 최종본 기사: {review.get('final_item_count', 0)}건",
        f"- 사용자가 추가한 기사: {len(review.get('added_items') or [])}건",
        f"- 사용자가 제외한 기사: {len(review.get('removed_items') or [])}건",
        f"- 요약 수정: {len(review.get('changed_items') or [])}건",
        "",
        "반영 후보:",
    ]
    for index, suggestion in enumerate(suggestions[:12], start=1):
        headline = suggestion.get("headline") or "(제목 없음)"
        lines.append(f"{index}. {suggestion_label(suggestion)}: {headline}")
    if len(suggestions) > 12:
        lines.append(f"... 외 {len(suggestions) - 12}건")
    lines.extend(
        [
            "",
            "반영하려면 오늘 자정 전까지 아래 형식으로 답해주세요.",
            "",
            "/apply_feedback",
            "1, 2 반영",
            "3은 보류",
            "추가 지시가 있으면 자유롭게 작성",
        ]
    )
    return "\n".join(lines)


def send_proposal(report_date, review):
    if not review.get("suggested_rule_changes"):
        print("feedback_proposal_skipped=no_suggestions")
        return 0
    state = read_json(STATE_PATH, {"dates": {}})
    current = state_for_date(state, report_date)
    if current.get("proposal_sent_at"):
        print("feedback_proposal_skipped=already_sent")
        return 0
    token, chat_id = telegram_credentials()
    send_message(token, chat_id, build_proposal_message(review))
    current["proposal_sent_at"] = datetime.now().isoformat(timespec="seconds")
    current["review_summary"] = {
        "draft_item_count": review.get("draft_item_count", 0),
        "final_item_count": review.get("final_item_count", 0),
        "added": len(review.get("added_items") or []),
        "removed": len(review.get("removed_items") or []),
        "changed": len(review.get("changed_items") or []),
    }
    current["suggested_rule_changes"] = review.get("suggested_rule_changes", [])
    write_json(STATE_PATH, state)
    print(f"feedback_proposal_sent=1 suggestions={len(current['suggested_rule_changes'])}")
    return 0


def latest_apply_feedback(feedback_payload):
    feedback = feedback_payload.get("feedback") or []
    applies = [item for item in feedback if item.get("command") == "/apply_feedback"]
    return applies[-1] if applies else None


def headline_terms(headline):
    text = re.sub(r"https?://\S+", " ", headline or "")
    chunks = re.findall(r"[가-힣A-Za-z0-9]{2,}", text)
    terms = []
    for chunk in chunks:
        if chunk in STOP_TERMS:
            continue
        if chunk in LEGAL_HINT_TERMS or any(hint in chunk for hint in LEGAL_HINT_TERMS):
            terms.append(chunk)
    return terms[:8]


def terms_from_suggestions(suggestions):
    include_terms = []
    exclude_terms = []
    for suggestion in suggestions:
        terms = headline_terms(suggestion.get("headline", ""))
        if suggestion.get("type") == "force_include_candidate":
            include_terms.extend(terms)
        elif suggestion.get("type") == "force_exclude_or_demote_candidate":
            exclude_terms.extend(terms)
    return dedupe(include_terms), dedupe(exclude_terms)


def dedupe(values):
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def send_apply_ack(rule):
    lines = [
        "[피드백 적용 내역]",
        "",
        "오늘 피드백 반영 지시를 저장했습니다.",
    ]
    if rule.get("include_terms"):
        lines.append(f"- 포함 강화: {', '.join(rule['include_terms'])}")
    if rule.get("exclude_terms"):
        lines.append(f"- 배제/강등 참고: {', '.join(rule['exclude_terms'])}")
    lines.extend(
        [
            f"- 저장된 반영 후보: {len(rule.get('suggestions') or [])}건",
            "- 다음 보고부터 승인된 피드백 규칙을 판단 힌트로 사용합니다.",
        ]
    )
    token, chat_id = telegram_credentials()
    send_message(token, chat_id, "\n".join(lines))


def apply_decision(report_date, feedback_payload):
    apply_item = latest_apply_feedback(feedback_payload)
    if not apply_item:
        print("feedback_apply_skipped=no_apply_feedback")
        return 0
    state = read_json(STATE_PATH, {"dates": {}})
    current = state_for_date(state, report_date)
    suggestions = current.get("suggested_rule_changes") or []
    if not suggestions:
        print("feedback_apply_skipped=no_pending_suggestions")
        return 0
    include_terms, exclude_terms = terms_from_suggestions(suggestions)
    rules = read_json(RULES_PATH, {"rules": []})
    rule = {
        "report_date": report_date,
        "status": "approved",
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "response_text": apply_item.get("text", ""),
        "include_terms": include_terms,
        "exclude_terms": exclude_terms,
        "suggestions": suggestions,
    }
    rules.setdefault("rules", []).append(rule)
    write_json(RULES_PATH, rules)
    current["applied_at"] = rule["approved_at"]
    current["apply_update_id"] = apply_item.get("update_id")
    write_json(STATE_PATH, state)
    send_apply_ack(rule)
    print(
        f"feedback_apply_saved=1 suggestions={len(suggestions)} "
        f"include_terms={len(include_terms)} exclude_terms={len(exclude_terms)}"
    )
    return 0


def main():
    ensure_app_dirs()
    args = parse_args()
    report_date = report_date_value(args.report_date)
    feedback_payload = read_json(args.feedback_json, {})
    review = read_json(args.review_json, {})
    if args.mode == "propose":
        return send_proposal(report_date, review)
    return apply_decision(report_date, feedback_payload)


if __name__ == "__main__":
    raise SystemExit(main())
