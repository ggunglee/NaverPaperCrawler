import report_generator as rg


def row(title, summary="", body="", section="사회", article_type="지면", paper_section=None):
    return {
        "title": title,
        "summary": summary,
        "body": body,
        "paper_section": section if paper_section is None else paper_section,
        "article_type": article_type,
    }


def test_routine_election_politics_is_excluded_even_with_incidental_legal_words():
    interview = row(
        '[인터뷰]조국 "김용남, 민주당·진영 가치에 안 맞아…제가 민주진보 진영 비전에 충실한 사람"',
        summary="6·3 경기 평택을 국회의원 재선거에 출마한 조국 조국혁신당 후보 인터뷰.",
        body="검경 수사권 조정 협의체에 들어갔고 검찰개혁 마무리를 말했다.",
        section="정치",
        article_type="통신",
    )
    race = row(
        '정청래 "김용남, 민주당 아들", 조국 "검찰개혁 적임"... 범여권 평택을서 \'적통 경쟁\'',
        summary="재선거 후보들이 선거사무소에서 지지를 호소했다.",
        section="5면",
    )
    policy = row(
        '김경수·조문관 "양산, 부울경 메가시티 중추도시 만들 것"',
        summary="도시 개발 공약과 보육·돌봄 지원체계를 제시했다.",
        body="지역 회생이라는 표현이 한 차례 등장한다.",
        section="정치",
        article_type="통신",
    )

    assert rg.is_desk_focus_article(interview) is False
    assert rg.is_desk_focus_article(race) is False
    assert rg.is_desk_focus_article(policy) is False


def test_court_ruling_and_sentencing_policy_are_included():
    lime = row(
        '‘라임펀드’ 투자했다 손실…대법 “우리은행, 고의로 속인 것 아냐”',
        summary="대법원이 투자자 손해배상 청구 소송에서 원심 일부를 파기환송했다.",
        section="A11면",
    )
    dui = row(
        "음주운전으로 사망했는데 징역 5년?...'솜방망이' 처벌 기준 다시 손 본다",
        summary="대법원 양형위원회가 교통범죄 양형기준을 주제로 심포지엄을 연다.",
        section="11면",
    )

    assert rg.is_desk_focus_article(lime) is True
    assert rg.is_desk_focus_article(dui) is True


def test_mandatory_institution_led_items_are_always_included():
    institutions = [
        "서울중앙지검",
        "서울중앙지법",
        "대법원",
        "헌법재판소",
        "법무부",
        "서울고등법원",
    ]

    for institution in institutions:
        article = row(
            f"{institution}, 새 기준 발표",
            summary="기관 발표 내용을 전했다.",
            section="B12면",
        )
        assert rg.matches_monitor_keywords(article) is True
        assert rg.is_desk_focus_article(article) is True


def test_schedule_items_stay_excluded_even_when_listing_mandatory_institutions():
    article = row(
        "[오늘의 주요일정]법조(5월18일 월요일)",
        summary="서울중앙지법 형사22부와 서울고법 재판 일정.",
        article_type="통신",
    )

    assert rg.matches_monitor_keywords(article) is True
    assert rg.is_desk_focus_article(article) is False
