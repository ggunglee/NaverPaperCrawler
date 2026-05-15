import logging
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import (
    CRAWLER_SELECTORS,
    DEFAULT_HEADERS,
    LIST_PAGE_PARAM,
    LIST_URL,
    MAX_LIST_PAGES,
    NEWSPAPERS,
    REQUEST_RETRIES,
    REQUEST_SLEEP_SECONDS,
    REQUEST_TIMEOUT,
)
from database import Database


logger = logging.getLogger(__name__)


class NaverPaperCrawler:
    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _get(self, url: str):
        last_error = None
        for attempt in range(1, REQUEST_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or response.encoding
                return response
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Request failed (%s/%s): %s", attempt, REQUEST_RETRIES, url, exc)
                time.sleep(min(REQUEST_SLEEP_SECONDS * attempt, 3))
        logger.error("Request failed permanently: %s", url, exc_info=last_error)
        return None

    def crawl_date(self, yyyymmdd: str, fetch_first_page_bodies: bool = False) -> dict:
        total = 0
        inserted = 0
        body_fetched = 0
        pages = 0
        failures = []
        for newspaper, oid in NEWSPAPERS.items():
            try:
                result = self.crawl_newspaper_date(
                    newspaper,
                    oid,
                    yyyymmdd,
                    fetch_first_page_bodies=fetch_first_page_bodies,
                )
                total += result["total"]
                inserted += result["inserted"]
                body_fetched += result["body_fetched"]
                pages += result["pages"]
            except Exception as exc:
                logger.exception("Failed crawling %s %s", newspaper, yyyymmdd)
                failures.append(f"{newspaper}: {exc}")
            time.sleep(REQUEST_SLEEP_SECONDS)
        return {
            "total": total,
            "inserted": inserted,
            "body_fetched": body_fetched,
            "pages": pages,
            "failures": failures,
        }

    def crawl_newspaper_date(
        self,
        newspaper: str,
        oid: str,
        yyyymmdd: str,
        fetch_first_page_bodies: bool = False,
    ) -> dict:
        articles = []
        first_page_urls = []
        seen_article_urls = set()
        seen_page_signatures = set()
        pages = 0

        for page in range(1, MAX_LIST_PAGES + 1):
            url = LIST_URL.format(oid=oid, date=yyyymmdd)
            if page > 1:
                url += LIST_PAGE_PARAM.format(page=page)
            response = self._get(url)
            if response is None:
                break

            page_articles = self.parse_list_page(response.text, newspaper, oid, yyyymmdd)
            page_urls = [article["url"] for article in page_articles]
            if not page_urls:
                break

            signature = tuple(page_urls)
            if signature in seen_page_signatures:
                logger.info("%s %s page %s repeated previous page; stopping", newspaper, yyyymmdd, page)
                break
            seen_page_signatures.add(signature)
            pages += 1

            if page == 1:
                first_page_urls = page_urls
            for article in page_articles:
                if article["url"] in seen_article_urls:
                    continue
                seen_article_urls.add(article["url"])
                articles.append(article)
            time.sleep(REQUEST_SLEEP_SECONDS)

        inserted = 0
        for article in articles:
            if self.db.upsert_article(article):
                inserted += 1
        body_fetched = 0
        if fetch_first_page_bodies:
            for url in first_page_urls:
                row = self.db.get_article_by_url(url)
                if row and self.fetch_and_store_body(row["id"]):
                    body_fetched += 1
                time.sleep(REQUEST_SLEEP_SECONDS)
        logger.info(
            "%s %s: pages=%s total=%s inserted=%s body_fetched=%s",
            newspaper,
            yyyymmdd,
            pages,
            len(articles),
            inserted,
            body_fetched,
        )
        return {
            "total": len(articles),
            "inserted": inserted,
            "body_fetched": body_fetched,
            "pages": pages,
        }

    def parse_list_page(self, html: str, newspaper: str, oid: str, yyyymmdd: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        section_tags = soup.select(CRAWLER_SELECTORS["paper_section"])
        articles = []
        seen_urls = set()

        for section_tag in section_tags:
            paper_section = self._clean_text(section_tag.get_text(" ", strip=True))
            for sibling in section_tag.find_next_siblings():
                if sibling.name == "h4" and "paper_h4" in sibling.get("class", []):
                    break
                if sibling.name != "ul" or "type13" not in sibling.get("class", []):
                    continue
                for li in sibling.select("li"):
                    item = self._parse_list_item(li, newspaper, oid, yyyymmdd, paper_section)
                    if item and item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        articles.append(item)

        if not articles:
            for li in soup.select(CRAWLER_SELECTORS["article_list"]):
                item = self._parse_list_item(li, newspaper, oid, yyyymmdd, None)
                if item and item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    articles.append(item)
        return articles

    def _parse_list_item(self, li, newspaper: str, oid: str, yyyymmdd: str, paper_section: str | None):
        link = self._pick_article_link(li)
        if not link or not link.get("href"):
            return None

        url = urljoin("https://news.naver.com", link.get("href"))
        if "/mnews/article/" not in url and "/main/read.naver" not in url:
            return None
        title = self._clean_text(link.get_text(" ", strip=True))
        if not title:
            image = link.select_one("img[alt]")
            title = self._clean_text(image.get("alt", "")) if image else ""
        if not title:
            return None
        summary_tag = li.select_one(CRAWLER_SELECTORS["summary"])
        summary = self._clean_text(summary_tag.get_text(" ", strip=True)) if summary_tag else ""
        return {
            "date": yyyymmdd,
            "newspaper": newspaper,
            "oid": oid,
            "paper_section": paper_section,
            "article_type": "지면",
            "title": title,
            "url": url,
            "summary": summary,
        }

    def _pick_article_link(self, li):
        selectors = [
            CRAWLER_SELECTORS["article_link_preferred"],
            CRAWLER_SELECTORS["article_link_fallback"],
        ]
        for selector in selectors:
            links = li.select(selector)
            for link in links:
                if self._clean_text(link.get_text(" ", strip=True)):
                    return link
            if links:
                return links[0]
        return None

    def fetch_article_body(self, url: str) -> str:
        response = self._get(url)
        if response is None:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        body_tag = soup.select_one(CRAWLER_SELECTORS["body_primary"])
        if not body_tag:
            for selector in CRAWLER_SELECTORS["body_fallbacks"]:
                body_tag = soup.select_one(selector)
                if body_tag:
                    break
        if not body_tag:
            return ""
        for tag in body_tag.select(",".join(CRAWLER_SELECTORS["remove_from_body"])):
            tag.decompose()
        return self._normalize_body(body_tag.get_text("\n", strip=True))

    def fetch_and_store_body(self, article_id: int, force: bool = False) -> str:
        article = self.db.get_article(article_id)
        if not article:
            return ""
        if article["body"] and not force:
            return article["body"]
        body = self.fetch_article_body(article["url"])
        body = self._cleanup_article_body(body, article["title"], article["newspaper"])
        if body:
            self.db.update_body(article_id, body)
        return body

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _normalize_body(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
        compact = []
        blank = False
        for line in lines:
            if not line:
                if not blank:
                    compact.append("")
                blank = True
            else:
                compact.append(line)
                blank = False
        return "\n".join(compact).strip()

    @staticmethod
    def _cleanup_article_body(text: str, title: str = "", newspaper: str = "") -> str:
        title_norm = re.sub(r"[\W_]+", "", title or "")
        cleaned = []
        for raw_line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            line_norm = re.sub(r"[\W_]+", "", line)
            if title_norm and (line_norm == title_norm or (len(line_norm) < 80 and line_norm in title_norm)):
                continue
            if re.fullmatch(r"(정치|사회|경제|문화|국제|전국|전체)", line):
                continue
            if re.fullmatch(r"(등록|수정)?\s*:?\s*\d{4}\.\d{2}\.\d{2}\s+(오전|오후)\s+\d{1,2}:\d{2}", line):
                continue
            if re.fullmatch(r"\d{2}\.\d{2}\s+(오전|오후)\s+\d{1,2}:\d{2}", line):
                continue
            if re.fullmatch(r"[가-힣]{2,5}\s*(선임|인턴|수습)?기자", line):
                continue
            if re.match(r"^[가-힣]{2,5}\s*(선임|인턴|수습)?기자\s*[=:]", line):
                continue
            if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", line):
                continue
            noise_terms = [
                "인공지능이 자동으로",
                "세 줄 요약",
                "전체 내용을 이해하기",
                "무단전재",
                "재배포 금지",
                "저작권자",
                "제보는 카카오톡",
                "뉴스 제보",
                "사진=",
                "자료사진",
                "연합뉴스",
                "뉴스1",
                "뉴시스",
                "게티이미지",
                "본문의 이해를 돕기",
                "많이 본 뉴스",
                "구독",
                "좋아요",
                "댓글",
            ]
            if any(term in line for term in noise_terms):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()
