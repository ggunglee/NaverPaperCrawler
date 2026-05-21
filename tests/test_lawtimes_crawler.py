from lawtimes_crawler import LawtimesCrawler, parse_article_detail


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


def test_lawtimes_detail_extracts_body_not_repeated_title():
    html = """
    <html><head>
      <meta property="og:title" content="[판결][단독] 남편·형부 교제 여성 찾아가 젓갈 폭행 벌금형">
    </head><body>
      <h1>[판결][단독] 남편·형부 교제 여성 찾아가 젓갈 폭행 벌금형</h1>
      <div id="article-view-content-div">
        서울중앙지법 형사12단독은 공동상해 혐의로 기소된 피고인들에게 벌금형을 선고했다.
        재판부는 항의 수준을 현저히 초과했다고 판단했다.
      </div>
    </body></html>
    """

    detail = parse_article_detail(html)

    assert "[단독]" in detail["title"]
    assert "서울중앙지법" in detail["body"]
    assert detail["summary"] != detail["title"]
