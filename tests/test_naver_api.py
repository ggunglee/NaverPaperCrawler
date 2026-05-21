from datetime import datetime

from naver_api import NaverNewsApiClient


class FakeDb:
    def __init__(self):
        self.articles = []

    def upsert_article(self, article):
        self.articles.append(article)
        return True


def test_fallback_collection_uses_runtime_keywords(monkeypatch):
    client = object.__new__(NaverNewsApiClient)
    client.client_id = "id"
    client.client_secret = "secret"
    client.db = FakeDb()
    searched = []

    def fake_search(keyword):
        searched.append(keyword)
        return [
            {
                "title": f"{keyword} 수사 본격화",
                "description": "노컷뉴스 보도",
                "link": "https://n.news.naver.com/mnews/article/079/1?sid=102",
                "originallink": "https://www.nocutnews.co.kr/news/1",
                "pubDate": "Mon, 18 May 2026 05:30:00 +0900",
            }
        ]

    monkeypatch.setattr(client, "search", fake_search)

    result = client.collect_fallback_outlets(
        ["특검"],
        datetime(2026, 5, 18, 5, 0, 0),
        datetime(2026, 5, 18, 6, 0, 0),
    )

    assert searched == ["특검"]
    assert result["inserted"] == 1


def test_fallback_collection_can_capture_joongang_exclusive(monkeypatch):
    client = object.__new__(NaverNewsApiClient)
    client.client_id = "id"
    client.client_secret = "secret"
    client.db = FakeDb()

    def fake_search(keyword):
        return [
            {
                "title": "[단독] 김건희, 관저 변경 관여 의혹…21그램·윤한홍 답사 동행",
                "description": "2차 종합특검팀이 관저 후보지 사전 답사 정황을 확인했다.",
                "link": "https://n.news.naver.com/mnews/article/025/25430143?sid=102",
                "originallink": "https://www.joongang.co.kr/article/25430143",
                "pubDate": "Thu, 21 May 2026 05:30:00 +0900",
            }
        ]

    monkeypatch.setattr(client, "search", fake_search)

    result = client.collect_fallback_outlets(
        ["특검"],
        datetime(2026, 5, 21, 5, 0, 0),
        datetime(2026, 5, 21, 6, 0, 0),
    )

    assert result["inserted"] == 1
    assert client.db.articles[0]["newspaper"] == "중앙일보"


def test_collection_drops_newsis_and_nonexclusive_broadcast(monkeypatch):
    client = object.__new__(NaverNewsApiClient)
    client.client_id = "id"
    client.client_secret = "secret"
    client.db = FakeDb()

    def fake_search(keyword):
        return [
            {
                "title": "특검 수사 상황 브리핑",
                "description": "TV조선 보도",
                "link": "https://n.news.naver.com/mnews/article/448/1?sid=102",
                "originallink": "https://news.tvchosun.com/site/data/html_dir/2026/05/21/1.html",
                "pubDate": "Thu, 21 May 2026 05:30:00 +0900",
            },
            {
                "title": "[단독] 특검 수사 상황",
                "description": "뉴시스 보도",
                "link": "https://www.newsis.com/view/NISX20260521_1",
                "originallink": "https://www.newsis.com/view/NISX20260521_1",
                "pubDate": "Thu, 21 May 2026 05:31:00 +0900",
            },
        ]

    monkeypatch.setattr(client, "search", fake_search)

    result = client.collect_keywords(
        ["특검"],
        datetime(2026, 5, 21, 5, 0, 0),
        datetime(2026, 5, 21, 6, 0, 0),
    )

    assert result["inserted"] == 0
