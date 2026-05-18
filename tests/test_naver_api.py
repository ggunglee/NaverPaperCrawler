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
