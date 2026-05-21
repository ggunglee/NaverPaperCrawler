import json
import logging
import os
import re
import sys
from pathlib import Path


APP_NAME = "NaverPaperCrawler"
SAFE_DIR = Path(os.path.expanduser("~")) / ".naver_news_crawler"
DATA_DIR = SAFE_DIR / "data"
DB_PATH = DATA_DIR / "naver_paper_articles.db"
CONFIG_PATH = SAFE_DIR / "config.json"
LOG_PATH = SAFE_DIR / "crawler_error.log"


NEWSPAPERS = {
    "경향신문": "032",
    "국민일보": "005",
    "동아일보": "020",
    "문화일보": "021",
    "서울신문": "081",
    "세계일보": "022",
    "중앙일보": "025",
    "한겨레": "028",
    "한국일보": "469",
}


LIST_URL = (
    "https://news.naver.com/main/list.naver"
    "?mode=LPOD&mid=sec&oid={oid}&listType=paper&date={date}"
)
LIST_PAGE_PARAM = "&page={page}"
MAX_LIST_PAGES = 20


CRAWLER_SELECTORS = {
    "paper_section": "h4.paper_h4",
    "article_list": "ul.type13 li",
    "article_link_preferred": 'a[href*="/mnews/article/"]',
    "article_link_fallback": "a[href]",
    "summary": "span.lede",
    "body_primary": "article#dic_area",
    "body_fallbacks": [
        "#dic_area",
        "div#articeBody",
        "div#articleBodyContents",
        "div.newsct_article",
        "article",
    ],
    "remove_from_body": ["script", "style", "iframe", "noscript", "button", "em.img_desc", ".img_desc"],
}


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 12
REQUEST_RETRIES = 3
REQUEST_SLEEP_SECONDS = 0.6
DEFAULT_BODY_KEYWORDS = [
    "대검찰청",
    "대검",
    "대법원",
    "대법",
    "헌법재판소",
    "헌재",
    "헌법불합치",
    "헌법",
    "개헌",
    "위헌",
    "서울 검찰",
    "서울 법원",
    "서울중앙지검",
    "서울고검",
    "법무부",
    "서울고등법원",
    "공수처",
    "특검",
    "종합특검",
    "특검팀",
    "합수본",
    "합동수사본부",
    "신천지",
    "계엄",
    "비상계엄",
    "관저",
    "관저 이전",
    "양형",
    "양형위원회",
    "검찰개혁",
    "검찰 개혁",
    "단독 검찰",
    "단독 법원",
    "단독 특검",
    "행정법원",
    "회생법원",
    "가정법원",
    "서울중앙지법",
    "서울고법",
    "변협",
    "대한변호사협회",
    "서울지방변호사회",
    "대법관",
    "고법판사",
    "고법 판사",
    "법관 인사",
    "배임죄",
    "특례법",
    "재산관리범죄",
    "무국적자",
    "국적판정불가",
    "탈북",
    "탈북인",
    "사증 발급",
    "비자 발급",
    "법률신문",
    "벌금형",
    "공동상해",
    "보완수사권",
    "하도급법",
    "부당수취",
    "성과장려금",
    "정보제공료",
]
DEFAULT_EXCLUDE_KEYWORDS = []
PROJECT_DIR = Path(__file__).resolve().parent


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_DIR


ENV_PATHS = [
    Path.cwd() / ".env",
    runtime_dir() / ".env",
    PROJECT_DIR / ".env",
]

ONLINE_NEWS_SOURCES = {
    "뉴시스": ["newsis.com"],
    "뉴스1": ["news1.kr"],
    "연합뉴스": ["yna.co.kr"],
    "경향신문": ["khan.co.kr"],
    "국민일보": ["kmib.co.kr"],
    "동아일보": ["donga.com"],
    "문화일보": ["munhwa.com"],
    "서울신문": ["seoul.co.kr"],
    "세계일보": ["segye.com"],
    "중앙일보": ["joongang.co.kr"],
    "한겨레": ["hani.co.kr"],
    "한국일보": ["hankookilbo.com"],
    "KBS": ["kbs.co.kr"],
    "SBS": ["sbs.co.kr"],
    "MBC": ["imbc.com", "mbc.co.kr"],
    "JTBC": ["jtbc.co.kr"],
    "채널A": ["ichannela.com", "channel-a.co.kr"],
    "TV조선": ["tvchosun.com"],
    "노컷뉴스": ["nocutnews.co.kr"],
    "법률신문": ["lawtimes.co.kr"],
    "온라인": [],
}

