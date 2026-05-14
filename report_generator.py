import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from config import DB_PATH, SAFE_DIR, load_config, load_env_values
from crawler import NaverPaperCrawler
from database import Database


REPORT_DIR = SAFE_DIR / "reports"
EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"
SIMILARITY_THRESHOLD = 0.85
EXCLUSIVE_THRESHOLD = 0.82
BASELINE_MAX_CHARS = 5000

KNOWN_CATEGORIES = {
    "2차 종합특검": [
        "2차 종합특검",
        "종합특검",
        "특검팀",
        "특검",
        "김건희 특검",
        "내란 특검",
        "채상병 특검",
    ],
    "내란 재판": [
        "내란",
        "비상계엄",
        "계엄",
        "윤석열",
        "국회 해제",
        "합참",
        "계엄사",
    ],
    "김건희 재판": [
        "김건희",
        "도이치",
        "주가조작",
        "명품백",
        "공천개입",
    ],
    "공수처": [
        "공수처",
        "고위공직자범죄수사처",
        "오동운",
    ],
    "중수청": [
        "중수청",
        "중대범죄수사청",
        "수사청",
    ],
    "검찰 수사개혁": [
        "검찰개혁",
        "수사권",
        "보완수사",
        "전건송치",
        "공소청",
        "검경",
        "검찰청 폐지",
    ],
}

MARTIAL_LAW_CONTEXT_KEYWORDS = {
    "12·3",
    "12.3",
    "비상계엄",
    "윤석열",
    "김용현",
    "조지호",
    "여인형",
    "곽종근",
    "노상원",
    "문상호",
    "계엄사",
    "합참",
}

