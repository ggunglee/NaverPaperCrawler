import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import ARTICLE_TYPE_BY_SOURCE, DB_PATH, ensure_app_dirs


SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    newspaper TEXT NOT NULL,
    oid TEXT NOT NULL,
    paper_section TEXT,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    summary TEXT,
    body TEXT,
    article_type TEXT NOT NULL DEFAULT '지면',
    published_at TEXT,
    category TEXT DEFAULT NULL,
    is_analyzed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

RSS_ERROR_SCHEMA = """
CREATE TABLE IF NOT EXISTS rss_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    section TEXT NOT NULL,
    url TEXT NOT NULL,
    error TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

CRAWL_RUN_SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
"""


INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date);",
    "CREATE INDEX IF NOT EXISTS idx_articles_newspaper ON articles(newspaper);",
    "CREATE INDEX IF NOT EXISTS idx_articles_section ON articles(paper_section);",
    "CREATE INDEX IF NOT EXISTS idx_articles_type ON articles(article_type);",
    "CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);",
    "CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);",
    "CREATE INDEX IF NOT EXISTS idx_articles_title ON articles(title);",
    "CREATE INDEX IF NOT EXISTS idx_crawl_runs_key ON crawl_runs(run_key);",
]


SECTION_SORT_SQL = """
CASE
    WHEN paper_section IS NULL OR paper_section = '' THEN 9999
    ELSE CAST(
        REPLACE(
            REPLACE(
                REPLACE(
                    REPLACE(
                        REPLACE(paper_section, '면', ''),
                        'A',
                        ''
                    ),
                    'B',
                    ''
                ),
                'C',
                ''
            ),
            'D',
            ''
        ) AS INTEGER
    )
END
"""


