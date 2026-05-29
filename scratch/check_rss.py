import requests
import xml.etree.ElementTree as ET

urls = {
    "뉴시스 정치": "https://nwww.newsis.com/RSS/politics.xml",
    "뉴시스 사회": "https://nwww.newsis.com/RSS/society.xml",
    "연합뉴스 정치": "https://www.yna.co.kr/rss/politics.xml",
    "경향신문 정치": "https://www.khan.co.kr/rss/rssdata/politic_news.xml",
    "경향신문 사회": "https://www.khan.co.kr/rss/rssdata/society_news.xml",
    "한겨레 정치": "http://www.hani.co.kr/rss/politics/",
    "한겨레 사회": "http://www.hani.co.kr/rss/society/",
    "동아일보 정치": "http://rss.donga.com/politics.xml",
    "동아일보 사회": "http://rss.donga.com/national.xml",
    "매일경제 정치": "https://www.mk.co.kr/rss/30200030/",
    "매일경제 사회": "https://www.mk.co.kr/rss/50400012/",
    "로리더": "https://www.lawleader.co.kr/rss",
    "법률저널": "http://www.lec.co.kr/rss/allArticle.xml"
}

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

for name, url in urls.items():
    try:
        res = requests.get(url, headers=headers, timeout=5)
        print(f"[{name}] status: {res.status_code}, length: {len(res.content)}")
        root = ET.fromstring(res.content)
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        print(f"[{name}] parsed items: {len(items)}")
    except Exception as e:
        print(f"[{name}] Error: {e}")