MONITOR_KEYWORDS = sorted(
    {
        "특검",
        "검찰",
        "법원",
        "재판",
        "공수처",
        "중수청",
        "공소청",
        "수사",
        "기소",
        "구속",
        "압수수색",
        "김건희",
        "도이치",
        "내란",
        "계엄",
        "법무부",
        "대법원",
        "헌법재판소",
    },
    key=len,
    reverse=True,
)


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS category_baselines (
        category TEXT PRIMARY KEY,
        baseline_md TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS article_embeddings (
        article_id INTEGER NOT NULL,
        model_name TEXT NOT NULL,
        embedding_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(article_id, model_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exclusive_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        claim_text TEXT NOT NULL,
        normalized_claim TEXT,
        embedding_json TEXT,
        source_article_id INTEGER,
        source_title TEXT,
        source_url TEXT,
        first_seen_date TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS article_analysis (
        article_id INTEGER PRIMARY KEY,
        category TEXT,
        status TEXT NOT NULL,
        similarity_score REAL,
        matched_article_id INTEGER,
        exclusive_score REAL,
        new_facts_md TEXT,
        report_summary_md TEXT,
        raw_response TEXT,
        analyzed_at TEXT NOT NULL,
        error TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS report_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_date TEXT NOT NULL,
        output_path TEXT,
        created_at TEXT NOT NULL,
        article_ids TEXT,
        summary_md TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_exclusive_claims_category ON exclusive_claims(category)",
    "CREATE INDEX IF NOT EXISTS idx_exclusive_claims_first_seen ON exclusive_claims(first_seen_date)",
    "CREATE INDEX IF NOT EXISTS idx_exclusive_claims_source_norm ON exclusive_claims(source_article_id, normalized_claim)",
    "CREATE INDEX IF NOT EXISTS idx_article_analysis_category ON article_analysis(category)",
    "CREATE INDEX IF NOT EXISTS idx_article_analysis_status ON article_analysis(status)",
]


class ReportDatabase:
    def __init__(self, path=DB_PATH):
        self.path = str(path)
        Database(path)
        self.ensure_schema()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self):
        with self.connect() as conn:
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)
            self._migrate_embedding_cache(conn)
            conn.commit()

    def _migrate_embedding_cache(self, conn):
        columns = conn.execute("PRAGMA table_info(article_embeddings)").fetchall()
        pk_columns = [row["name"] for row in columns if row["pk"]]
        if pk_columns != ["article_id"]:
            return
        conn.execute("ALTER TABLE article_embeddings RENAME TO article_embeddings_old")
        conn.execute(
            """
            CREATE TABLE article_embeddings (
                article_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(article_id, model_name)
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO article_embeddings (article_id, model_name, embedding_json, created_at)
            SELECT article_id, model_name, embedding_json, created_at
            FROM article_embeddings_old
            """
        )
        conn.execute("DROP TABLE article_embeddings_old")

    def pending_articles(self, date=None, limit=None):
        clauses = ["COALESCE(is_analyzed, 0) = 0", "(COALESCE(body, '') != '' OR COALESCE(summary, '') != '')"]
        params = []
        if date:
            clauses.append("date = ?")
            params.append(date)
        sql = f"""
            SELECT * FROM articles
            WHERE {' AND '.join(clauses)}
            ORDER BY date DESC, COALESCE(published_at, '') DESC, id ASC
        """
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def uncategorized_articles(self, date=None, date_from=None, date_to=None, limit=None):
        clauses = ["(category IS NULL OR category = '')", "(COALESCE(body, '') != '' OR COALESCE(summary, '') != '')"]
        params = []
        if date:
            clauses.append("date = ?")
            params.append(date)
        if date_from:
            clauses.append("date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("date <= ?")
            params.append(date_to)
        sql = f"""
            SELECT * FROM articles
            WHERE {' AND '.join(clauses)}
            ORDER BY date DESC, COALESCE(published_at, '') DESC, id ASC
        """
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def articles_for_range(self, date_from, date_to, only_exclusive=False):
        clauses = ["date BETWEEN ? AND ?", "COALESCE(body, '') != ''"]
        params = [date_from, date_to]
        if only_exclusive:
            clauses.append("title LIKE '%단독%'")
        sql = f"""
            SELECT * FROM articles
            WHERE {' AND '.join(clauses)}
            ORDER BY date ASC, id ASC
        """
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def recent_category_articles(self, category, before_id, days=45, limit=100):
        with self.connect() as conn:
            base = conn.execute("SELECT date FROM articles WHERE id = ?", (before_id,)).fetchone()
            if not base:
                return []
            start = (datetime.strptime(base["date"], "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")
            return conn.execute(
                """
                SELECT * FROM articles
                WHERE id != ?
                  AND COALESCE(body, '') != ''
                  AND COALESCE(category, '') = ?
                  AND date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                LIMIT ?
                """,
                (before_id, category, start, base["date"], limit),
            ).fetchall()

    def embedding(self, article_id, model_name):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT embedding_json FROM article_embeddings WHERE article_id = ? AND model_name = ?",
                (article_id, model_name),
            ).fetchone()
        return json.loads(row["embedding_json"]) if row else None

    def save_embedding(self, article_id, model_name, vector):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO article_embeddings (article_id, model_name, embedding_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(article_id, model_name) DO UPDATE SET
                    embedding_json = excluded.embedding_json,
                    created_at = excluded.created_at
                """,
                (article_id, model_name, json.dumps(vector), now),
            )
            conn.commit()

    def baseline(self, category):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT baseline_md FROM category_baselines WHERE category = ?",
                (category,),
            ).fetchone()
        return row["baseline_md"] if row else ""

    def save_baseline(self, category, baseline_md):
        now = datetime.now().isoformat(timespec="seconds")
        baseline_md = trim_text(baseline_md, BASELINE_MAX_CHARS)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO category_baselines (category, baseline_md, updated_at, version)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(category) DO UPDATE SET
                    baseline_md = excluded.baseline_md,
                    updated_at = excluded.updated_at,
                    version = category_baselines.version + 1
                """,
                (category, baseline_md, now),
            )
            conn.commit()

    def save_analysis(
        self,
        article_id,
        category,
        status,
        similarity_score=None,
        matched_article_id=None,
        exclusive_score=None,
        new_facts_md=None,
        report_summary_md=None,
        raw_response=None,
        error=None,
        mark_analyzed=True,
    ):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO article_analysis (
                    article_id, category, status, similarity_score, matched_article_id,
                    exclusive_score, new_facts_md, report_summary_md, raw_response,
                    analyzed_at, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    category = excluded.category,
                    status = excluded.status,
                    similarity_score = excluded.similarity_score,
                    matched_article_id = excluded.matched_article_id,
                    exclusive_score = excluded.exclusive_score,
                    new_facts_md = excluded.new_facts_md,
                    report_summary_md = excluded.report_summary_md,
                    raw_response = excluded.raw_response,
                    analyzed_at = excluded.analyzed_at,
                    error = excluded.error
                """,
                (
                    article_id,
                    category,
                    status,
                    similarity_score,
                    matched_article_id,
                    exclusive_score,
                    new_facts_md,
                    report_summary_md,
                    raw_response,
                    now,
                    error,
                ),
            )
            if mark_analyzed:
                conn.execute("UPDATE articles SET is_analyzed = 1 WHERE id = ?", (article_id,))
            conn.commit()

    def save_claim(self, claim, category, article, embedding):
        now = datetime.now().isoformat(timespec="seconds")
        normalized = normalize_claim(claim)
        with self.connect() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM exclusive_claims
                WHERE source_article_id = ? AND normalized_claim = ?
                LIMIT 1
                """,
                (article["id"], normalized),
            ).fetchone()
            if exists:
                return False
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO exclusive_claims (
                    category, claim_text, normalized_claim, embedding_json,
                    source_article_id, source_title, source_url, first_seen_date, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    claim,
                    normalized,
                    json.dumps(embedding),
                    article["id"],
                    article["title"],
                    article["url"],
                    article["date"],
                    now,
                ),
            )
            conn.commit()
            return cur.rowcount > 0

    def claims_for_category(self, category, limit=200):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM exclusive_claims
                WHERE COALESCE(category, '') = ?
                ORDER BY first_seen_date DESC, id DESC
                LIMIT ?
                """,
                (category, limit),
            ).fetchall()

    def all_claims(self):
        with self.connect() as conn:
            return conn.execute("SELECT id, claim_text FROM exclusive_claims ORDER BY id").fetchall()

    def update_claim_embedding(self, claim_id, embedding):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                "UPDATE exclusive_claims SET embedding_json = ?, created_at = COALESCE(created_at, ?) WHERE id = ?",
                (json.dumps(embedding), now, claim_id),
            )
            conn.commit()

    def save_report_run(self, report_date, output_path, article_ids, summary_md):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO report_runs (report_date, output_path, created_at, article_ids, summary_md)
                VALUES (?, ?, ?, ?, ?)
                """,
                (report_date, output_path, now, json.dumps(article_ids), summary_md),
            )
            conn.commit()

    def set_article_category(self, article_id, category):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                "UPDATE articles SET category = ?, updated_at = ? WHERE id = ?",
                (category, now, article_id),
            )
            conn.commit()


