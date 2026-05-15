import argparse
import logging
import sys
import traceback
from datetime import datetime

from config import LOG_PATH, ensure_app_dirs, load_body_keywords, save_body_keywords, setup_logging
from crawler import NaverPaperCrawler
from database import Database
from online_crawler import crawl_online_candidates
from rss_crawler import RssCrawler
from scheduler import install_scheduled_tasks, uninstall_scheduled_tasks


def parse_args():
    parser = argparse.ArgumentParser(description="Naver newspaper article crawler")
    parser.add_argument("--crawl-today-with-prompt", action="store_true", help="Ask before crawling today's list.")
    parser.add_argument("--crawl-today", action="store_true", help="Crawl today's list.")
    parser.add_argument("--crawl-date", help="Crawl list for YYYYMMDD.")
    parser.add_argument("--crawl-rss", action="store_true", help="Crawl configured RSS feeds.")
    parser.add_argument("--crawl-online", action="store_true", help="Crawl RSS feeds and monitored Naver API keywords.")
    parser.add_argument("--run-morning-report", action="store_true", help="Run morning report crawl/generate/send flow.")
    parser.add_argument("--install-scheduler", action="store_true", help="Register Windows Task Scheduler jobs.")
    parser.add_argument("--uninstall-scheduler", action="store_true", help="Remove Windows Task Scheduler jobs.")
    parser.add_argument("--no-gui", action="store_true", help="Run without main GUI.")
    return parser.parse_args()


def today_string():
    return datetime.now().strftime("%Y%m%d")


def crawl_list_only(date: str):
    result = NaverPaperCrawler().crawl_date(date)
    print(
        f"date={date} total={result['total']} inserted={result['inserted']} "
        f"pages={result.get('pages', 0)} body_fetched={result.get('body_fetched', 0)}"
    )
    if result["failures"]:
        print("failures:")
        for failure in result["failures"]:
            print(f"- {failure}")
    return 0 if not result["failures"] else 1


def crawl_rss_only():
    result = RssCrawler().crawl_all()
    print(f"rss total={result['total']} inserted={result['inserted']} errors={len(result['errors'])}")
    for error in result["errors"]:
        print(f"- {error}")
    return 0 if result["total"] > 0 else 1


def crawl_online_only():
    result = crawl_online_candidates()
    print(
        f"online total={result['total']} inserted={result['inserted']} "
        f"rss_total={result['rss']['total']} api_total={result['api']['total']} "
        f"errors={len(result['errors'])}"
    )
    for error in result["errors"]:
        print(f"- {error}")
    return 0 if result["total"] > 0 or not result["errors"] else 1


def crawl_today_with_prompt():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

    from gui import KeywordBodyDialog

    app = QApplication(sys.argv)
    answer = QMessageBox.question(
        None,
        "네이버 신문게재 기사 수집",
        "기사를 모을까요?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    if answer != QMessageBox.Yes:
        return 0
    try:
        date = today_string()
        crawler = NaverPaperCrawler()
        progress = QProgressDialog("목록 수집 중입니다. 잠시만 기다려 주세요.", "", 0, 0)
        progress.setWindowTitle("처리 중")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.show()
        QApplication.processEvents()
        result = crawler.crawl_date(date)
        progress.close()

        summary = (
            "목록 수집 완료\n"
            f"확인: {result['total']}건\n"
            f"신규 저장: {result['inserted']}건\n"
            f"수집 페이지: {result.get('pages', 0)}쪽"
        )
        dialog = KeywordBodyDialog(summary, load_body_keywords())
        dialog.exec()
        if dialog.action in {"collect", "save_skip"}:
            keywords = save_body_keywords(dialog.keywords())
            if dialog.action == "save_skip":
                QMessageBox.information(None, "수집 완료", f"{summary}\n\n키워드를 저장했습니다.")
            elif dialog.action == "collect" and keywords:
                rows = Database().find_articles_by_keywords(date, keywords)
                if rows:
                    body_progress = QProgressDialog("키워드 기사 본문 수집 중입니다.", "", 0, len(rows))
                    body_progress.setWindowTitle("처리 중")
                    body_progress.setCancelButton(None)
                    body_progress.setWindowModality(Qt.ApplicationModal)
                    body_progress.show()
                    QApplication.processEvents()
                    for index, row in enumerate(rows, start=1):
                        crawler.fetch_and_store_body(row["id"], force=False)
                        body_progress.setValue(index)
                        body_progress.setLabelText(f"키워드 기사 본문 수집 중입니다. ({index}/{len(rows)})")
                        QApplication.processEvents()
                    body_progress.close()
                    QMessageBox.information(None, "수집 완료", f"{summary}\n\n본문 수집: {len(rows)}건")
                else:
                    QMessageBox.information(None, "수집 완료", f"{summary}\n\n키워드 매칭 기사가 없습니다.")
            else:
                QMessageBox.information(None, "수집 완료", f"{summary}\n\n본문 수집에 사용할 키워드가 없습니다.")
        else:
            QMessageBox.information(None, "수집 완료", summary)
        return 0 if not result["failures"] else 1
    except Exception:
        logging.exception("Prompt crawl failed")
        QMessageBox.critical(None, "오류", f"수집 중 오류가 발생했습니다.\n\n상세 로그: {LOG_PATH}")
        return 1
    finally:
        app.quit()


def install_scheduler_cli():
    install_scheduled_tasks()
    print("registered scheduled tasks:")
    print("- NaverPaperCrawler_MorningReportTelegram: daily 06:00, crawl/generate/send Telegram morning report")
    return 0


def uninstall_scheduler_cli():
    uninstall_scheduled_tasks()
    print("removed scheduled tasks:")
    print("- NaverPaperCrawler_DailyPaperPrompt")
    print("- NaverPaperCrawler_OnlineEvery3Hours")
    print("- NaverPaperCrawler_MorningReportTelegram")
    return 0


def main():
    ensure_app_dirs()
    setup_logging()
    args = parse_args()
    try:
        if args.crawl_today_with_prompt:
            return crawl_today_with_prompt()
        if args.install_scheduler:
            return install_scheduler_cli()
        if args.uninstall_scheduler:
            return uninstall_scheduler_cli()
        if args.run_morning_report:
            from morning_report_task import main as morning_report_main

            sys.argv = [sys.argv[0], "--date", "today", "--send-telegram", "--force", "--no-llm"]
            return morning_report_main()
        if args.crawl_online:
            return crawl_online_only()
        if args.crawl_rss:
            return crawl_rss_only()
        if args.crawl_today:
            return crawl_list_only(today_string())
        if args.crawl_date:
            return crawl_list_only(args.crawl_date)
        if args.no_gui:
            return 0
        from gui import run_gui

        return run_gui()
    except Exception:
        logging.exception("Fatal error")
        if not args.no_gui:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "치명적 오류", f"프로그램 오류가 발생했습니다.\n\n상세 로그: {LOG_PATH}")
            app.quit()
        else:
            print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
