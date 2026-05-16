import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta
from types import SimpleNamespace

from config import LOG_PATH, ensure_app_dirs, load_body_keywords, load_env_values, load_exclude_keywords, setup_logging
from crawler import NaverPaperCrawler
from database import Database
from online_crawler import crawl_online_candidates
from report_generator import ReportDatabase, generate_report


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl and send the legal morning report.")
    parser.add_argument("--date", default="today", help="Report date YYYYMMDD or today.")
    parser.add_argument("--send-telegram", action="store_true", help="Send the generated report to Telegram.")
    parser.add_argument("--force", action="store_true", help="Re-analyze already analyzed articles in the morning scope.")
    parser.add_argument("--no-crawl", action="store_true", help="Skip crawling and only generate/send from DB.")
    parser.add_argument("--no-llm", action="store_true", help="Use deterministic extractive summaries without an LLM.")
    parser.add_argument("--llm-backend", choices=["gemini", "ollama"], default=os.environ.get("REPORT_LLM_BACKEND", "ollama"))
    parser.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", "exaone3.5:2.4b"))
    parser.add_argument("--ollama-timeout", type=int, default=int(os.environ.get("OLLAMA_TIMEOUT", "300")))
    parser.add_argument("--ollama-num-ctx", type=int, default=int(os.environ.get("OLLAMA_NUM_CTX", "4096")))
    parser.add_argument("--gemini-model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    parser.add_argument("--embedding-backend", choices=["auto", "sentence", "lexical"], default="lexical")
    return parser.parse_args()


def report_date_value(value):
    if value == "today":
        return datetime.now().strftime("%Y%m%d")
    return value


def online_window(report_date):
    base = datetime.strptime(report_date, "%Y%m%d")
    start = datetime.combine(base.date() - timedelta(days=1), time(18, 0))
    end = datetime.combine(base.date(), time(6, 0))
    return start, end


def fetch_bodies_for_scope(db, report_date, online_start, online_end, force=False):
    crawler = NaverPaperCrawler(db)
    keywords = load_body_keywords()
    excludes = load_exclude_keywords()
    rows = db.search_articles(
        date=report_date,
        keyword=None,
        search_scope="title_summary",
        article_type="지면",
        exclude_keywords=excludes,
    )
    rows.extend(
        row
        for row in db.search_articles(
            date_from=online_start.strftime("%Y%m%d"),
            date_to=online_end.strftime("%Y%m%d"),
            search_scope="title_summary",
            exclude_keywords=excludes,
        )
        if (row["article_type"] or "") != "지면"
        and row["published_at"]
        and online_start.strftime("%Y-%m-%d %H:%M:%S") <= row["published_at"] <= online_end.strftime("%Y-%m-%d %H:%M:%S")
    )
    seen = set()
    fetched = 0
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        haystack = f"{row['title'] or ''} {row['summary'] or ''} {row['body'] or ''}"
        if not any(keyword in haystack for keyword in keywords):
            continue
        if row["body"] and not force and not body_needs_refresh(row["body"]):
            continue
        should_force = force or body_needs_refresh(row["body"] or "")
        if crawler.fetch_and_store_body(row["id"], force=should_force):
            fetched += 1
    return fetched


def body_needs_refresh(body):
    noise = [
        "인공지능이 자동으로",
        "세 줄 요약",
        "전체 내용을 이해하기",
        "사회 전체",
        "정치 전체",
        "경제 전체",
        "문화 전체",
        "국제 전체",
        "많이 본 뉴스",
        "본문의 이해를 돕기",
    ]
    return any(term in (body or "") for term in noise)


def build_report(report_date, online_start, online_end, args):
    report_args = SimpleNamespace(
        date=report_date,
        date_from=None,
        date_to=None,
        morning_scope=True,
        online_from=online_start.strftime("%Y-%m-%d %H:%M:%S"),
        online_to=online_end.strftime("%Y-%m-%d %H:%M:%S"),
        include_analyzed=args.force,
        reset_analysis=args.force,
        suppress_skipped=False,
        all_articles=False,
        only_exclusive=False,
        paper_only=False,
        desk_focus=True,
        limit=None,
        output_file=True,
        no_llm=args.no_llm,
        llm_backend=args.llm_backend,
        gemini_model=args.gemini_model,
        ollama_model=args.ollama_model,
        ollama_url=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_timeout=args.ollama_timeout,
        ollama_num_ctx=args.ollama_num_ctx,
        embedding_backend=args.embedding_backend,
        similarity_threshold=0.85,
        same_day_threshold=0.85,
        exclusive_threshold=0.82,
    )
    return generate_report(ReportDatabase(), report_args)


def telegram_credentials():
    env = load_env_values()
    token = env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id


def send_telegram(text):
    token, chat_id = telegram_credentials()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = split_telegram_message(text)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"[아침보고 {index}/{len(chunks)}]\n" if len(chunks) > 1 else ""
        payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": prefix + chunk,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError("Telegram send failed.")


def split_telegram_message(text, limit=3800):
    text = text.strip()
    hold_marker = "\n[보류/제외 기사]"
    if hold_marker in text:
        report_text, hold_text = text.split(hold_marker, 1)
        chunks = []
        chunks.extend(split_telegram_message(report_text.strip(), limit=limit))
        chunks.extend(split_telegram_message(("[보류/제외 기사]" + hold_text).strip(), limit=limit))
        return chunks

    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    chunks = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = block
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def main():
    ensure_app_dirs()
    setup_logging()
    args = parse_args()
    report_date = report_date_value(args.date)
    online_start, online_end = online_window(report_date)
    db = Database()

    if not args.no_crawl:
        paper = NaverPaperCrawler(db).crawl_date(report_date)
        online = crawl_online_candidates(db, online_start, online_end, exclude_keywords=load_exclude_keywords())
        fetched = fetch_bodies_for_scope(db, report_date, online_start, online_end, force=args.force)
        print(
            f"paper_total={paper['total']} paper_inserted={paper['inserted']} "
            f"online_total={online['total']} online_inserted={online['inserted']} body_fetched={fetched}"
        )

    report = build_report(report_date, online_start, online_end, args)
    if args.send_telegram:
        send_telegram(report)
        print("telegram_sent=1")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"morning report failed: {exc}", file=sys.stderr)
        print(f"log: {LOG_PATH}", file=sys.stderr)
        raise
