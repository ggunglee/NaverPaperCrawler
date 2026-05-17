import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from config import SAFE_DIR


REPORT_MARK = "\u203b"


def parse_args():
    parser = argparse.ArgumentParser(description="Compare collected Telegram feedback with generated reports.")
    parser.add_argument("--feedback-json", type=Path, required=True)
    parser.add_argument("--report-date", default="today")
    parser.add_argument("--reports-dir", type=Path, default=SAFE_DIR / "reports")
    parser.add_argument("--json-out", type=Path, required=True)
    return parser.parse_args()


def report_date_value(value):
    if value == "today":
        return datetime.now().strftime("%Y%m%d")
    return value


def read_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def final_feedback_items(feedback_payload):
    feedback_items = feedback_payload.get("feedback", [])
    finals = [item for item in feedback_items if item.get("command") == "/final"]
    if not finals:
        return []
    return extract_report_items(finals[-1].get("text", ""))


def load_draft_report(reports_dir, report_date):
    candidates = [
        reports_dir / f"{report_date}_initial_morning_report.md",
        reports_dir / f"{report_date}_morning_report.md",
    ]
    for path in candidates:
        if path.exists():
            return path, extract_report_items(path.read_text(encoding="utf-8"))
    return None, []


def extract_report_items(text):
    text = re.sub(r"^/final\s*", "", text.strip())
    items = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        headline = lines[0]
        if not headline.startswith(REPORT_MARK):
            continue
        url = next((line for line in lines if line.startswith("http")), "")
        summary = " ".join(line[1:].strip() for line in lines[1:] if line.startswith("-"))
        items.append({"headline": headline, "summary": summary, "url": url})
    return items


def compare_items(draft_items, final_items):
    draft_by_url = {item["url"]: item for item in draft_items if item.get("url")}
    final_by_url = {item["url"]: item for item in final_items if item.get("url")}
    added = [final_by_url[url] for url in sorted(set(final_by_url) - set(draft_by_url))]
    removed = [draft_by_url[url] for url in sorted(set(draft_by_url) - set(final_by_url))]
    retained = [final_by_url[url] for url in sorted(set(final_by_url) & set(draft_by_url))]
    changed = []
    for item in retained:
        draft = draft_by_url[item["url"]]
        if normalize(draft.get("summary")) != normalize(item.get("summary")):
            changed.append({"draft": draft, "final": item})
    return added, removed, changed


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def review_hints(added, removed, changed):
    hints = []
    if added:
        hints.append(
            {
                "type": "candidate_recall",
                "message": "Final feedback added report items that were not in the draft. Review inclusion keywords and desk-focus filters.",
                "count": len(added),
            }
        )
    if removed:
        hints.append(
            {
                "type": "candidate_precision",
                "message": "Final feedback removed draft items. Review exclusion, demotion, or duplicate-priority rules.",
                "count": len(removed),
            }
        )
    if changed:
        hints.append(
            {
                "type": "summary_style",
                "message": "Final feedback rewrote retained item summaries. Review extractive summary and tone rules.",
                "count": len(changed),
            }
        )
    return hints


def main():
    args = parse_args()
    report_date = report_date_value(args.report_date)
    feedback_payload = read_json(args.feedback_json)
    draft_path, draft_items = load_draft_report(args.reports_dir, report_date)
    final_items = final_feedback_items(feedback_payload)
    added, removed, changed = compare_items(draft_items, final_items)
    output = {
        "report_date": report_date,
        "draft_report_path": str(draft_path) if draft_path else None,
        "feedback_count": len(feedback_payload.get("feedback", [])),
        "final_feedback_count": sum(1 for item in feedback_payload.get("feedback", []) if item.get("command") == "/final"),
        "draft_item_count": len(draft_items),
        "final_item_count": len(final_items),
        "added_items": added,
        "removed_items": removed,
        "changed_items": changed,
        "review_hints": review_hints(added, removed, changed),
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"feedback_review final_items={len(final_items)} draft_items={len(draft_items)} "
        f"added={len(added)} removed={len(removed)} changed={len(changed)} json={args.json_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
