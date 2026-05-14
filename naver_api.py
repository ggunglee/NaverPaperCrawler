import html
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from urllib.parse import parse_qs

import requests

from config import (
    ARTICLE_TYPE_BY_SOURCE,
    DEFAULT_HEADERS,
    NAVER_API_FALLBACK_OUTLETS,
    NAVER_API_MONITOR_KEYWORDS,
    NAVER_SID_SECTIONS,
    ONLINE_NEWS_SOURCES,
    get_naver_api_credentials,
)
from database import Database


logger = logging.getLogger(__name__)


class NaverNewsApiClient:
    URL = "https://openapi.naver.com/v1/search/news.json"

    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self.client_id, self.client_secret = get_naver_api_credentials()

    def available(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def collect_keywords(
        self,
        keywords: list[str],
        start_dt: datetime,
        end_dt: datetime,
        exclude_keywords: list[str] | None = None,
    ) -> dict:
        if not self.available():
            return {"total": 0, "inserted": 0, "failures": ["네이버 API 키가 없습니다."]}
        seen_urls = set()
        total = 0
        inserted = 0
        failures = []
        for keyword in keywords:
            try:
                for item in self.search(keyword):
                    article = self.item_to_article(item)
                    if not article:
                        continue
                    haystack = f"{article['title']} {article.get('summary') or ''}"
                    if any(keyword in haystack for keyword in exclude_keywords or []):
                        continue
                    published = article.pop("_published_dt", None)
                    if published and not (start_dt <= published <= end_dt):
                        continue
                    if article["url"] in seen_urls:
                        continue
                    seen_urls.add(article["url"])
                    total += 1
                    if self.db.upsert_article(article):
                        inserted += 1
            except Exception as exc:
                logger.exception("Naver API search failed: %s", keyword)
                failures.append(f"{keyword}: {exc}")
        return {"total": total, "inserted": inserted, "failures": failures}

    def collect_fallback_outlets(
        self,
        keywords: list[str],
        start_dt: datetime,
        end_dt: datetime,
        exclude_keywords: list[str] | None = None,
    ) -> dict:
        if not self.available():
            return {"total": 0, "inserted": 0, "failures": ["네이버 API 키가 없습니다."]}
        seen_urls = set()
        total = 0
        inserted = 0
        failures = []
        monitor_keywords = NAVER_API_MONITOR_KEYWORDS
        for keyword in monitor_keywords:
            try:
                for item in self.search(keyword):
                    article = self.fallback_item_to_article(item)
                    if not article:
                        continue
                    if not contains_any_monitor_keyword(article["title"], monitor_keywords):
                        continue
                    haystack = f"{article['title']} {article.get('summary') or ''}"
                    published = article.pop("_published_dt", None)
                    if published and not (start_dt <= published <= end_dt):
                        continue
                    if any(exclude in haystack for exclude in exclude_keywords or []):
                        continue
                    if article["url"] in seen_urls:
                        continue
                    seen_urls.add(article["url"])
                    total += 1
                    if self.db.upsert_article(article):
                        inserted += 1
            except Exception as exc:
                logger.exception("Naver API fallback failed: %s", keyword)
                failures.append(f"{keyword}: {exc}")
        return {"total": total, "inserted": inserted, "failures": failures}

    def search(self, keyword: str):
        headers = {
            **DEFAULT_HEADERS,
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        for start in range(1, 101, 100):
            response = requests.get(
                self.URL,
                headers=headers,
                params={"query": keyword, "display": 100, "start": start, "sort": "date"},
                timeout=12,
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            if not items:
                break
            for item in items:
                yield item
            if len(items) < 100:
                break

    def item_to_article(self, item: dict):
        title = clean_api_text(item.get("title", ""))
        summary = clean_api_text(item.get("description", ""))
        link = item.get("link") or item.get("originallink")
        originallink = item.get("originallink") or link
        if not title or not link:
            return None
        published = parse_pubdate(item.get("pubDate"))
        source = guess_source(originallink, title, summary) or "온라인"
        date = published.strftime("%Y%m%d") if published else datetime.now().strftime("%Y%m%d")
        return {
            "date": date,
            "newspaper": source,
            "oid": "api",
            "paper_section": NAVER_SID_SECTIONS.get(extract_naver_oid_sid(link, originallink)[1], ""),
            "article_type": ARTICLE_TYPE_BY_SOURCE.get(source, "온라인"),
            "published_at": format_published_at(published),
            "title": title,
            "url": link,
            "summary": summary,
            "_published_dt": published,
        }

    def fallback_item_to_article(self, item: dict):
        title = clean_api_text(item.get("title", ""))
        summary = clean_api_text(item.get("description", ""))
        link = item.get("link") or ""
        originallink = item.get("originallink") or ""
        if not title or not link:
            return None
        oid, sid = extract_naver_oid_sid(link, originallink)
        if oid not in NAVER_API_FALLBACK_OUTLETS:
            return None
        section = NAVER_SID_SECTIONS.get(sid)
        if not section:
            return None
        published = parse_pubdate(item.get("pubDate"))
        date = published.strftime("%Y%m%d") if published else datetime.now().strftime("%Y%m%d")
        return {
            "date": date,
            "newspaper": NAVER_API_FALLBACK_OUTLETS[oid],
            "oid": oid,
            "paper_section": section,
            "article_type": ARTICLE_TYPE_BY_SOURCE.get(NAVER_API_FALLBACK_OUTLETS[oid], "온라인"),
            "published_at": format_published_at(published),
            "title": title,
            "url": link,
            "summary": summary,
            "_published_dt": published,
        }


def clean_api_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def contains_any_monitor_keyword(text: str, keywords: list[str]) -> bool:
    compact_text = normalize_match_text(text)
    for keyword in keywords:
        compact_keyword = normalize_match_text(keyword)
        if compact_keyword and compact_keyword in compact_text:
            return True
    return False


def normalize_match_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", text or "")


def parse_pubdate(value: str | None):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt.astimezone().replace(tzinfo=None)
    except Exception:
        return None


def format_published_at(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def guess_source(url: str, title: str, summary: str):
    host = urlparse(url or "").netloc.lower()
    text = f"{title} {summary}"
    for source, domains in ONLINE_NEWS_SOURCES.items():
        if source in text:
            return source
        if any(domain in host for domain in domains):
            return source
    return None


def extract_naver_oid_sid(*urls):
    oid = None
    sid = None
    for url in urls:
        if not url:
            continue
        match = re.search(r"/(?:mnews/)?article/(\d{3})/", url)
        if match:
            oid = match.group(1)
        query = parse_qs(urlparse(url).query)
        if query.get("sid"):
            sid = query["sid"][0]
    return oid, sid
