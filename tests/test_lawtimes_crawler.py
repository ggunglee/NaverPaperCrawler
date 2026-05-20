from lawtimes_crawler import LawtimesCrawler


def test_lawtimes_listing_extracts_article_links():
    html = """
    <html><body>
      <a href="/news/articleView.html?idxno=220886">[판결][단독] 남편·형부 교제 여성 찾아가 젓갈 폭행</a>
      <a href="/news/articleView.html?idxno=220908">[단독] 특검 임의제출 우선 압수수색 영장 집행 논란</a>
      <a href="/news">뉴스</a>
    </body></html>
    """

    crawler = object.__new__(LawtimesCrawler)
    articles = crawler.parse_listing(html)

    assert [article["newspaper"] for article in articles] == ["법률신문", "법률신문"]
    assert articles[0]["url"] == "https://www.lawtimes.co.kr/news/articleView.html?idxno=220886"
    assert "젓갈 폭행" in articles[0]["title"]
