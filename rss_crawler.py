import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

from config import ARTICLE_TYPE_BY_SOURCE, DEFAULT_HEADERS, REQUEST_TIMEOUT, RSS_FEEDS, should_collect_online_article
from database import Database


logger = logging.getLogger(__name__)


class RssCrawler:
    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def crawl_all(self) -> dict:
        total = 0
        inserted = 0
        errors = []
        for feed in RSS_FEEDS:
            result = self.crawl_feed(feed)
            total += result["total"]
            inserted += result["inserted"]
            errors.extend(result["errors"])
        return {"total": total, "inserted": inserted, "errors": errors}

    def crawl_feed(self, feed: dict) -> dict:
        source = feed["source"]
        section = feed["section"]
        url = feed["url"]
        try:
            response = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
            content_type = response.headers.get("content-type", "")
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            content = response.content.strip()
            if not (content.startswith(b"<?xml") or b"<rss" in content[:500].lower() or b"<feed" in content[:500].lower()):
                raise ValueError(f"RSS XML이 아닌 응답입니다. content-type={content_type}")
            articles = self.parse_feed(content, source, section)
            inserted = 0
            for article in articles:
                if not should_collect_online_article(article["newspaper"], article["article_type"], article["title"]):
                    continue
                if self.db.upsert_article(article):
                    inserted += 1
            return {"total": len(articles), "inserted": inserted, "errors": []}
        except Exception as exc:
            message = f"{source} {section} RSS 실패: {url} ({exc})"
            logger.warning(message)
            self.db.insert_rss_error(source, section, url, str(exc))
            return {"total": 0, "inserted": 0, "errors": [message]}

    def parse_feed(self, content: bytes, source: str, section: str) -> list[dict]:
        root = ET.fromstring(content)
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        articles = []
        seen = set()
        for item in items:
            title = clean_text(find_text(item, ["title"]))
            link = find_link(item)
            summary = clean_text(find_text(item, ["description", "summary"]))
            published = parse_date(find_text(item, ["pubDate", "published", "updated"]))
            if not title or not link or link in seen:
                continue
            seen.add(link)
            articles.append({
                "date": published.strftime("%Y%m%d") if published else datetime.now().strftime("%Y%m%d"),
                "newspaper": source,
                "oid": "rss",
                "paper_section": section,
                "article_type": ARTICLE_TYPE_BY_SOURCE.get(source, "온라인"),
                "published_at": format_published_at(published),
                "title": title,
                "url": link,
                "summary": summary,
            })
        return articles


def find_text(item, names):
    for name in names:
        node = item.find(name)
        if node is None:
            node = item.find(f"{{http://www.w3.org/2005/Atom}}{name}")
        if node is not None and node.text:
            return node.text
    return ""


def find_link(item):
    text = find_text(item, ["link"])
    if text:
        return text.strip()
    atom_link = item.find("{http://www.w3.org/2005/Atom}link")
    if atom_link is not None:
        return atom_link.attrib.get("href", "").strip()
    return ""


def clean_text(value):
    value = re.sub(r"<[^>]+>", "", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value):
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone().replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except Exception:
            continue
    return None


def format_published_at(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None
