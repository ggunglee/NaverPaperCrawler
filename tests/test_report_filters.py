import report_generator as rg


def row(title, summary="", body="", section="사회", article_type="지면", paper_section=None):
    return {
        "title": title,
        "summary": summary,
        "body": body,
        "paper_section": section if paper_section is None else paper_section,
        "article_type": article_type,
        "newspaper": "테스트신문",
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


def test_user_feedback_recall_topics_are_included():
    articles = [
        row("당정, 기업 옥죄던 배임죄 폐지하고 특례법 만든다", summary="법무부가 재산관리범죄 특례법 초안을 마련했다.", section="정치"),
        row("법무부 '유령 탈북인' 연구용역도 맡겼지만…여전히 방치", summary="국적판정불가자와 탈북 화교의 관리 체계가 문제로 지적됐다.", article_type="온라인"),
        row("대법관 못 달면 퇴직까지 재판만...'업무 과중' 시달리는 고법판사", summary="법관 인사 구조 개편 필요성이 제기됐다.", section="10면"),
        row('유승준 세번째 비자 소송 항소심 7월 시작…1심 "발급거부 위법"', summary="서울고법이 사증 발급 거부 취소 소송 항소심을 진행한다.", article_type="통신"),
        row("남편·형부 교제 여성 찾아가 ‘젓갈 폭행’ 가한 세 자매, 벌금형", summary="서울중앙지법이 공동상해 혐의에 벌금형을 선고했다.", article_type="온라인"),
    ]

    for article in articles:
        assert rg.matches_monitor_keywords(article) is True
        assert rg.is_desk_focus_article(article) is True


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


def test_low_value_legal_mentions_are_filtered_before_report_selection():
    for article in [
        row("[게시판] 서울남부출입국사무소, 세계인의 날 기념행사 개최", summary="출입국 행사 안내.", article_type="통신"),
        row("[기억할 오늘] 미 연방대법원의 부정- 자기부정의 역사", summary="역사 칼럼.", section="26면"),
        row("미스코리아眞 출신 김연주, 고려대 통계학과 교수 임용", summary="임용 소식.", article_type="통신"),
        row("'SG발 주가조작' 라덕연, 오늘 대법원 선고…2심 징역 8년", summary="선고 일정 안내.", article_type="통신"),
        row("종합특검, '관저 이전 의혹' 김대기·윤재순 구속 영장 청구", summary="특검 수사 상황.", article_type="통신"),
        row("공소취소특검법은 ‘입법 내란’이다[김세동의 시론]", summary="시론.", section="30면"),
        row("대법 \"'환매 중단' 옵티머스 펀드 판 NH증권, 오뚜기에 75억 배상\"", summary="금융 민사 판결.", article_type="통신"),
        row("권순형(22기) 서울고법 부장판사 부친상", summary="부고.", article_type="온라인"),
        row("군인의 유족이 가지는 군인사망급여금 청구권의 소멸시효", summary="판례평석.", article_type="온라인"),
        row("삼전 노조 영업이익 15% 성과급 요구, 이사회 통과시 배임 논란", summary="노사 이슈.", article_type="온라인"),
    ]:
        assert rg.is_low_value_legal_mention(article) is True


def test_procedural_special_counsel_story_survives_political_churn_filter():
    article = row(
        "특검 “임의제출 우선” 압수수색 영장 집행 논란",
        summary="법원이 영장 조건으로 임의제출 형식을 우선하라고 명시했다.",
        article_type="온라인",
    )

    assert rg.is_low_value_legal_mention(article) is False


def test_special_counsel_martial_law_and_residence_items_are_monitored():
    residence = row(
        '윤석열 대통령실 "관저 이전비, 행안부가 다 내라" 압박 정황',
        summary="2차 종합특검팀이 대통령실의 관저 이전 추가비용 압박 정황을 파악했다.",
        section="10면",
    )
    martial_law = row(
        '특검, 김흥준 전 육본 정책실장 입건...계엄 가담 의혹',
        summary="종합특검팀이 비상계엄 해제 요구결의안 가결 이후 대책 논의 의혹을 수사한다.",
        article_type="통신",
    )
    constitutional = row(
        "'위헌-헌법불합치' 결정에도 개정 안된 법률 27건",
        summary="헌법재판소 결정 이후 후속 법률안이 발의되지 않은 법률도 있다.",
        section="10면",
    )

    for article in [residence, martial_law, constitutional]:
        assert rg.matches_monitor_keywords(article) is True
        assert rg.is_desk_focus_article(article) is True


def test_local_non_seoul_legal_items_are_excluded_without_national_anchor():
    local = row(
        "춘천지법, 지역 조합장 선거법 위반 벌금형",
        summary="강원 지역 사건의 1심 선고 내용.",
        section="전국",
    )
    national = row(
        "대법, 춘천지법 선고 뒤집고 파기환송",
        summary="대법원이 법리 오해를 이유로 사건을 돌려보냈다.",
        section="전국",
    )

    assert rg.is_local_non_seoul_article(local) is True
    assert rg.is_local_non_seoul_article(national) is False


def test_regional_court_subjects_are_excluded_even_outside_national_section():
    chuncheon = row(
        "춘천지방법원, 음주운전 사고 운전자 징역형 선고",
        summary="춘천지법이 지역 사건 1심 판결을 내렸다.",
        section="사회",
    )
    jeonju = row(
        "전주지법, 보이스피싱 조직원 실형",
        summary="전주지방법원이 피고인에게 실형을 선고했다.",
        section="사회",
    )
    supreme = row(
        "대법, 전주지법 판결 파기환송",
        summary="대법원이 원심 판단을 뒤집었다.",
        section="사회",
    )

    assert rg.is_local_non_seoul_article(chuncheon) is True
    assert rg.is_local_non_seoul_article(jeonju) is True
    assert rg.is_local_non_seoul_article(supreme) is False


def test_same_event_prefers_paper_over_newsis_when_not_exclusive_or_yonhap():
    paper = row(
        "특검, 김흥준 전 육본 정책실장 입건...계엄 가담 의혹",
        summary="종합특검팀이 같은 사안을 수사한다.",
        article_type="지면",
    )
    newsis = row(
        "특검, 김흥준 전 육본 정책실장 입건...계엄 가담 의혹",
        summary="종합특검팀이 같은 사안을 수사한다.",
        article_type="통신",
    )
    paper.update({"id": 1, "newspaper": "동아일보", "published_at": None, "created_at": "2026-05-18T01:00:00"})
    newsis.update({"id": 2, "newspaper": "뉴시스", "published_at": "2026-05-18 05:00:00", "created_at": "2026-05-18T05:00:00"})

    assert rg.report_article_priority(paper) < rg.report_article_priority(newsis)


def test_same_event_duplicates_cover_common_update_wire_rewrites():
    rows = []
    for index, title in enumerate(
        [
            "종합특검, '관저 이전 의혹' 김대기·윤재순·김오진 구속 영장 청구",
            "'관저 이전 의혹' 김대기·윤재순·김오진, 22일 구속 심사",
            "'비화폰 전달·계엄 증거인멸 지시' 김용현 1심 징역 3년",
            "'비화폰 지급' 김용현, 1심 징역 3년…法 \"노상원과 상황 공유 목적\"",
        ],
        start=1,
    ):
        item = row(title, summary="서울중앙지법과 특검 관련 내용.", article_type="통신")
        item.update({"id": index, "newspaper": "뉴시스", "published_at": f"2026-05-20 06:0{index}:00", "created_at": ""})
        rows.append(item)

    kept, skipped = rg.dedupe_event_rows(rows)

    assert len(kept) == 2
    assert len(skipped) == 2
