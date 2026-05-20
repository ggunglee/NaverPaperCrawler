import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from database import Database


logger = logging.getLogger(__name__)


LAWTIMES_URLS = [
    "https://www.lawtimes.co.kr/",
    "https://www.lawtimes.co.kr/news",
    "https://www.lawtimes.co.kr/news/court",
    "https://www.lawtimes.co.kr/news/prosecution",
    "https://www.lawtimes.co.kr/news/ministry",
]


class LawtimesCrawler:
    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def crawl_latest(self, max_articles=80, published_at: datetime | None = None) -> dict:
        articles = []
        seen = set()
        errors = []
        for url in LAWTIMES_URLS:
            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or response.encoding
                for article in self.parse_listing(response.text, published_at=published_at):
                    if article["url"] in seen:
                        continue
                    seen.add(article["url"])
                    articles.append(article)
                    if len(articles) >= max_articles:
                        break
            except Exception as exc:
                logger.warning("Lawtimes crawl failed: %s (%s)", url, exc)
                errors.append(f"법률신문 수집 실패: {url} ({exc})")
            if len(articles) >= max_articles:
                break

        inserted = 0
        for article in articles:
            if self.db.upsert_article(article):
                inserted += 1
        return {"total": len(articles), "inserted": inserted, "errors": errors}

    def parse_listing(self, html, published_at: datetime | None = None):
        soup = BeautifulSoup(html, "html.parser")
        now = published_at or datetime.now()
        articles = []
        for link in soup.select('a[href*="/news"]'):
            href = link.get("href") or ""
            url = normalize_lawtimes_url(href)
            if not url:
                continue
            title = clean_text(link.get_text(" ", strip=True))
            if not title:
                image = link.select_one("img[alt]")
                title = clean_text(image.get("alt", "")) if image else ""
            if not title or title in {"뉴스", "전체", "더보기", "최신기사"}:
                continue
            summary = nearby_summary(link)
            articles.append(
                {
                    "date": now.strftime("%Y%m%d"),
                    "newspaper": "법률신문",
                    "oid": "lawtimes",
                    "paper_section": "법률",
                    "article_type": "온라인",
                    "published_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "title": title,
                    "url": url,
                    "summary": summary,
                }
            )
        return dedupe_by_url(articles)


def normalize_lawtimes_url(href):
    url = urljoin("https://www.lawtimes.co.kr", href)
    parsed = urlparse(url)
    if "lawtimes.co.kr" not in parsed.netloc:
        return ""
    if "articleView" in parsed.path:
        idx = parse_qs(parsed.query).get("idxno", [""])[0]
        return f"https://www.lawtimes.co.kr/news/articleView.html?idxno={idx}" if idx else url
    match = re.search(r"/news/(\d+)", parsed.path)
    if match:
        return f"https://www.lawtimes.co.kr/news/{match.group(1)}"
    return ""


def nearby_summary(link):
    parent = link.find_parent(["li", "article", "div"])
    if not parent:
        return ""
    title = clean_text(link.get_text(" ", strip=True))
    text = clean_text(parent.get_text(" ", strip=True))
    if title and text.startswith(title):
        text = text[len(title):].strip()
    return text[:500]


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def dedupe_by_url(articles):
    seen = set()
    output = []
    for article in articles:
        if article["url"] in seen:
            continue
        seen.add(article["url"])
        output.append(article)
    return output