class Database:
    def __init__(self, path=DB_PATH):
        ensure_app_dirs()
        self.path = str(path)
        self.initialize()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self):
        with self.connect() as conn:
            conn.execute(SCHEMA)
            conn.execute(RSS_ERROR_SCHEMA)
            conn.execute(CRAWL_RUN_SCHEMA)
            self._migrate(conn)
            for sql in INDEXES:
                conn.execute(sql)

    def _migrate(self, conn):
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
        if "is_analyzed" not in columns:
            conn.execute("ALTER TABLE articles ADD COLUMN is_analyzed INTEGER NOT NULL DEFAULT 0")
        if "category" not in columns:
            conn.execute("ALTER TABLE articles ADD COLUMN category TEXT DEFAULT NULL")
        if "article_type" not in columns:
            conn.execute("ALTER TABLE articles ADD COLUMN article_type TEXT NOT NULL DEFAULT '지면'")
        if "published_at" not in columns:
            conn.execute("ALTER TABLE articles ADD COLUMN published_at TEXT")
        conn.execute("UPDATE articles SET paper_section = substr(paper_section, 5) WHERE paper_section LIKE 'RSS-%'")
        conn.execute("UPDATE articles SET paper_section = substr(paper_section, 5) WHERE paper_section LIKE 'API-%'")
        conn.execute("UPDATE articles SET paper_section = '' WHERE paper_section = '온라인'")
        for source, article_type in ARTICLE_TYPE_BY_SOURCE.items():
            conn.execute(
                "UPDATE articles SET article_type = ? WHERE newspaper = ? AND article_type = '지면'",
                (article_type, source),
            )

    def upsert_article(self, article: dict) -> bool:
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            existed = conn.execute("SELECT 1 FROM articles WHERE url = ?", (article["url"],)).fetchone() is not None
            cur = conn.execute(
                """
                INSERT INTO articles (
                    date, newspaper, oid, paper_section, title, url, summary,
                    body, article_type, published_at, category, is_analyzed, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, 0, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    newspaper = excluded.newspaper,
                    oid = excluded.oid,
                    paper_section = excluded.paper_section,
                    summary = COALESCE(excluded.summary, articles.summary),
                    article_type = excluded.article_type,
                    published_at = COALESCE(excluded.published_at, articles.published_at),
                    updated_at = excluded.updated_at
                """,
                (
                    article["date"],
                    article["newspaper"],
                    article["oid"],
                    article.get("paper_section"),
                    article["title"],
                    article["url"],
                    article.get("summary"),
                    article.get("article_type") or ARTICLE_TYPE_BY_SOURCE.get(article["newspaper"], "지면"),
                    article.get("published_at"),
                    now,
                    now,
                ),
            )
            return cur.rowcount > 0 and not existed

    def insert_rss_error(self, source: str, section: str, url: str, error: str):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO rss_errors (source, section, url, error, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source, section, url, error, now),
            )

    def recent_rss_errors(self, limit: int = 20):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM rss_errors
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def crawl_run_completed(self, run_key: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM crawl_runs WHERE run_key = ? AND status = 'completed' LIMIT 1",
                (run_key,),
            ).fetchone()
            return row is not None

    def start_crawl_run(self, run_key: str):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO crawl_runs (run_key, status, started_at)
                VALUES (?, 'running', ?)
                ON CONFLICT(run_key) DO UPDATE SET
                    status = 'running',
                    error = NULL,
                    started_at = excluded.started_at,
                    finished_at = NULL
                """,
                (run_key, now),
            )

    def finish_crawl_run(self, run_key: str, status: str, total: int = 0, inserted: int = 0, error: str | None = None):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO crawl_runs (run_key, status, total, inserted, error, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_key) DO UPDATE SET
                    status = excluded.status,
                    total = excluded.total,
                    inserted = excluded.inserted,
                    error = excluded.error,
                    finished_at = excluded.finished_at
                """,
                (run_key, status, total, inserted, error, now, now),
            )

    def update_body(self, article_id: int, body: str):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                "UPDATE articles SET body = ?, updated_at = ? WHERE id = ?",
                (body, now, article_id),
            )

    def update_category(self, article_ids: list[int], category: str | None):
        if not article_ids:
            return
        now = datetime.now().isoformat(timespec="seconds")
        placeholders = ",".join("?" for _ in article_ids)
        category = category.strip() if category else None
        with self.connect() as conn:
            conn.execute(
                f"UPDATE articles SET category = ?, updated_at = ? WHERE id IN ({placeholders})",
                [category, now, *article_ids],
            )

    def get_article(self, article_id: int):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()

    def get_article_by_url(self, url: str):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM articles WHERE url = ?", (url,)).fetchone()

    def search_articles(
        self,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        newspaper: str | None = None,
        paper_section: str | None = None,
        keyword: str | None = None,
        search_scope: str = "title_summary",
        category: str | None = None,
        article_type: str | None = None,
        exclude_keywords: list[str] | None = None,
    ):
        clauses = []
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
        if newspaper and newspaper != "전체":
            clauses.append("newspaper LIKE ?")
            params.append(f"%{newspaper}%")
        if paper_section:
            clauses.append("paper_section LIKE ?")
            params.append(f"%{paper_section}%")
        if article_type and article_type != "전체":
            clauses.append("article_type = ?")
            params.append(article_type)
        if category and category != "전체":
            if category == "(미지정)":
                clauses.append("(category IS NULL OR category = '')")
            else:
                clauses.append("category = ?")
                params.append(category)
        if keyword:
            like = f"%{keyword}%"
            if search_scope == "title":
                clauses.append("title LIKE ?")
                params.append(like)
            elif search_scope == "title_summary_body":
                clauses.append("(title LIKE ? OR summary LIKE ? OR body LIKE ?)")
                params.extend([like, like, like])
            else:
                clauses.append("(title LIKE ? OR summary LIKE ?)")
                params.extend([like, like])
        for exclude in exclude_keywords or []:
            like = f"%{exclude}%"
            clauses.append("(title NOT LIKE ? AND summary NOT LIKE ? AND body NOT LIKE ?)")
            params.extend([like, like, like])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"""
            SELECT * FROM articles
            {where}
            ORDER BY
                date DESC,
                COALESCE(published_at, '') DESC,
                newspaper ASC,
                {SECTION_SORT_SQL} ASC,
                paper_section ASC,
                id ASC
        """
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def find_articles_by_keywords(
        self,
        date: str | None,
        keywords: list[str],
        exclude_keywords: list[str] | None = None,
        include_existing_body: bool = False,
        date_from: str | None = None,
        date_to: str | None = None,
        article_type: str | None = None,
    ):
        if not keywords:
            return []
        keyword_clauses = []
        date_clauses = []
        params = []
        if date:
            date_clauses.append("date = ?")
            params.append(date)
        if date_from:
            date_clauses.append("date >= ?")
            params.append(date_from)
        if date_to:
            date_clauses.append("date <= ?")
            params.append(date_to)
        if not date_clauses:
            date_clauses.append("1 = 1")
        if article_type and article_type != "전체":
            date_clauses.append("article_type = ?")
            params.append(article_type)
        for keyword in keywords:
            keyword_clauses.append("(title LIKE ? OR summary LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like])
        exclude_clauses = []
        for keyword in exclude_keywords or []:
            exclude_clauses.append("(title NOT LIKE ? AND summary NOT LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like])
        exclude_sql = f" AND {' AND '.join(exclude_clauses)}" if exclude_clauses else ""
        body_clause = "" if include_existing_body else " AND (body IS NULL OR body = '')"
        sql = f"""
            SELECT * FROM articles
            WHERE {' AND '.join(date_clauses)}
              AND ({' OR '.join(keyword_clauses)})
              {exclude_sql}
              {body_clause}
            ORDER BY
                COALESCE(published_at, '') DESC,
                newspaper ASC,
                {SECTION_SORT_SQL} ASC,
                paper_section ASC,
                id ASC
        """
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def has_articles_for_date(self, date: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM articles WHERE date = ? AND article_type = '지면' LIMIT 1", (date,)).fetchone()
            return row is not None

    def distinct_sections(self):
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT paper_section FROM articles
                WHERE paper_section IS NOT NULL AND paper_section != ''
                ORDER BY
                    {SECTION_SORT_SQL} ASC,
                    paper_section ASC
                """
            ).fetchall()
            return [row[0] for row in rows]

    def distinct_categories(self):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT category FROM articles
                WHERE category IS NOT NULL AND category != ''
                ORDER BY category
                """
            ).fetchall()
            return [row[0] for row in rows]
