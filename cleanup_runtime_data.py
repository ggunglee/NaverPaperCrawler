import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR, DB_PATH, SAFE_DIR, ensure_app_dirs
from report_generator import ReportDatabase


def parse_args():
    parser = argparse.ArgumentParser(description="Prune runtime SQLite data for scheduled GitHub runs.")
    parser.add_argument("--days", type=int, default=30, help="Number of days of runtime data to retain.")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Main crawler SQLite database path.")
    parser.add_argument(
        "--feedback-db",
        type=Path,
        default=DATA_DIR / "telegram_feedback.db",
        help="Telegram feedback SQLite database path.",
    )
    return parser.parse_args()


def cutoff_date(days):
    return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")


def table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def prune_main_db(path, cutoff):
    if not path.exists():
        return {"db": str(path), "exists": False}
    ReportDatabase(path)
    deleted = {}
    with sqlite3.connect(path) as conn:
        if table_exists(conn, "article_embeddings"):
            deleted["article_embeddings"] = conn.execute(
                """
                DELETE FROM article_embeddings
                WHERE article_id IN (
                    SELECT id FROM articles
                    WHERE COALESCE(date, '') < ?
                )
                """,
                (cutoff,),
            ).rowcount
        if table_exists(conn, "article_analysis"):
            deleted["article_analysis"] = conn.execute(
                """
                DELETE FROM article_analysis
                WHERE article_id IN (
                    SELECT id FROM articles
                    WHERE COALESCE(date, '') < ?
                )
                """,
                (cutoff,),
            ).rowcount
        if table_exists(conn, "exclusive_claims"):
            deleted["exclusive_claims"] = conn.execute(
                "DELETE FROM exclusive_claims WHERE COALESCE(first_seen_date, '') < ?",
                (cutoff,),
            ).rowcount
        if table_exists(conn, "report_runs"):
            deleted["report_runs"] = conn.execute(
                "DELETE FROM report_runs WHERE COALESCE(report_date, '') < ?",
                (cutoff,),
            ).rowcount
        if table_exists(conn, "articles"):
            deleted["articles"] = conn.execute(
                "DELETE FROM articles WHERE COALESCE(date, '') < ?",
                (cutoff,),
            ).rowcount
        conn.commit()
    with sqlite3.connect(path) as conn:
        conn.execute("VACUUM")
    return {"db": str(path), "exists": True, "cutoff": cutoff, "deleted": deleted}


def prune_feedback_db(path, days):
    if not path.exists():
        return {"db": str(path), "exists": False}
    cutoff_iso = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    deleted = {}
    with sqlite3.connect(path) as conn:
        if table_exists(conn, "feedback_messages"):
            deleted["feedback_messages"] = conn.execute(
                "DELETE FROM feedback_messages WHERE COALESCE(collected_at, '') < ?",
                (cutoff_iso,),
            ).rowcount
            conn.commit()
    with sqlite3.connect(path) as conn:
        conn.execute("VACUUM")
    return {"db": str(path), "exists": True, "cutoff": cutoff_iso, "deleted": deleted}


def prune_old_files(root, days):
    if not root.exists():
        return 0
    cutoff_ts = (datetime.now() - timedelta(days=days)).timestamp()
    count = 0
    for path in root.glob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff_ts:
            path.unlink()
            count += 1
    return count


def main():
    ensure_app_dirs()
    args = parse_args()
    cutoff = cutoff_date(args.days)
    results = [
        prune_main_db(args.db, cutoff),
        prune_feedback_db(args.feedback_db, args.days),
        {"reports_deleted": prune_old_files(SAFE_DIR / "reports", args.days)},
        {"feedback_json_deleted": prune_old_files(SAFE_DIR / "feedback", args.days)},
    ]
    for result in results:
        print(result)


if __name__ == "__main__":
    main()
