import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import urllib.error
import urllib.request
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


MONITOR_KEYWORDS = sorted(
    (
        set(MONITOR_KEYWORDS)
        | {
        "대검찰청",
        "대검",
        "대법원",
        "대법",
        "헌법재판소",
        "헌재",
        "서울중앙지검",
        "서울고검",
        "법무부",
        "공수처",
        "검찰",
        "법원",
        "특검",
        "행정법원",
        "회생법원",
        "가정법원",
        "서울중앙지법",
        "서울고법",
        "변협",
        "대한변호사협회",
        "서울지방변호사회",
        "감찰",
        "감찰위",
        "불기소",
        "약식기소",
        "파산",
        "회생",
        "변호사",
        "비자",
        }
    )
    - {"검사"},
    key=len,
    reverse=True,
)
KNOWN_CATEGORIES = {
    "특검": ["특검", "종합특검", "내란 특검", "김건희 특검", "조작기소 특검", "대장동 특검"],
    "검찰 수사개혁": ["검찰개혁", "수사권", "보완수사", "중수청", "중대범죄수사청", "공소청"],
    "검찰 처분": ["불기소", "약식기소", "기소", "고소", "각하", "서울중앙지검", "서울고검"],
    "검찰 감찰": ["감찰", "감찰위", "대검", "박상용", "연어", "술 파티"],
    "법무부": ["법무부", "비자", "출입국", "체류", "귀화"],
    "법원": ["법원", "대법원", "대법", "서울중앙지법", "서울고법", "행정법원", "회생법원", "가정법원"],
    "헌법재판": ["헌법재판소", "헌재"],
    "법조 제도": ["변협", "대한변호사협회", "서울지방변호사회", "회생", "파산", "변호사"],
    "공수처": ["공수처", "고위공직자범죄수사처"],
}

MARTIAL_LAW_CONTEXT_KEYWORDS = {
    "12·3",
    "12.3",
    "비상계엄",
    "내란",
    "윤석열",
    "조지호",
    "이상민",
    "계엄",
    "특검",
}

