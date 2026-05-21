import argparse
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, SAFE_DIR


RAW_HEADERS = [
    "date",
    "published_at",
    "source",
    "article_type",
    "paper_section",
    "title",
    "url",
    "summary",
    "body",
    "crawl_source",
    "body_fetch_status",
    "normalized_event_key",
    "main_actor",
    "legal_relevance",
    "locality",
    "selection_status",
    "exclusion_reason",
    "duplicate_of",
    "selected_for_report",
]

REPORT_HEADERS = [
    "date",
    "title",
    "newspaper",
    "selection_status",
    "duplicate_of",
    "exclusion_reason",
    "llm_summary",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Mirror report data to Google Sheets.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--spreadsheet-id", default=os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID"))
    parser.add_argument("--skip-if-unconfigured", action="store_true")
    return parser.parse_args()


def configured(spreadsheet_id):
    return bool(spreadsheet_id and os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))


def main():
    args = parse_args()
    args.date = resolve_date(args.date)
    if not configured(args.spreadsheet_id):
        message = "google_sheets_mirror_skipped=unconfigured"
        if args.skip_if_unconfigured:
            print(message)
            return 0
        raise SystemExit(message)

    report_items = load_report_items(args.date)
    selected_urls = {item["url"] for item in report_items if item.get("url")}
    rows = load_article_rows(args.db_path, args.date, selected_urls)
    report_rows = report_rows_from_report(args.date, report_items) or report_rows_from_db(rows)

    sheet = open_sheet(args.spreadsheet_id)
    replace_worksheet(sheet, "Raw_Articles", RAW_HEADERS, [row_to_raw_values(item) for item in rows])
    replace_worksheet(sheet, "Morning_Report", REPORT_HEADERS, report_rows)
    print(f"google_sheets_mirror_completed raw_rows={len(rows)} report_rows={len(report_rows)}")
    return 0


def resolve_date(value):
    if value == "today":
        return datetime.now().strftime("%Y%m%d")
    return value


def open_sheet(spreadsheet_id):
    import gspread

    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    client = gspread.service_account_from_dict(info)
    return client.open_by_key(spreadsheet_id)


def replace_worksheet(sheet, title, headers, rows):
    import gspread

    try:
        ws = sheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=title, rows=max(100, len(rows) + 1), cols=len(headers))
    ws.clear()
    values = [headers] + rows
    if values:
        ws.update(values, value_input_option="RAW")
    ws.freeze(rows=1)


def report_path_for_date(date):
    report_path = SAFE_DIR / "reports" / f"{date}_morning_report.md"
    if not report_path.exists():
        report_path = SAFE_DIR / "reports" / f"{date}_initial_morning_report.md"
    return report_path


def report_urls(date):
    return {item["url"] for item in load_report_items(date) if item.get("url")}


def load_report_items(date):
    report_path = report_path_for_date(date)
    if not report_path.exists():
        return []
    text = report_path.read_text(encoding="utf-8", errors="ignore")
    items = []
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("\u203b"):
            if current:
                items.append(current)
            title, source = split_report_heading(line[1:])
            current = {"title": title, "source": source, "summary": "", "url": ""}
        elif current and line.startswith("-"):
            current["summary"] = line[1:].strip()
        elif current and re.match(r"https?://", line):
            current["url"] = line.split()[0]
    if current:
        items.append(current)
    return items


def split_report_heading(value):
    if "/" not in value:
        return value.strip(), ""
    title, source = value.rsplit("/", 1)
    return title.strip(), source.strip()


def report_rows_from_report(date, items):
    return [
        [
            date,
            item.get("title", ""),
            item.get("source", ""),
            "selected",
            "",
            "",
            item.get("summary", ""),
        ]
        for item in items
    ]


def report_rows_from_db(rows):
    return [
        [
            item["date"],
            item["title"],
            item["source"],
            item["selection_status"],
            item["duplicate_of"],
            item["exclusion_reason"],
            item["summary"],
        ]
        for item in rows
        if item["selected_for_report"] == "TRUE" or item["selection_status"] != "raw"
    ]


def load_article_rows(db_path, date, selected_urls):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                a.*,
                aa.status AS analysis_status,
                aa.matched_article_id,
                aa.report_summary_md,
                aa.raw_response,
                aa.error
            FROM articles a
            LEFT JOIN article_analysis aa ON aa.article_id = a.id
            WHERE a.date = ?
            ORDER BY COALESCE(a.published_at, a.created_at, ''), a.id
            """,
            (date,),
        ).fetchall()
    finally:
        conn.close()
    return [article_to_mirror_row(row, selected_urls) for row in rows]


def article_to_mirror_row(row, selected_urls):
    raw_response = parse_json(row["raw_response"])
    selected = row["url"] in selected_urls
    status = row["analysis_status"] or "raw"
    if selected:
        status = "selected"
    return {
        "date": row["date"] or "",
        "published_at": row["published_at"] or "",
        "source": row["newspaper"] or "",
        "article_type": row["article_type"] or "",
        "paper_section": row["paper_section"] or "",
        "title": row["title"] or "",
        "url": row["url"] or "",
        "summary": row["report_summary_md"] or row["summary"] or "",
        "body": row["body"] or "",
        "crawl_source": row["oid"] or "",
        "body_fetch_status": "fetched" if row["body"] else "missing",
        "normalized_event_key": raw_response.get("duplicate_key", ""),
        "main_actor": raw_response.get("main_actor", ""),
        "legal_relevance": raw_response.get("legal_relevance", ""),
        "locality": raw_response.get("locality", ""),
        "selection_status": status,
        "exclusion_reason": "" if selected else exclusion_reason(status, row["error"]),
        "duplicate_of": str(row["matched_article_id"] or ""),
        "selected_for_report": "TRUE" if selected else "FALSE",
    }


def row_to_raw_values(item):
    return [trim_cell(item[key]) for key in RAW_HEADERS]


def trim_cell(value, limit=45000):
    text = str(value or "")
    return text[:limit]


def parse_json(value):
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def exclusion_reason(status, error):
    if error:
        return error
    if status in {"raw", "selected"}:
        return ""
    return status


if __name__ == "__main__":
    raise SystemExit(main())