class Embedder:
    def __init__(self, model_name=EMBEDDING_MODEL, backend="auto"):
        self.model_name = model_name
        self.backend = backend
        self._model = None

    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                if self.backend == "sentence":
                    raise SystemExit(
                        "sentence-transformers is not installed. Run: "
                        "venv\\Scripts\\python.exe -m pip install -r requirements-report.txt"
                    ) from exc
                self.backend = "lexical"
                return None
            self._model = SentenceTransformer(self.model_name)
            self.backend = "sentence"
        return self._model

    def encode(self, text):
        if self.backend == "lexical":
            return lexical_vector(text)
        model = self.model()
        if model is None:
            return lexical_vector(text)
        vector = model.encode([text], normalize_embeddings=True)[0]
        return [float(x) for x in vector]

    @property
    def cache_name(self):
        return self.model_name if self.backend != "lexical" else "lexical-stable-v2"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate morning reports from crawled Naver articles.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="Report date YYYYMMDD or today.")
    parser.add_argument("--from", dest="date_from", help="Start date YYYYMMDD for seeding/backfill.")
    parser.add_argument("--to", dest="date_to", help="End date YYYYMMDD for seeding/backfill.")
    parser.add_argument("--seed-exclusive", action="store_true", help="Build the exclusive-claim comparison DB.")
    parser.add_argument(
        "--refresh-claim-embeddings",
        action="store_true",
        help="Rebuild stored exclusive-claim vectors with the selected embedding backend.",
    )
    parser.add_argument("--backfill-source", action="store_true", help="Crawl list pages for --from to --to before seeding.")
    parser.add_argument("--preflight", action="store_true", help="Check dependencies, DB schema, and API-key readiness.")
    parser.add_argument("--classify-uncertain", action="store_true", help="Ask category for ambiguous articles in terminal.")
    parser.add_argument("--suggest-categories", action="store_true", help="Suggest categories for uncategorized articles.")
    parser.add_argument("--all-articles", action="store_true", help="Include articles outside monitor keywords.")
    parser.add_argument("--limit", type=int, help="Limit pending articles for test runs.")
    parser.add_argument("--output-file", action="store_true", help="Save markdown report under the app reports folder.")
    parser.add_argument("--no-llm", action="store_true", help="Do not call Gemini; render candidate summaries only.")
    parser.add_argument("--gemini-model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    parser.add_argument("--embedding-backend", choices=["auto", "sentence", "lexical"], default="auto")
    parser.add_argument("--similarity-threshold", type=float, default=SIMILARITY_THRESHOLD)
    parser.add_argument(
        "--same-day-threshold",
        type=float,
        default=0.6,
        help="Threshold for suppressing duplicate articles within the same report run.",
    )
    parser.add_argument("--exclusive-threshold", type=float, default=EXCLUSIVE_THRESHOLD)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.date == "today":
        args.date = datetime.now().strftime("%Y%m%d")
    db = ReportDatabase()

    if args.preflight:
        run_preflight(db, args)
        return

    if args.backfill_source:
        require_range(args)
        backfill_source(args.date_from, args.date_to)

    if args.suggest_categories:
        suggest_categories(db, args)

    if args.seed_exclusive:
        require_range(args)
        count = seed_exclusive_claims(db, args)
        print(f"exclusive_claims seeded: {count}")

    if args.refresh_claim_embeddings:
        count = refresh_claim_embeddings(db, args)
        print(f"exclusive_claims embeddings refreshed: {count}")

    if (
        not args.seed_exclusive
        and not args.backfill_source
        and not args.suggest_categories
        and not args.refresh_claim_embeddings
    ):
        report = generate_report(db, args)
        print(report)


def require_range(args):
    if not args.date_from or not args.date_to:
        raise SystemExit("--from and --to are required for this command.")


def run_preflight(db, args):
    checks = []
    checks.append(("SQLite DB", Path(db.path).exists(), db.path))
    with db.connect() as conn:
        for table in [
            "articles",
            "exclusive_claims",
            "article_embeddings",
            "article_analysis",
            "category_baselines",
            "report_runs",
        ]:
            try:
                count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                checks.append((f"table:{table}", True, str(count)))
            except Exception as exc:
                checks.append((f"table:{table}", False, str(exc)))
    for module_name in ["google.genai", "kss", "numpy"]:
        try:
            __import__(module_name)
            checks.append((f"module:{module_name}", True, "installed"))
        except Exception as exc:
            checks.append((f"module:{module_name}", False, str(exc)))
    try:
        __import__("sentence_transformers")
        checks.append(("module:sentence_transformers", True, "installed"))
    except Exception:
        checks.append(("module:sentence_transformers", True, "not installed; lexical fallback will be used"))
    checks.append(("Gemini API key", bool(gemini_api_key()), "configured" if gemini_api_key() else "missing"))
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")


def backfill_source(date_from, date_to):
    crawler = NaverPaperCrawler()
    db = ReportDatabase()
    current = datetime.strptime(date_from, "%Y%m%d")
    end = datetime.strptime(date_to, "%Y%m%d")
    while current <= end:
        date = current.strftime("%Y%m%d")
        print(f"crawl list: {date}")
        crawler.crawl_date(date)
        fetch_exclusive_candidate_bodies(db, crawler, date)
        current += timedelta(days=1)


def fetch_exclusive_candidate_bodies(db, crawler, date):
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM articles
            WHERE date = ?
              AND title LIKE '%단독%'
              AND COALESCE(body, '') = ''
            ORDER BY id ASC
            """,
            (date,),
        ).fetchall()
    for row in rows:
        if not matches_monitor_keywords(row):
            continue
        print(f"fetch body: {row['id']} {row['title']}")
        crawler.fetch_and_store_body(row["id"], force=False)


def suggest_categories(db, args):
    rows = db.uncategorized_articles(
        date=None if args.date_from or args.date_to else args.date,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit if args.all_articles else None,
    )
    if not args.all_articles:
        rows = [row for row in rows if matches_monitor_keywords(row)]
        if args.limit:
            rows = rows[: args.limit]
    uncertain = []
    for row in rows:
        if row["category"]:
            continue
        category, confidence, reasons = recommend_category(row)
        if category and confidence >= 2:
            db.set_article_category(row["id"], category)
            print(f"[auto] {row['id']} {category}: {row['title']}")
        else:
            uncertain.append(row)
            print(f"[uncertain] {row['id']} {row['title']}")
            if reasons:
                print(f"  hints: {', '.join(reasons)}")

    if args.classify_uncertain and uncertain:
        ask_categories(db, uncertain)
    elif uncertain:
        print("\nRun again with --classify-uncertain to classify ambiguous articles.")


def ask_categories(db, rows):
    categories = list(KNOWN_CATEGORIES)
    for row in rows:
        print("\n" + "-" * 72)
        print(f"id={row['id']} {row['title']}")
        print(trim_text(row["summary"] or row["body"] or "", 500))
        for index, category in enumerate(categories, start=1):
            print(f"{index}. {category}")
        print("0. skip")
        value = input("category number or custom text: ").strip()
        if not value or value == "0":
            continue
        if value.isdigit() and 1 <= int(value) <= len(categories):
            category = categories[int(value) - 1]
        else:
            category = value
        db.set_article_category(row["id"], category)
        print(f"saved: {category}")


def seed_exclusive_claims(db, args):
    embedder = Embedder(backend=args.embedding_backend)
    rows = db.articles_for_range(args.date_from, args.date_to, only_exclusive=True)
    count = 0
    for row in rows:
        if not matches_monitor_keywords(row):
            continue
        category = row["category"] or recommend_category(row)[0] or "미분류"
        if not row["category"] and category != "미분류":
            db.set_article_category(row["id"], category)
        sentences = split_sentences(row["body"] or row["summary"] or "", prefer_kss=False)
        for sentence in sentences:
            if not useful_claim(sentence):
                continue
            vector = embedder.encode(sentence)
            if is_duplicate_claim(db, category, vector, args.exclusive_threshold):
                continue
            if db.save_claim(sentence, category, row, vector):
                count += 1
    return count


def refresh_claim_embeddings(db, args):
    embedder = Embedder(backend=args.embedding_backend)
    count = 0
    for row in db.all_claims():
        db.update_claim_embedding(row["id"], embedder.encode(row["claim_text"]))
        count += 1
    return count


def generate_report(db, args):
    rows = db.pending_articles(date=args.date, limit=args.limit if args.all_articles else None)
    if not args.all_articles:
        rows = [row for row in rows if matches_monitor_keywords(row)]
        if args.limit:
            rows = rows[: args.limit]
    if not rows:
        report = f"# 아침 보고서 - {args.date}\n\n새로 분석할 기사가 없습니다.\n"
        output_path = write_report_file(args.date, report) if args.output_file else None
        db.save_report_run(args.date, output_path, [], report)
        return report

    embedder = Embedder(backend=args.embedding_backend)
    skipped = []
    candidates_by_category = defaultdict(list)
    for row in rows:
        category = row["category"] or recommend_category(row)[0]
        if not category:
            skipped.append((row, "category_uncertain", None, None))
            continue
        if not row["category"]:
            db.set_article_category(row["id"], category)
        score, matched_id = most_similar_past_article(db, embedder, row, category)
        if score >= args.similarity_threshold:
            db.save_analysis(
                row["id"],
                category,
                "skipped_similarity",
                similarity_score=score,
                matched_article_id=matched_id,
            )
            skipped.append((row, "similarity", score, matched_id))
            continue
        same_day_score, same_day_id = most_similar_candidate(db, embedder, row, candidates_by_category[category])
        if same_day_score >= args.same_day_threshold:
            db.save_analysis(
                row["id"],
                category,
                "skipped_same_day_similarity",
                similarity_score=same_day_score,
                matched_article_id=same_day_id,
            )
            skipped.append((row, "same_day_similarity", same_day_score, same_day_id))
            continue
        candidates_by_category[category].append(row)

    report_items = []
    for category, category_rows in candidates_by_category.items():
        if args.no_llm:
            items = fallback_items(category_rows)
            report_items.extend(items)
            for row, item in zip(category_rows, items):
                db.save_analysis(
                    row["id"],
                    category,
                    "candidate_no_llm",
                    report_summary_md=item["summary"],
                    mark_analyzed=False,
                )
            continue
        try:
            result = analyze_with_gemini(db, category, category_rows, args.gemini_model)
        except Exception as exc:
            for row in category_rows:
                db.save_analysis(
                    row["id"],
                    category,
                    "failed",
                    error=str(exc),
                    mark_analyzed=False,
                )
            skipped.extend((row, f"llm_failed: {exc}", None, None) for row in category_rows)
            continue
        db.save_baseline(category, result.get("updated_baseline_md") or db.baseline(category))
        by_id = {int(item["article_id"]): item for item in result.get("items", []) if item.get("article_id")}
        for row in category_rows:
            item = by_id.get(row["id"])
            if not item:
                db.save_analysis(row["id"], category, "analyzed_no_response", mark_analyzed=False)
                continue
            if item.get("is_report_worthy"):
                report_items.append(
                    {
                        "headline": item.get("headline_line") or format_headline(row),
                        "summary": item.get("report_summary") or "",
                        "url": row["url"],
                    }
                )
                status = "analyzed_new"
            else:
                status = "analyzed_no_new"
            db.save_analysis(
                row["id"],
                category,
                status,
                exclusive_score=item.get("exclusive_score"),
                new_facts_md="\n".join(item.get("new_claims", [])),
                report_summary_md=item.get("report_summary"),
                raw_response=json.dumps(item, ensure_ascii=False),
            )
            for claim in item.get("new_claims", []):
                if claim.strip():
                    vector = embedder.encode(claim)
                    if not is_duplicate_claim(db, category, vector, EXCLUSIVE_THRESHOLD):
                        db.save_claim(claim, category, row, vector)

    report = render_report(args.date, report_items, skipped)
    output_path = None
    if args.output_file:
        output_path = write_report_file(args.date, report)
    db.save_report_run(args.date, output_path, [row["id"] for row in rows], report)
    return report


def write_report_file(report_date, report):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORT_DIR / f"{report_date}_morning_report.md"
    output.write_text(report, encoding="utf-8")
    output_path = str(output)
    print(f"saved: {output_path}")
    return output_path


def analyze_with_gemini(db, category, rows, model_name):
    api_key = gemini_api_key()
    if not api_key:
        raise SystemExit("Gemini API key not found. Save it in GUI config or set GEMINI_API_KEY.")
    prompt = build_prompt(db, category, rows)
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = getattr(response, "text", "") or ""
    except ImportError:
        try:
            import google.generativeai as old_genai
        except ImportError as exc:
            raise SystemExit(
                "google-genai is not installed. Run: "
                "venv\\Scripts\\python.exe -m pip install -r requirements-report.txt"
            ) from exc
        old_genai.configure(api_key=api_key)
        model = old_genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = getattr(response, "text", "") or ""
    return parse_json_response(text)


def build_prompt(db, category, rows):
    baseline = db.baseline(category) or "(아직 누적 요약 없음)"
    claims = db.claims_for_category(category, limit=80)
    claim_lines = "\n".join(f"- {row['claim_text']}" for row in claims[:80]) or "(관련 단독 claim 없음)"
    article_blocks = []
    for row in rows:
        article_blocks.append(
            "\n".join(
                [
                    f"article_id: {row['id']}",
                    f"title: {row['title']}",
                    f"source: {row['newspaper']} {row['paper_section'] or ''}".strip(),
                    f"url: {row['url']}",
                    "body:",
                    trim_text(row["body"] or row["summary"] or "", 9000),
                ]
            )
        )
    return f"""
너는 한국 법조/정치 뉴스 데스크의 아침 보고 보조자다.
기존 baseline과 단독 claim DB에 이미 있는 내용은 반복하지 말고, 새로 추가된 팩트나 상황 변화만 골라라.
배경 설명은 새 팩트를 이해하는 데 필요한 최소한만 쓴다.
문체는 기자 아침 보고용으로 '- ... 달해', '- ... 검토중', '- ... 전해져'처럼 간결하게 쓴다.

[카테고리]
{category}

[기존 누적 baseline]
{baseline}

[관련 단독 claim DB]
{claim_lines}

[새 기사]
{chr(10).join(article_blocks)}

아래 JSON만 반환하라. Markdown 코드블록은 쓰지 마라.
{{
  "items": [
    {{
      "article_id": 123,
      "is_report_worthy": true,
      "exclusive_score": 0.0,
      "headline_line": "제목/매체 지면",
      "report_summary": "새롭게 추가된 팩트와 상황 변화만 2~4문장으로 요약.",
      "new_claims": ["문장 단위 새 claim"]
    }}
  ],
  "updated_baseline_md": "최신 상황을 반영한 카테고리 누적 요약. {BASELINE_MAX_CHARS}자 이내."
}}
"""


def gemini_api_key():
    config = load_config()
    env = load_env_values()
    return (
        config.get("gemini_api_key")
        or env.get("GEMINI_API_KEY")
        or env.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )


def parse_json_response(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    return json.loads(text)


def most_similar_past_article(db, embedder, row, category):
    current = article_embedding(db, embedder, row)
    best_score = 0.0
    best_id = None
    for past in db.recent_category_articles(category, row["id"]):
        past_vector = article_embedding(db, embedder, past)
        score = cosine(current, past_vector)
        if score > best_score:
            best_score = score
            best_id = past["id"]
    return best_score, best_id


def most_similar_candidate(db, embedder, row, candidates):
    current = article_embedding(db, embedder, row)
    best_score = 0.0
    best_id = None
    for candidate in candidates:
        score = max(
            cosine(current, article_embedding(db, embedder, candidate)),
            title_token_similarity(row["title"], candidate["title"]),
        )
        if score > best_score:
            best_score = score
            best_id = candidate["id"]
    return best_score, best_id


def title_token_similarity(left, right):
    left_tokens = title_tokens(left)
    right_tokens = title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def title_tokens(text):
    text = (text or "").replace("尹", "윤석열")
    tokens = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower()))
    return {token for token in tokens if token not in {"종합", "단독", "속보"}}


def article_embedding(db, embedder, row):
    cached = db.embedding(row["id"], embedder.cache_name)
    if cached:
        return cached
    text = article_embedding_text(row)
    vector = embedder.encode(text)
    db.save_embedding(row["id"], embedder.cache_name, vector)
    return vector


def article_embedding_text(row):
    return trim_text(
        "\n".join(
            [
                row["title"] or "",
                row["summary"] or "",
                row["body"] or "",
            ]
        ),
        3500,
    )


def is_duplicate_claim(db, category, vector, threshold):
    for row in db.claims_for_category(category, limit=500):
        if not row["embedding_json"]:
            continue
        score = cosine(vector, json.loads(row["embedding_json"]))
        if score >= threshold:
            return True
    return False


def recommend_category(row):
    text = f"{row['title'] or ''}\n{row['summary'] or ''}\n{trim_text(row['body'] or '', 1200)}"
    if "2차 종합특검" in text or "종합특검" in text:
        return "2차 종합특검", 99, ["종합특검"]
    scores = []
    for category, keywords in KNOWN_CATEGORIES.items():
        if category == "내란 재판" and not any(keyword in text for keyword in MARTIAL_LAW_CONTEXT_KEYWORDS):
            continue
        hits = [keyword for keyword in keywords if keyword in text]
        if hits:
            scores.append((len(hits), category, hits))
    if not scores:
        return None, 0, []
    scores.sort(reverse=True)
    top_score, category, hits = scores[0]
    if len(scores) > 1 and scores[1][0] == top_score:
        return None, top_score, hits + scores[1][2]
    return category, top_score, hits


def matches_monitor_keywords(row):
    text = f"{row['title'] or ''}\n{row['summary'] or ''}\n{row['body'] or ''}"
    return any(keyword in text for keyword in MONITOR_KEYWORDS)


def split_sentences(text, prefer_kss=False):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    if prefer_kss:
        try:
            import kss

            return [sentence.strip() for sentence in kss.split_sentences(text) if sentence.strip()]
        except ImportError:
            pass
    parts = re.split(
        r"(?<=[.!?。])\s+|(?<=[.!?。])(?=[가-힣A-Za-z0-9\"'“‘])|(?<=다)\s+|(?<=요)\s+",
        text,
    )
    sentences = []
    for part in parts:
        part = part.strip()
        if part:
            sentences.append(part)
    return sentences


def useful_claim(sentence):
    if len(sentence) < 25 or len(sentence) > 450:
        return False
    if not matches_monitor_keywords({"title": sentence, "summary": "", "body": ""}):
        return False
    noise = ["기자", "무단", "저작권", "네이버", "구독", "영상"]
    return not any(word in sentence for word in noise)


def normalize_claim(text):
    return re.sub(r"[\W_]+", "", text or "").lower()


def cosine(left, right):
    if not left or not right:
        return 0.0
    total = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return total / (left_norm * right_norm)


def lexical_vector(text, dimensions=1024):
    vector = [0.0] * dimensions
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", text or "")
    for token in tokens:
        token = token.lower()
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest, "big") % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def render_report(report_date, items, skipped):
    lines = [f"# 아침 보고서 - {report_date}", ""]
    if not items:
        lines.append("새로운 팩트로 보고할 기사가 없습니다.")
        lines.append("")
    for item in items:
        lines.append(f"※{item['headline']}")
        lines.append(f"-{item['summary'].lstrip('-').strip()}")
        lines.append(item["url"])
        lines.append("")

    if skipped:
        similarity_rows = [item for item in skipped if item[1] in {"similarity", "same_day_similarity"}]
        uncertain_rows = [item for item in skipped if item[1] == "category_uncertain"]
        failed_rows = [item for item in skipped if str(item[1]).startswith("llm_failed")]

        if similarity_rows:
            lines.append("## 걸러진 스트레이트/반복 기사")
            lines.append("")
            for row, reason, score, matched_id in similarity_rows:
                label = "당일 유사도" if reason == "same_day_similarity" else "유사도"
                suffix = f"{label} {score:.2f}" if score is not None else reason
                lines.append(f"- {row['title']} / {row['newspaper']} ({suffix})")
                lines.append(f"  {row['url']}")
            lines.append("")

        if uncertain_rows:
            lines.append("## 분류 필요 기사")
            lines.append("")
            for row, reason, score, matched_id in uncertain_rows:
                lines.append(f"- {row['title']} / {row['newspaper']}")
                lines.append(f"  {row['url']}")
            lines.append("")

        if failed_rows:
            lines.append("## 분석 실패 기사")
            lines.append("")
            for row, reason, score, matched_id in failed_rows:
                lines.append(f"- {row['title']} / {row['newspaper']} ({reason})")
                lines.append(f"  {row['url']}")
            lines.append("")

        other_rows = [
            item
            for item in skipped
            if item not in similarity_rows and item not in uncertain_rows and item not in failed_rows
        ]
        if other_rows:
            lines.append("## 기타 제외 기사")
            lines.append("")
            for row, reason, score, matched_id in other_rows:
                suffix = f"유사도 {score:.2f}" if score is not None else reason
                lines.append(f"- {row['title']} / {row['newspaper']} ({suffix})")
                lines.append(f"  {row['url']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def fallback_items(rows):
    items = []
    for row in rows:
        source = row["body"] or row["summary"] or ""
        first_sentence = split_sentences(source)[:1]
        summary = first_sentence[0] if first_sentence else (row["summary"] or row["title"])
        items.append(
            {
                "headline": format_headline(row),
                "summary": trim_text(summary, 450),
                "url": row["url"],
            }
        )
    return items


def format_headline(row):
    section = row["paper_section"] or ""
    source = row["newspaper"] or ""
    suffix = f"{source} {section}".strip()
    return f"{row['title']}/{suffix}" if suffix else row["title"]


def trim_text(text, limit):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


if __name__ == "__main__":
    main()
