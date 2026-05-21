import argparse
import json
import os
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta
from types import SimpleNamespace

from config import LOG_PATH, SAFE_DIR, ensure_app_dirs, load_body_keywords, load_env_values, load_exclude_keywords, setup_logging, telegram_recipient_ids
from crawler import NaverPaperCrawler
from database import Database
from online_crawler import crawl_online_candidates
from report_generator import ReportDatabase, generate_report


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl and send the legal morning report.")
    parser.add_argument("--date", default="today", help="Report date YYYYMMDD or today.")
    parser.add_argument(
        "--mode",
        choices=["initial", "update"],
        default="initial",
        help="initial sends the 06:00 report; update checks online articles from 06:00 to 06:50.",
    )
    parser.add_argument("--send-telegram", action="store_true", help="Send the generated report to Telegram.")
    parser.add_argument("--send-feedback-guide", action="store_true", help="Send feedback instructions after the report.")
    parser.add_argument("--force", action="store_true", help="Re-analyze already analyzed articles in the morning scope.")
    parser.add_argument("--no-crawl", action="store_true", help="Skip crawling and only generate/send from DB.")
    parser.add_argument("--no-llm", action="store_true", help="Compatibility flag; reports are always deterministic.")
    parser.add_argument("--embedding-backend", choices=["auto", "sentence", "lexical"], default="lexical")
    return parser.parse_args()


def report_date_value(value):
    if value == "today":
        return datetime.now().strftime("%Y%m%d")
    return value


def online_window(report_date):
    base = datetime.strptime(report_date, "%Y%m%d")
    start = datetime.combine(base.date() - timedelta(days=1), time(18, 0))
    # Some wire articles are published a few seconds after 06:00 while still
    # belonging to the morning batch.
    end = datetime.combine(base.date(), time(6, 10))
    return start, end


def update_online_window(report_date):
    base = datetime.strptime(report_date, "%Y%m%d")
    start = datetime.combine(base.date(), time(6, 0))
    end = datetime.combine(base.date(), time(6, 50))
    return start, end


def fetch_bodies_for_scope(db, report_date, online_start, online_end, force=False, include_paper=True):
    crawler = NaverPaperCrawler(db)
    keywords = load_body_keywords()
    excludes = load_exclude_keywords()
    rows = []
    if include_paper:
        rows.extend(
            db.search_articles(
                date=report_date,
                keyword=None,
                search_scope="title_summary",
                article_type="지면",
                exclude_keywords=excludes,
            )
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
    attempted = 0
    fetched = 0
    failed = 0
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
        attempted += 1
        if crawler.fetch_and_store_body(row["id"], force=should_force):
            fetched += 1
        else:
            failed += 1
    return {"candidates": len(seen), "attempted": attempted, "fetched": fetched, "failed": failed}


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
        online_only=args.mode == "update",
        desk_focus=True,
        limit=None,
        output_file=True,
        no_llm=True,
        embedding_backend=args.embedding_backend,
        similarity_threshold=0.85,
        same_day_threshold=0.85,
        exclusive_threshold=0.82,
    )
    return generate_report(ReportDatabase(), report_args)


def archive_mode_report(report_date, mode):
    report_dir = SAFE_DIR / "reports"
    source = report_dir / f"{report_date}_morning_report.md"
    if not source.exists():
        return None
    target = report_dir / f"{report_date}_{mode}_morning_report.md"
    shutil.copyfile(source, target)
    print(f"archived: {target}")
    return target


def feedback_guide_message():
    return """[피드백 보내는 법]

아침보고를 고친 뒤 아래 형식으로 이 방에 보내주면 낮 12시쯤 프로그램이 모아서 다음 룰 개선 자료로 쓰게 만들 예정.

/final
최종 완성본 전체

/exclude
제외해야 할 기사 제목 또는 제외 기준

/fix
원문: 어색한 문장
수정: 원하는 보고체 문장

/important
앞으로 꼭 넣어야 할 기사 유형

/apply_feedback
오후 3시 반영 확인 메시지에 대한 답변

/include_keyword
추가할 포함 키워드. 여러 개는 줄바꿈 또는 쉼표로 구분.

/exclude_keyword
추가할 배제 키워드. 여러 개는 줄바꿈 또는 쉼표로 구분.

/remove_include_keyword
삭제할 포함 키워드.

/remove_exclude_keyword
삭제할 배제 키워드.

/keywords
현재 포함/배제 키워드 확인. /show_keywords도 가능."""


def report_has_selected_items(report):
    return any(line.startswith("※") for line in (report or "").splitlines())


def body_fetch_warning(stats):
    if not stats or not stats.get("failed"):
        return ""
    return "\n".join(
        [
            "[아침보고 오류 알림]",
            "",
            "- 단계: 본문 크롤링",
            "- 상태: 일부 실패",
            f"- 후보 기사: {stats.get('candidates', 0)}건",
            f"- 본문 수집 시도: {stats.get('attempted', 0)}건",
            f"- 성공: {stats.get('fetched', 0)}건",
            f"- 실패: {stats.get('failed', 0)}건",
            "- 영향: 일부 기사는 제목/요약 중심으로 판단됐을 수 있음",
        ]
    )


def telegram_credentials():
    env = load_env_values()
    token = env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    return token, telegram_recipient_ids(env)


def send_telegram(text):
    token, chat_ids = telegram_credentials()
    if not token or not chat_ids:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = split_telegram_message(text)
    for chat_id in chat_ids:
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
                raise RuntimeError(f"Telegram send failed for chat_id={chat_id}.")


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
    if args.mode == "update":
        online_start, online_end = update_online_window(report_date)
    else:
        online_start, online_end = online_window(report_date)
    db = Database()

    if not args.no_crawl:
        if args.mode == "update":
            paper = {"total": 0, "inserted": 0}
        else:
            paper = NaverPaperCrawler(db).crawl_date(report_date)
        online = crawl_online_candidates(db, online_start, online_end, exclude_keywords=load_exclude_keywords())
        body_stats = fetch_bodies_for_scope(
            db,
            report_date,
            online_start,
            online_end,
            force=args.force,
            include_paper=args.mode != "update",
        )
        print(
            f"mode={args.mode} "
            f"paper_total={paper['total']} paper_inserted={paper['inserted']} "
            f"online_total={online['total']} online_inserted={online['inserted']} "
            f"lawtimes_total={online.get('lawtimes', {}).get('total', 0)} "
            f"lawtimes_inserted={online.get('lawtimes', {}).get('inserted', 0)} "
            f"body_candidates={body_stats['candidates']} body_attempted={body_stats['attempted']} "
            f"body_fetched={body_stats['fetched']} body_failed={body_stats['failed']}"
        )

    report = build_report(report_date, online_start, online_end, args)
    archive_mode_report(report_date, args.mode)
    if args.send_telegram:
        telegram_report = report
        if args.mode == "update" and report_has_selected_items(report):
            telegram_report = "[추가 보고]\n\n" + report
        should_send_report = args.mode != "update" or report_has_selected_items(report)
        if should_send_report:
            send_telegram(telegram_report)
        else:
            print("telegram_report_skipped=no_update_items")
        warning = body_fetch_warning(body_stats if not args.no_crawl else {})
        if warning:
            send_telegram(warning)
        if args.send_feedback_guide:
            send_telegram(feedback_guide_message())
        print("telegram_sent=1")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"morning report failed: {exc}", file=sys.stderr)
        print(f"log: {LOG_PATH}", file=sys.stderr)
        raise