MONITOR_KEYWORDS = sorted(
    {
        "대검찰청",
        "대검",
        "대법원",
        "대법",
        "헌법재판소",
        "헌재",
        "서울중앙지검",
        "서울고검",
        "법무부",
        "공수처",
        "검찰",
        "법원",
        "특검",
        "행정법원",
        "회생법원",
        "가정법원",
        "서울중앙지법",
        "서울고법",
        "변협",
        "대한변호사협회",
        "서울지방변호사회",
        "중수청",
        "공소청",
        "보완수사",
        "감찰",
        "불기소",
        "약식기소",
        "파산",
        "회생",
        "비자",
        "출입국",
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

    def morning_articles(self, report_date, online_start=None, online_end=None, include_analyzed=False, limit=None):
        analyzed_clause = "" if include_analyzed else "AND COALESCE(is_analyzed, 0) = 0"
        clauses = [
            "(COALESCE(body, '') != '' OR COALESCE(summary, '') != '')",
            analyzed_clause,
            """
            (
                (article_type = '지면' AND date = ?)
                OR (
                    article_type != '지면'
                    AND published_at IS NOT NULL
                    AND published_at >= ?
                    AND published_at <= ?
                )
            )
            """,
        ]
        params = [report_date, online_start or "", online_end or ""]
        sql = f"""
            SELECT * FROM articles
            WHERE {' AND '.join(clause for clause in clauses if clause)}
            ORDER BY
                CASE WHEN article_type = '지면' THEN 0 ELSE 1 END ASC,
                date ASC,
                newspaper ASC,
                COALESCE(published_at, '') ASC,
                id ASC
        """
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def reset_analysis_for_articles(self, article_ids):
        if not article_ids:
            return
        placeholders = ",".join("?" for _ in article_ids)
        with self.connect() as conn:
            conn.execute(f"UPDATE articles SET is_analyzed = 0 WHERE id IN ({placeholders})", article_ids)
            conn.execute(f"DELETE FROM article_analysis WHERE article_id IN ({placeholders})", article_ids)

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
    parser.add_argument("--only-exclusive", action="store_true", help="Only include articles with exclusive titles.")
    parser.add_argument("--paper-only", action="store_true", help="Only include newspaper-page articles.")
    parser.add_argument("--desk-focus", action="store_true", help="Use stricter legal desk morning-report candidate filtering.")
    parser.add_argument("--morning-scope", action="store_true", help="Use morning scope: report-date paper plus online window.")
    parser.add_argument("--online-from", help="Online article window start, format YYYY-MM-DD HH:MM:SS.")
    parser.add_argument("--online-to", help="Online article window end, format YYYY-MM-DD HH:MM:SS.")
    parser.add_argument("--include-analyzed", action="store_true", help="Include articles already marked analyzed.")
    parser.add_argument("--reset-analysis", action="store_true", help="Reset analysis state for selected report articles before generating.")
    parser.add_argument("--suppress-skipped", action="store_true", help="Do not render skipped/diagnostic sections.")
    parser.add_argument("--limit", type=int, help="Limit pending articles for test runs.")
    parser.add_argument("--output-file", action="store_true", help="Save markdown report under the app reports folder.")
    parser.add_argument("--no-llm", action="store_true", help="Do not call an LLM; render candidate summaries only.")
    parser.add_argument(
        "--llm-backend",
        choices=["gemini", "ollama"],
        default=os.environ.get("REPORT_LLM_BACKEND", "gemini"),
        help="LLM backend for report-worthiness and summary generation.",
    )
    parser.add_argument("--gemini-model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    parser.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", "qwen3:4b"))
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--ollama-timeout", type=int, default=int(os.environ.get("OLLAMA_TIMEOUT", "300")))
    parser.add_argument("--ollama-num-ctx", type=int, default=int(os.environ.get("OLLAMA_NUM_CTX", "4096")))
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
    optional_modules = {
        "google.genai": "optional; needed only for Gemini LLM runs",
        "kss": "optional; built-in sentence splitter is used when missing",
        "numpy": "optional; lexical embedding backend works without it",
    }
    for module_name, missing_detail in optional_modules.items():
        try:
            __import__(module_name)
            checks.append((f"module:{module_name}", True, "installed"))
        except Exception:
            checks.append((f"module:{module_name}", True, missing_detail))
    try:
        __import__("sentence_transformers")
        checks.append(("module:sentence_transformers", True, "installed"))
    except Exception:
        checks.append(("module:sentence_transformers", True, "not installed; lexical fallback will be used"))
    if args.no_llm:
        checks.append(("Gemini API key", True, "not required for --no-llm"))
    else:
        checks.append(("Gemini API key", bool(gemini_api_key()), "configured" if gemini_api_key() else "missing"))
    if args.llm_backend == "ollama":
        ok, detail = ollama_status(args.ollama_url)
        checks.append(("Ollama server", ok, detail))
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
        if is_police_led_article(row):
            continue
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
        if is_police_led_article(row):
            continue
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
    if args.morning_scope:
        rows = db.morning_articles(
            args.date,
            online_start=args.online_from,
            online_end=args.online_to,
            include_analyzed=args.include_analyzed or args.reset_analysis,
            limit=args.limit if args.all_articles else None,
        )
        if args.reset_analysis:
            db.reset_analysis_for_articles([row["id"] for row in rows])
    else:
        rows = db.pending_articles(date=args.date, limit=args.limit if args.all_articles else None)
    candidate_exclusions = []
    if args.paper_only:
        paper_rows = [row for row in rows if (row["article_type"] or "") == "지면"]
        candidate_exclusions.extend(
            (row, "paper_only_excluded", None, None)
            for row in rows
            if row not in paper_rows and matches_monitor_keywords(row)
        )
        rows = paper_rows
    if args.only_exclusive:
        exclusive_rows = [row for row in rows if "단독" in (row["title"] or "")]
        candidate_exclusions.extend(
            (row, "non_exclusive_candidate", None, None)
            for row in rows
            if row not in exclusive_rows and matches_monitor_keywords(row)
        )
        rows = exclusive_rows
    non_police_rows = [row for row in rows if not is_police_led_article(row)]
    candidate_exclusions.extend(
        (row, "police_led_candidate", None, None)
        for row in rows
        if row not in non_police_rows and matches_monitor_keywords(row)
    )
    rows = non_police_rows
    domestic_rows = [row for row in rows if not is_foreign_incidental_article(row)]
    rows = domestic_rows
    report_rows = [row for row in rows if not is_lifestyle_legal_advice(row)]
    candidate_exclusions.extend(
        (row, "lifestyle_legal_advice", None, None)
        for row in rows
        if row not in report_rows and matches_monitor_keywords(row)
    )
    rows = report_rows
    if args.desk_focus:
        desk_rows = [row for row in rows if is_desk_focus_article(row)]
        candidate_exclusions.extend(
            (row, "desk_focus_excluded", None, None)
            for row in rows
            if row not in desk_rows and matches_monitor_keywords(row)
        )
        rows = desk_rows
    if not args.all_articles:
        rows = [row for row in rows if matches_monitor_keywords(row)]
        if args.limit:
            rows = rows[: args.limit]
    rows = sorted(rows, key=same_day_priority_key)
    rows, early_skipped = dedupe_event_rows(rows)
    early_skipped = candidate_exclusions + early_skipped
    if not rows:
        report = f"# 아침 보고서 - {args.date}\n\n새로 분석할 기사가 없습니다.\n"
        output_path = write_report_file(args.date, report) if args.output_file else None
        db.save_report_run(args.date, output_path, [], report)
        return report

    embedder = Embedder(backend=args.embedding_backend)
    skipped = early_skipped
    candidates_by_category = defaultdict(list)
    for row in rows:
        category = recommend_category(row)[0] or row["category"]
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
            result = analyze_with_llm(db, category, category_rows, args)
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
                fallback = fallback_item_if_report_worthy(row)
                if fallback:
                    report_items.append(fallback)
                    db.save_analysis(
                        row["id"],
                        category,
                        "candidate_llm_no_response",
                        report_summary_md=fallback["summary"],
                    )
                else:
                    db.save_analysis(row["id"], category, "analyzed_no_response", mark_analyzed=False)
                continue
            if item.get("is_report_worthy"):
                summary = polish_report_summary(item.get("report_summary") or "", row)
                if not summary_passes_quality_gate(summary, row):
                    fallback = fallback_item_if_report_worthy(row) or fallback_items([row])[0]
                    if fallback:
                        report_items.append(fallback)
                        db.save_analysis(
                            row["id"],
                            category,
                            "candidate_quality_fallback",
                            exclusive_score=item.get("exclusive_score"),
                            new_facts_md="\n".join(item.get("new_claims", [])),
                            report_summary_md=fallback["summary"],
                            raw_response=json.dumps(item, ensure_ascii=False),
                        )
                        continue
                report_items.append(
                    {
                        "headline": format_headline(row),
                        "summary": summary,
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

    report = render_report(args.date, report_items, [] if getattr(args, "suppress_skipped", False) else skipped)
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


def analyze_with_llm(db, category, rows, args):
    if args.llm_backend == "ollama":
        return analyze_with_ollama(db, category, rows, args)
    return analyze_with_gemini(db, category, rows, args.gemini_model)


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


def analyze_with_ollama(db, category, rows, args):
    prompt = build_prompt(
        db,
        category,
        rows,
        article_char_limit=2200,
        claim_limit=25,
        baseline_char_limit=1600,
    )
    payload = {
        "model": args.ollama_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": args.ollama_num_ctx,
        },
    }
    url = args.ollama_url.rstrip("/") + "/api/generate"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.ollama_timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
    data = json.loads(raw)
    text = data.get("response") or data.get("thinking") or ""
    if not text.strip():
        raise RuntimeError("Ollama returned an empty response")
    return parse_json_response(text)


def build_prompt(db, category, rows, article_char_limit=9000, claim_limit=80, baseline_char_limit=BASELINE_MAX_CHARS):
    baseline = trim_text(db.baseline(category), baseline_char_limit) or "(아직 누적 요약 없음)"
    claims = db.claims_for_category(category, limit=claim_limit)
    claim_lines = "\n".join(f"- {row['claim_text']}" for row in claims[:claim_limit]) or "(관련 단독 claim 없음)"
    article_blocks = []
    for row in rows:
        article_blocks.append(
            "\n".join(
                [
                    f"article_id: {row['id']}",
                    f"title: {row['title']}",
                    f"source: {row['newspaper']} {row['paper_section'] or ''}".strip(),
                    f"url: {row['url']}",
                    "relevant_body:",
                    focused_article_text(row, article_char_limit),
                ]
            )
        )
    return f"""
너는 한국 법조/정치 뉴스 데스크의 아침 보고 보조자다.
기존 baseline과 단독 claim DB에 이미 있는 내용은 반복하지 말고, 새로 추가된 팩트나 상황 변화만 골라라.
배경 설명은 새 팩트를 이해하는 데 필요한 최소한만 쓴다.
문체는 기자가 데스크에 넘기는 아침 보고체로 쓴다. 절대 '~습니다', '~합니다', '~했습니다'로 끝내지 마라.
각 report_summary는 한 줄 문자열 안에 2~4문장으로 쓰고, 문장 끝은 주로 '~포착', '~확인돼', '~판단', '~답변', '~파악돼', '~전해져', '~밝혀', '~제출', '~산정', '~설명'처럼 명사형/연결형 보고체로 끝내라.
제목·언론사·게재면은 프로그램이 원 기사 메타데이터로 붙인다. report_summary에는 제목, 매체명, 게재면을 반복하지 말고 본문 요약만 써라.
좋은 예:
- '대통령 관저 이전 특혜' 의혹을 수사 중인 2차 종합특검팀이 당시 대통령실의 예산 마련 지시에 압박감을 느낀 행안부 공무원이 '차라리 인사 조치되는 편이 낫겠다'며 반발했던 정황을 포착. 2022년 중순 관저 이전 업무를 담당한 행안부 공무원들은 추가 비용 마련 주문을 받고선 '차라리 질책성 인사조치를 시켜달라'는 취지로 대화를 주고받아.
- 한겨레가 6~10일 1701명을 조사한 결과 47.9%가 검찰의 보완수사 기능을 남겨둬야 한다고 답변. 특검에 공소취소 권한을 부여한 조작기소 특검법안에 대해선 51.6%가 찬성, 31.5%가 반대한다고 응답.
- 중수청의 인력 규모를 놓고 법무부는 1000여 명, 행안부는 4000명 안팎으로 맞서고 있는 것으로 파악돼.

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
      "headline_line": "",
      "report_summary": "새롭게 추가된 팩트와 상황 변화만 2~4문장으로 요약. '~습니다'체 금지, 아침 보고체로 작성.",
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


def ollama_status(base_url):
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return False, str(exc)
    models = [item.get("name", "") for item in data.get("models", [])]
    return True, ", ".join(models) if models else "running; no models installed"


def parse_json_response(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = "".join(
            char if char in "\t\n\r" or ord(char) >= 0x20 else " "
            for char in text
        )
        return json.loads(cleaned, strict=False)


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


def same_day_priority_key(row):
    title = row["title"] or ""
    is_exclusive = "단독" in title
    is_yonhap = (row["newspaper"] or "") == "연합뉴스"
    time_key = row["published_at"] or row["created_at"] or ""
    return (0 if is_exclusive else 1, 0 if is_yonhap else 1, time_key, row["id"])


def title_token_similarity(left, right):
    left_tokens = title_tokens(left)
    right_tokens = title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def dedupe_event_rows(rows):
    kept = []
    skipped = []
    by_key = {}
    for row in rows:
        key = article_event_key(row)
        if not key:
            kept.append(row)
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = row
            kept.append(row)
            continue
        current_priority = report_article_priority(row)
        existing_priority = report_article_priority(existing)
        if current_priority < existing_priority:
            kept = [current if current["id"] != existing["id"] else row for current in kept]
            by_key[key] = row
            skipped.append((existing, "same_event_duplicate", 1.0, row["id"]))
        else:
            skipped.append((row, "same_event_duplicate", 1.0, existing["id"]))
    return kept, skipped


def report_article_priority(row):
    title = row["title"] or ""
    is_yonhap = (row["newspaper"] or "") == "연합뉴스"
    return (
        0 if "단독" in title else 1,
        0 if is_yonhap else 1,
        row["published_at"] or row["created_at"] or "",
        row["id"],
    )


def article_event_key(row):
    text = normalize_match_text(" ".join([row["title"] or "", row["summary"] or "", focused_article_text(row, 700)]))
    if "윤석열" in text and "특검" in text and ("소환" in text or "출석" in text):
        date_match = re.search(r"(\d{1,2})일", text)
        return f"윤석열:특검소환:{date_match.group(1) if date_match else ''}"
    if "박영수" in text and "대장동" in text and "약식기소" in text:
        return "박영수딸:대장동:약식기소"
    if "중수청" in text and ("1000" in text or "4000" in text or "인력" in text):
        return "중수청:인력규모"
    if "보완수사권" in text and ("47" in text or "37" in text or "유권자" in text):
        return "검찰:보완수사권:여론조사"
    if "박상용" in text and ("감찰" in text or "징계" in text):
        return "박상용:감찰징계"
    if "김건희" in text and "매관매직" in text and "구형" in text:
        return "김건희:매관매직:구형"
    if "방통위" in text and "2인체제" in text and "KBS" in text and "감사" in text:
        return "방통위:2인체제:KBS감사"
    if ("제이알글로벌리츠" in text or "제이알리츠" in text) and "회생" in text:
        return "제이알리츠:회생절차"
    if "김어준" in text and "명예훼손" in text and "구형" in text:
        return "김어준:명예훼손:구형"
    if "택배대리점" in text and "살해사주" in text and "구형" in text:
        return "택배대리점:살해사주:구형"
    if "가습기살균제" in text and "불기소" in text:
        return "가습기살균제:불기소"
    if "네팔" in text and "비자" in text and "법무부" in text:
        return "네팔노모:비자변경"
    if "관저" in text and "예산" in text and ("행안부" in text or "인사" in text):
        return "관저이전:예산압박"
    return None


def title_tokens(text):
    text = (text or "").replace("尹", "윤석열")
    tokens = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower()))
    return {token for token in tokens if token not in {"종합", "단독", "속보"}}


def normalize_match_text(text):
    return re.sub(r"[\W_]+", "", text or "")


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
                focused_article_text(row, 2500),
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
    if any(keyword in text for keyword in ["중수청", "보완수사권", "검찰개혁", "공소청"]):
        return "검찰 수사개혁", 3, ["검찰 제도"]
    if any(keyword in text for keyword in ["감찰위", "감찰", "박상용", "대검"]):
        return "검찰 감찰", 3, ["검찰 감찰"]
    if any(keyword in text for keyword in ["불기소", "약식기소", "기소", "구형", "고소", "서울중앙지검"]):
        return "검찰 처분", 3, ["검찰 처분"]
    if any(keyword in text for keyword in ["법무부", "비자", "출입국"]):
        return "법무부", 3, ["법무부"]
    if any(keyword in text for keyword in ["파산", "회생", "변호사"]):
        return "법조 제도", 3, ["법조 제도"]
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


def is_police_led_article(row):
    title = row["title"] or ""
    title = re.sub(r"^\s*\[[^\]]*단독[^\]]*\]\s*", "", title)
    return "경찰" in title


def is_foreign_incidental_article(row):
    title = row["title"] or ""
    text = f"{title}\n{row['summary'] or ''}\n{row['body'] or ''}"
    foreign_terms = [
        "데일리메일",
        "외신",
        "현지시각",
        "현지시간",
        "영국",
        "미국",
        "일본",
        "중국",
        "프랑스",
        "독일",
        "브라질",
        "인도",
        "Daily Mail",
        "Reuters",
        "AP통신",
        "BBC",
        "CNN",
    ]
    domestic_anchor_terms = [
        "대법",
        "대법원",
        "헌재",
        "헌법재판소",
        "법무부",
        "특검",
        "공수처",
        "대검",
        "중수청",
        "공소청",
        "서울중앙지검",
        "서울고검",
        "서울중앙지법",
        "서울고법",
        "서울행정법원",
        "김건희",
        "윤석열",
    ]
    if not any(term in text for term in foreign_terms):
        return False
    if any(term in text for term in domestic_anchor_terms):
        return False
    return True


def is_lifestyle_legal_advice(row):
    text = f"{row['title'] or ''}\n{row['summary'] or ''}\n{row['body'] or ''}"
    advice_terms = [
        "상담소",
        "사연자",
        "생활법률",
        "조인섭 변호사",
        "법률상담",
        "상간녀 소송",
        "상간남 소송",
    ]
    if any(term in text for term in advice_terms):
        return True
    return "라디오" in text and any(term in text for term in ["상담", "사연", "생활법률"])


def is_desk_focus_article(row):
    title = row["title"] or ""
    section = row["paper_section"] or ""
    text = f"{title}\n{row['summary'] or ''}\n{row['body'] or ''}"
    if (row["article_type"] or "") == "지면" and re.match(r"^[BCD]\d+", section):
        return False
    if any(term in title for term in ["살해", "살인", "폭행", "음주운전"]) and not any(
        term in title for term in ["검찰", "법원", "법무부", "공수처", "특검"]
    ):
        return False
    exclude_terms = [
        "[기고]",
        "[오늘의 주요일정]",
        "오늘의 주요일정",
        "주요일정",
        "시시각각",
        "사설",
        "칼럼",
        "오피니언",
        "지선",
        "지방선거",
        "후보",
        "판세",
        "선대위",
        "공천",
        "유세",
        "보수 결집",
        "항소법원",
        "의료",
        "중과실",
        "쇼핑",
        "관광",
        "유통업계",
        "브랜드 공간",
        "국회 의사봉",
        "국회의장",
        "국정과제 입법",
        "원 구성",
        "수락연설",
        "친명",
        "원전",
        "한수원",
        "한전",
        "수출",
        "감사원",
    ]
    if any(term in title for term in exclude_terms):
        return False
    strong_terms = [
        "보완수사권",
        "중수청",
        "공소청",
        "검찰개혁",
        "감찰위",
        "박상용",
        "불기소",
        "약식기소",
        "법무부",
        "비자",
        "체류변경",
        "출입국",
        "외국인 환자",
        "재정 능력",
        "불허",
        "통보",
        "파산",
        "회생",
        "관저",
        "계엄",
        "김건희",
        "결심공판",
        "구형",
        "알선수재",
        "공판",
        "재판",
    ]
    if any(term in text for term in strong_terms):
        return True
    return "단독" in title and matches_monitor_keywords(row)


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
    decimal_placeholder = "<DECIMAL_POINT>"
    text = re.sub(r"(?<=\d)\.(?=\d)", decimal_placeholder, text)
    parts = re.split(r"(?<=[.!?。])\s+|(?<=[.!?。])(?=[가-힣A-Za-z0-9\"'“‘])", text)
    sentences = []
    for part in parts:
        part = part.replace(decimal_placeholder, ".").strip()
        if part:
            sentences.append(part)
    return sentences


def clean_article_text(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"^(?:정치|사회|경제|문화|국제|전국)\s+전체\s+", " ", text)
    text = re.sub(r"\b\d{2}\.\d{2}\s+(?:오전|오후)\s+\d{1,2}:\d{2}\b", " ", text)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\[(?:앵커|리포트|기자)\]", " ", text)
    text = re.sub(r"\[[^\]]*(?:관련기사|설명할경향|단독)[^\]]*\]", " ", text)
    text = re.sub(r"(?:사진|그래픽|자료사진)\s*[=:]\s*[^.。]*", " ", text)
    text = re.sub(r"[가-힣]{2,5}\s*(?:선임|인턴|수습)?기자\s*[^.。]*", " ", text)
    text = re.sub(r"(무단전재|재배포 금지|저작권자|Copyright|구독|좋아요|댓글).*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def focused_article_text(row, limit=2200):
    title = row["title"] or ""
    source = clean_article_text(row["body"] or row["summary"] or "")
    sentences = split_sentences(source)
    selected = []
    for index, sentence in enumerate(sentences):
        if is_noise_sentence(sentence):
            continue
        score = sentence_score_for_report(sentence, title)
        if score > 0:
            selected.append((score, index, sentence))
    selected.sort(key=lambda item: item[0], reverse=True)
    top_ranked = selected[:10]
    top_ranked.sort(key=lambda item: item[1])
    top = [sentence for _, _, sentence in top_ranked]
    if not top:
        top = [sentence for sentence in sentences if not is_noise_sentence(sentence)][:8]
    return trim_text(" ".join(top), limit)


def is_noise_sentence(sentence):
    sentence = sentence.strip()
    if len(sentence) < 15:
        return True
    hard_noise_terms = [
        "연합뉴스",
        "뉴스1",
        "뉴시스",
        "게티이미지",
        "자료사진",
        "그래픽",
        "로비에",
        "서울중앙지검 로비",
        "액자가 걸려",
        "걸려 있어",
        "하고 있어",
        "수락연설",
        "tomato99",
        "혈중알코올",
        "면허취소",
        "입국 규제 지침",
        "재외교포 A씨",
        "의 모습",
        "창간",
        "본문의 이해를 돕기",
        "인공지능이 자동으로",
        "세 줄 요약",
        "전체 내용을 이해하기",
        "사회 전체",
        "국회 의사봉",
        "국정과제 입법",
        "[앵커]",
        "[리포트]",
    ]
    if any(term in sentence for term in hard_noise_terms):
        return True
    if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", sentence):
        return True
    if re.search(r"[가-힣]{2,5}\s*(?:선임|인턴|수습)?기자", sentence):
        return True
    return False


def sentence_score_for_report(sentence, title=""):
    text = f"{title} {sentence}"
    score = 0
    title_terms = title_tokens(title)
    sentence_terms = title_tokens(sentence)
    score += 3 * len(title_terms & sentence_terms)
    for keyword in MONITOR_KEYWORDS:
        if keyword in text:
            score += 2
    high_value_terms = [
        "확인",
        "포착",
        "파악",
        "밝혔다",
        "답변",
        "제출",
        "처분",
        "불기소",
        "약식기소",
        "기소",
        "수사",
        "특검",
        "법무부",
        "검찰",
        "중수청",
        "보완수사권",
        "감찰",
        "비자",
        "체류변경",
        "출입국",
        "외국인 환자",
        "재정 능력",
        "불허",
        "통보",
        "파산",
        "회생",
        "조사",
        "%",
        "명",
    ]
    for term in high_value_terms:
        if term in text:
            score += 1
    if "단독" in title:
        score += 1
    return score


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
    hidden_reasons = {"same_event_duplicate", "lifestyle_legal_advice"}
    skipped = [item for item in skipped if item[1] not in hidden_reasons]
    lines = []
    if not items:
        lines.append("[보고 기사]")
        lines.append("")
        lines.append("새로 보고할 기사가 없음.")
        lines.append("")
    else:
        lines.append("[보고 기사]")
        lines.append("")
        for item in items:
            lines.append(f"※{item['headline']}")
            lines.append(f"-{normalize_report_tone(item['summary']).lstrip('-').strip()}")
            lines.append(item["url"])
            lines.append("")

    if skipped:
        lines.append("[보류/제외 기사]")
        lines.append("")
        similarity_rows = [
            item
            for item in skipped
            if item[1] in {"similarity", "same_day_similarity", "same_event_duplicate"}
        ]
        uncertain_rows = [item for item in skipped if item[1] == "category_uncertain"]
        failed_rows = [item for item in skipped if str(item[1]).startswith("llm_failed")]

        if similarity_rows:
            lines.append("## 걸러진 스트레이트/반복 기사")
            lines.append("")
            for row, reason, score, matched_id in similarity_rows:
                if reason == "same_day_similarity":
                    label = "당일 유사도"
                elif reason == "same_event_duplicate":
                    label = "동일 사안"
                else:
                    label = "유사도"
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
                reason_labels = {
                    "paper_only_excluded": "지면 범위 제외",
                    "non_exclusive_candidate": "단독 아님",
                    "police_led_candidate": "경찰 주체 제외",
                    "lifestyle_legal_advice": "생활법률/상담성 기사 제외",
                    "desk_focus_excluded": "법조 초점 낮음",
                }
                suffix = f"유사도 {score:.2f}" if score is not None else reason_labels.get(reason, reason)
                lines.append(f"- {row['title']} / {row['newspaper']} ({suffix})")
                lines.append(f"  {row['url']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def fallback_items(rows):
    items = []
    for row in rows:
        summary = extractive_report_summary(row)
        items.append(
            {
                "headline": format_headline(row),
                "summary": normalize_report_tone(trim_text(summary, 450)),
                "url": row["url"],
            }
        )
    return items


def extractive_report_summary(row):
    sentences = report_sentence_candidates(row)
    summary = " ".join(sentences[:2]) or (row["summary"] or row["title"])
    return polish_report_summary(summary, row)


def report_sentence_candidates(row, max_sentences=2, max_total_chars=420):
    raw_source = row["body"] or row["summary"] or ""
    raw_sentences = []
    for line in raw_source.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = clean_article_text(line)
        if not line:
            continue
        raw_sentences.extend(split_sentences(line))
    scored = []
    for index, sentence in enumerate(raw_sentences):
        sentence = clean_candidate_sentence(sentence, row)
        if not sentence or is_noise_sentence(sentence) or is_bad_report_sentence(sentence, row):
            continue
        score = sentence_score_for_report(sentence, row["title"] or "")
        if score <= 0:
            continue
        scored.append((score, index, sentence))
    if not scored:
        return []
    max_score = max(item[0] for item in scored)
    min_pick_score = max(1, max_score - 5)
    scored = [item for item in scored if item[0] >= min_pick_score]
    scored.sort(key=lambda item: item[1])
    picked = []
    total = 0
    seen_norms = set()
    for _, index, sentence in scored:
        norm = normalize_claim(sentence)
        if any(norm and (norm in existing or existing in norm) for existing in seen_norms):
            continue
        sentence_len = len(sentence)
        if picked and total + sentence_len > max_total_chars:
            continue
        picked.append((index, sentence))
        total += sentence_len
        seen_norms.add(norm)
        if len(picked) >= max_sentences:
            break
    picked.sort(key=lambda item: item[0])
    return [sentence for _, sentence in picked]


def clean_candidate_sentence(sentence, row=None):
    sentence = clean_article_text(sentence)
    sentence = re.sub(r"^(?:정치|사회|경제|문화|국제|전국)\s+전체\s+", "", sentence)
    sentence = re.sub(r"^[\s)\]〉》.,·:;|]+", "", sentence)
    if row:
        title = re.escape(clean_report_title(row["title"] or ""))
        if title:
            sentence = re.sub(rf"^{title}\s*", "", sentence)
    sentence = re.sub(r"\s+", " ", sentence).strip()
    return sentence


def is_bad_report_sentence(sentence, row=None):
    if len(sentence) > 260:
        return True
    if re.search(r"(니다|니까|됩니다|합니다|입니다|겁니다|이에요|예요|어요|아요)[.!?。]?$", sentence):
        return True
    if not re.search(r"(다|됨|음|고|며|돼|해|계획|요구|통보|평가|판단|확인|포착|파악)[.!?。]?$", sentence):
        return True
    bad_endings = (
        "주요",
        "주요.",
        "통해",
        "통해.",
        "보다도",
        "보다도.",
        "저마다",
        "저마다.",
        "대해선",
        "대해선.",
        "필요",
        "필요.",
        "등을",
        "등을.",
        "면서다",
        "면서다.",
    )
    if sentence.endswith(bad_endings):
        return True
    bad_terms = [
        "전체 내용을 이해",
        "인공지능이 자동",
        "세 줄 요약",
        "기자 =",
        "무단 전재",
        "많이 본 뉴스",
    ]
    if any(term in sentence for term in bad_terms):
        return True
    if row and title_token_similarity(sentence, row["title"] or "") >= 0.8 and len(sentence) < 80:
        return True
    return False


def fallback_item_if_report_worthy(row):
    text = f"{row['title'] or ''}\n{row['summary'] or ''}\n{row['body'] or ''}"
    strong_terms = {
        "단독",
        "불기소",
        "약식기소",
        "기소",
        "보완수사권",
        "중수청",
        "공소청",
        "감찰위",
        "법무부",
        "비자",
        "파산",
        "회생",
        "관저",
    }
    if not any(term in text for term in strong_terms):
        return None
    return fallback_items([row])[0]


def format_headline(row):
    title = clean_report_title(row["title"] or "")
    section = format_section(row["paper_section"] or "")
    source = short_newspaper_name(row["newspaper"] or "")
    suffix = f"{source} {section}".strip()
    return f"{title}/{suffix}" if suffix else title


def clean_report_title(title):
    return re.sub(r"^\s*\[[^\]]*단독[^\]]*\]\s*", "", title or "").strip()


def short_newspaper_name(name):
    aliases = {
        "경향신문": "경향",
        "국민일보": "국민",
        "동아일보": "동아",
        "문화일보": "문화",
        "서울신문": "서울",
        "세계일보": "세계",
        "조선일보": "조선",
        "중앙일보": "중앙",
        "한겨레": "한겨레",
        "한국일보": "한국",
    }
    return aliases.get(name, name)


def format_section(section):
    section = (section or "").strip()
    section = re.sub(r"^A(?=\d)", "", section)
    return section


def normalize_report_tone(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"(?<=\d)\.\s+(?=\d)", ".", text)
    text = re.sub(r'(["“][^"”]+?다["”])\s*고\s+(?:말|밝|설명|답변|주장)했(?:다|습니다)\.?', r"\1고.", text)
    text = re.sub(r'(["“][^"”]+?다["”])\s*고\s+(?:말함|밝힘|설명|답변|주장)\.?', r"\1고.", text)
    text = re.sub(r"(라고|다고)\s+(?:말|밝|설명|답변|주장)했(?:다|습니다)\.?", r"\1.", text)
    replacements = [
        ("처분했다.", "처분."),
        ("처분했다", "처분"),
        ("기소했다.", "기소."),
        ("기소했다", "기소"),
        ("기소했습니다.", "기소."),
        ("기소했습니다", "기소"),
        ("불허했다.", "불허."),
        ("불허했다", "불허"),
        ("제출했다.", "제출."),
        ("제출했다", "제출"),
        ("주장했다.", "주장."),
        ("주장했다", "주장"),
        ("확인했다.", "확인."),
        ("확인했다", "확인"),
        ("인정했다.", "인정."),
        ("인정했다", "인정"),
        ("기각했다.", "기각."),
        ("기각했다", "기각"),
        ("각하했다.", "각하."),
        ("각하했다", "각하"),
        ("선고했다.", "선고."),
        ("선고했다", "선고"),
        ("선고받았다.", "선고."),
        ("선고받았다", "선고"),
        ("요청했다.", "요청."),
        ("요청했다", "요청"),
        ("결정했다.", "결정."),
        ("결정했다", "결정"),
        ("내렸다.", "결정."),
        ("내렸다", "결정"),
        ("파악했다.", "파악."),
        ("파악했다", "파악"),
        ("밝혔다.", "밝혀."),
        ("밝혔다", "밝혀"),
        ("말했다.", "말해."),
        ("말했다", "말해"),
        ("설명했다.", "설명."),
        ("설명했다", "설명"),
        ("답변했다.", "답변."),
        ("답변했다", "답변"),
        ("판단했다.", "판단."),
        ("판단했다", "판단"),
        ("계획이다.", "계획."),
        ("계획이다", "계획"),
        ("계획입니다.", "계획."),
        ("계획입니다", "계획"),
        ("상태다.", "상태."),
        ("상태다", "상태"),
        ("상태입니다.", "상태."),
        ("상태입니다", "상태"),
        ("했다.", "."),
        ("했다", ""),
        ("하다.", "."),
        ("하다", ""),
        ("있다.", "있음."),
        ("있다", "있음"),
        ("있었다.", "있었음."),
        ("있었다", "있었음"),
        ("보였다.", "보였음."),
        ("보였다", "보였음"),
        ("이었다.", "이었음."),
        ("이었다", "이었음"),
        ("이었습니다.", "이었음."),
        ("이었습니다", "이었음"),
        ("였다.", "였음."),
        ("였다", "였음"),
        ("였습니다.", "였음."),
        ("였습니다", "였음"),
        ("뿐이었습니다.", "뿐이었음."),
        ("뿐이었습니다", "뿐이었음"),
        ("이다.", "."),
        ("이다", ""),
        ("입니다.", "."),
        ("입니다", ""),
        ("겁니다.", "."),
        ("겁니다", ""),
        ("됐다.", "됨."),
        ("됐다", "됨"),
        ("했습니다.", "."),
        ("했습니다", ""),
        ("합니다.", "."),
        ("합니다", ""),
        ("이어갑니다.", "이어감."),
        ("이어갑니다", "이어감"),
        ("살펴봅니다.", "살펴봄."),
        ("살펴봅니다", "살펴봄"),
        ("나옵니다.", "나옴."),
        ("나옵니다", "나옴"),
        ("보입니다.", "보임."),
        ("보입니다", "보임"),
        ("나왔습니다.", "나옴."),
        ("나왔습니다", "나옴"),
        ("나왔다.", "나옴."),
        ("나왔다", "나옴"),
        ("나타났습니다.", "나타남."),
        ("나타났습니다", "나타남"),
        ("나타났다.", "나타남."),
        ("나타났다", "나타남"),
        ("받았습니다.", "받음."),
        ("받았습니다", "받음"),
        ("받았다.", "받음."),
        ("받았다", "받음"),
        ("맡았습니다.", "맡음."),
        ("맡았습니다", "맡음"),
        ("맡았다.", "맡음."),
        ("맡았다", "맡음"),
        ("취득했습니다.", "취득."),
        ("취득했습니다", "취득"),
        ("됐습니다.", "됨."),
        ("됐습니다", "됨"),
        ("되었습니다.", "됨."),
        ("되었습니다", "됨"),
        ("밝혔습니다.", "밝힘."),
        ("밝혔습니다", "밝힘"),
        ("말했습니다.", "말함."),
        ("말했습니다", "말함"),
        ("설명했습니다.", "설명."),
        ("설명했습니다", "설명"),
        ("답변했습니다.", "답변."),
        ("답변했습니다", "답변"),
        ("확인됐습니다.", "확인돼."),
        ("확인됐습니다", "확인돼"),
        ("있었습니다.", "있었음."),
        ("있었습니다", "있었음"),
        ("파악됐습니다.", "파악돼."),
        ("파악됐습니다", "파악돼"),
        ("판단했습니다.", "판단."),
        ("판단했습니다", "판단"),
        ("나섰다.", "나섬."),
        ("나섰다", "나섬"),
        ("주어졌다.", "주어짐."),
        ("주어졌다", "주어짐"),
        ("의심한다.", "의심."),
        ("의심한다", "의심"),
        ("진행할 계획이다.", "진행할 계획."),
        ("진행할 계획이다", "진행할 계획"),
        ("요구했다.", "요구."),
        ("요구했다", "요구"),
        ("통보했다.", "통보."),
        ("통보했다", "통보"),
        ("평가가 나온다.", "평가."),
        ("평가가 나온다", "평가"),
        ("선고됐다.", "선고됨."),
        ("선고됐다", "선고됨"),
        ("돌았다.", "돌았음."),
        ("돌았다", "돌았음"),
        ("완화됐다.", "완화됨."),
        ("완화됐다", "완화됨"),
        ("해왔다.", "해왔음."),
        ("해왔다", "해왔음"),
        ("해 왔다.", "해 왔음."),
        ("해 왔다", "해 왔음"),
        ("판단했다.", "판단."),
        ("판단했다", "판단"),
        ("한다.", "."),
        ("한다", ""),
        ("된다.", "됨."),
        ("된다", "됨"),
    ]
    for old, new in replacements:
        if old.endswith("."):
            text = text.replace(old, new)
        else:
            text = re.sub(re.escape(old) + r"(?=[\s.。]|$)", new, text)
    verb_endings = [
        ("처분해.", "처분."),
        ("기소해.", "기소."),
        ("약식기소해.", "약식기소."),
        ("불허해.", "불허."),
        ("제출해.", "제출."),
        ("확인돼.", "확인."),
        ("파악돼.", "파악."),
        ("포착돼.", "포착."),
        ("밝혀.", "밝힘."),
        ("전해져.", "전해짐."),
        ("드러나.", "드러남."),
        ("나타나.", "나타남."),
        ("제기돼.", "제기."),
        ("약속해.", "약속."),
        ("지적해.", "지적."),
        ("강조해.", "강조."),
        ("반박해.", "반박."),
    ]
    for old, new in verb_endings:
        text = text.replace(old, new)
    text = re.sub(r"했다(?=[\s.。]|$)", "", text)
    text = re.sub(r"하다(?=[\s.。]|$)", "", text)
    text = re.sub(r"받았다(?=[\s.。]|$)", "받음", text)
    text = re.sub(r"나왔다(?=[\s.。]|$)", "나옴", text)
    text = re.sub(r"맡았다(?=[\s.。]|$)", "맡음", text)
    text = re.sub(r"선고받았다(?=[\s.。]|$)", "선고", text)
    text = re.sub(r"선고했다(?=[\s.。]|$)", "선고", text)
    text = re.sub(r"요청했다(?=[\s.。]|$)", "요청", text)
    text = re.sub(r"결과가 나온\.", "결과가 나옴.", text)
    text = re.sub(r"([가-힣]{2,})(?:해|함)\.", r"\1.", text)
    text = re.sub(r"([가-힣]{2,})이었다\.", r"\1이었음.", text)
    text = re.sub(r"([가-힣]{2,})이다\.", r"\1.", text)
    text = re.sub(r"필요\.\s+인력", "필요 인력", text)
    text = re.sub(r"\s+\.", ".", text)
    text = re.sub(r"\.{2,}", ".", text)
    return text


def polish_report_summary(text, row=None):
    text = clean_article_text(text)
    text = re.sub(r"필요\.\s+인력", "필요 인력", text)
    sentences = []
    for sentence in split_sentences(text):
        sentence = normalize_report_tone(sentence)
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if not sentence or is_noise_sentence(sentence):
            continue
        if row and not sentence_has_source_overlap(sentence, row):
            continue
        if not sentence.endswith("."):
            sentence += "."
        sentences.append(sentence)
    if not sentences:
        text = normalize_report_tone(text)
        text = re.sub(r"필요\.\s+인력", "필요 인력", text)
        return text if text.endswith(".") else text + "."
    summary = " ".join(sentences[:4])
    return re.sub(r"필요\.\s+인력", "필요 인력", summary)


def sentence_has_source_overlap(sentence, row):
    source = clean_article_text("\n".join([row["title"] or "", row["summary"] or "", row["body"] or ""]))
    sentence_tokens = {token for token in title_tokens(sentence) if len(token) >= 2}
    source_tokens = title_tokens(source)
    if not sentence_tokens:
        return False
    return len(sentence_tokens & source_tokens) / len(sentence_tokens) >= 0.45


def summary_passes_quality_gate(summary, row):
    summary = polish_report_summary(summary, row)
    if not summary or len(summary) < 40:
        return False
    forbidden = [
        "기자",
        "@",
        "사진",
        "로비에",
        "액자가 걸려",
        "걸려 있어",
        "하고 있어",
        "수락연설",
        "구독",
        "무단전재",
        "창간",
    ]
    if any(term in summary for term in forbidden):
        return False
    if any(term in summary for term in ["습니다", "합니다", "했습니다", "하였습니다"]):
        return False
    if re.search(r"(했다|하였다|합니다|했습니다|입니다|이다|있다|해|돼|져)\.", summary):
        return False
    source = clean_article_text("\n".join([row["title"] or "", row["summary"] or "", row["body"] or ""]))
    summary_tokens = title_tokens(summary)
    source_tokens = title_tokens(source)
    meaningful = {token for token in summary_tokens if len(token) >= 2}
    if meaningful:
        overlap = len(meaningful & source_tokens) / max(len(meaningful), 1)
        if overlap < 0.35:
            return False
    return True


def trim_text(text, limit):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


if __name__ == "__main__":
    main()