RSS_FEEDS = [
    {"source": "뉴시스", "section": "정치", "url": "https://nwww.newsis.com/RSS/politics.xml"},
    {"source": "뉴시스", "section": "사회", "url": "https://nwww.newsis.com/RSS/society.xml"},
    {"source": "연합뉴스", "section": "정치", "url": "https://www.yna.co.kr/rss/politics.xml"},
    {"source": "연합뉴스", "section": "사회", "url": "https://www.yna.co.kr/rss/society.xml"},
    {"source": "SBS", "section": "정치", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSSREADER"},
    {"source": "SBS", "section": "사회", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03&plink=RSSREADER"},
    {"source": "JTBC", "section": "정치", "url": "https://fs.jtbc.co.kr/RSS/politics.xml"},
    {"source": "JTBC", "section": "사회", "url": "https://fs.jtbc.co.kr/RSS/society.xml"},
    {"source": "TV조선", "section": "정치", "url": "https://news.tvchosun.com/site/data/rss/politics.xml"},
    {"source": "TV조선", "section": "사회", "url": "https://news.tvchosun.com/site/data/rss/national.xml"},
    {"source": "노컷뉴스", "section": "사회", "url": "https://rss.nocutnews.co.kr/category/society.xml"},
]

ARTICLE_TYPE_BY_SOURCE = {
    "뉴시스": "통신",
    "뉴스1": "통신",
    "연합뉴스": "통신",
    "KBS": "방송",
    "SBS": "방송",
    "MBC": "방송",
    "JTBC": "방송",
    "채널A": "방송",
    "TV조선": "방송",
    "노컷뉴스": "온라인",
    "법률신문": "온라인",
    "온라인": "온라인",
}

EXCLUDED_ONLINE_SOURCES = {"뉴시스"}
BROADCAST_SOURCES = {"KBS", "SBS", "MBC", "JTBC", "채널A", "TV조선"}
ONLINE_EXCLUSIVE_EXEMPT_SOURCES = {"연합뉴스"}


def is_exclusive_title(title: str | None) -> bool:
    return "단독" in (title or "")


def should_collect_online_article(source: str | None, article_type: str | None, title: str | None) -> bool:
    source = source or ""
    article_type = article_type or ""
    if source in EXCLUDED_ONLINE_SOURCES:
        return False
    if article_type == "지면":
        return True
    if source in ONLINE_EXCLUSIVE_EXEMPT_SOURCES:
        return True
    if article_type == "방송" or source in BROADCAST_SOURCES:
        return is_exclusive_title(title)
    return is_exclusive_title(title)


NAVER_API_FALLBACK_OUTLETS = {
    "025": "중앙일보",
    "421": "뉴스1",
    "056": "KBS",
    "214": "MBC",
    "449": "채널A",
    "079": "노컷뉴스",
}

NAVER_API_MONITOR_KEYWORDS = DEFAULT_BODY_KEYWORDS

NAVER_SID_SECTIONS = {
    "100": "정치",
    "102": "사회",
    "162": "정치",
}


def ensure_app_dirs() -> None:
    SAFE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    ensure_app_dirs()
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )


def load_config() -> dict:
    ensure_app_dirs()
    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logging.exception("Failed to load config")
        return {}


def save_config(values: dict) -> None:
    ensure_app_dirs()
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(values, f, ensure_ascii=False, indent=2)


def update_config(values: dict) -> dict:
    config = load_config()
    config.update(values)
    save_config(config)
    return config


def load_body_keywords() -> list[str]:
    keywords = load_config().get("body_keywords", DEFAULT_BODY_KEYWORDS)
    if isinstance(keywords, str):
        keywords = [keywords]
    return normalize_keywords(keywords)


def save_body_keywords(keywords: list[str]) -> list[str]:
    normalized = normalize_keywords(keywords)
    update_config({"body_keywords": normalized})
    return normalized


def load_exclude_keywords() -> list[str]:
    keywords = load_config().get("exclude_keywords", DEFAULT_EXCLUDE_KEYWORDS)
    if isinstance(keywords, str):
        keywords = [keywords]
    return normalize_keywords(keywords)


def save_exclude_keywords(keywords: list[str]) -> list[str]:
    normalized = normalize_keywords(keywords)
    update_config({"exclude_keywords": normalized})
    return normalized


def normalize_keywords(keywords) -> list[str]:
    seen = set()
    normalized = []
    for keyword in keywords or []:
        text = str(keyword).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def load_env_values() -> dict:
    values = {}
    env_path = next((path for path in ENV_PATHS if path.exists()), None)
    if not env_path:
        return values
    try:
        text = env_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = env_path.read_text(encoding="cp949", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = re.sub(r"[^A-Z0-9_]+", "_", key.strip().upper()).strip("_")
        values[key] = value.strip().strip('"').strip("'")
    return values


def split_env_list(value):
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,;\n]+", str(value)) if item.strip()]


def telegram_recipient_ids(env=None):
    env = env or load_env_values()

    def read(key):
        return env.get(key) or os.environ.get(key)

    group_id = read("TELEGRAM_GROUP_CHAT_ID")
    group_only = str(read("TELEGRAM_GROUP_ONLY") or "").strip().lower() in {"1", "true", "yes", "on"}
    if group_only and group_id:
        return [group_id]

    recipients = []
    for chat_id in [group_id, *split_env_list(read("TELEGRAM_CHAT_IDS")), read("TELEGRAM_CHAT_ID")]:
        if chat_id and chat_id not in recipients:
            recipients.append(chat_id)
    return recipients


def get_naver_api_credentials() -> tuple[str | None, str | None]:
    env = load_env_values()
    client_id = (
        env.get("NAVER_CLIENT_ID")
        or env.get("NAVER_API_CLIENT_ID")
        or env.get("CLIENT_ID")
    )
    client_secret = (
        env.get("NAVER_CLIENT_SECRET")
        or env.get("NAVER_API_CLIENT_SECRET")
        or env.get("CLIENT_SECRET")
    )
    return client_id, client_secret
