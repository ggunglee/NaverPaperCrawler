# 네이버 신문게재 기사 수집기

Windows 기자 업무용 네이버 뉴스 `신문게재 기사` 목록/본문 수집 프로그램입니다.

## 실행

```bat
pip install -r requirements.txt
python main.py
```

더블클릭용 EXE는 GUI가 열립니다.

```bat
build.bat
```

빌드 결과는 매번 새 타임스탬프 이름으로 생성됩니다. 기존 EXE가 실행 중이어도 덮어쓰지 않습니다.

```text
dist\NaverPaperCrawler_YYYYMMDD_HHMMSS\NaverPaperCrawler_YYYYMMDD_HHMMSS.exe
```

## 저장 위치

DB, 설정, 오류 로그는 실행 파일 폴더가 아니라 사용자 홈 안전 폴더에 저장됩니다.

```text
%USERPROFILE%\.naver_news_crawler\
%USERPROFILE%\.naver_news_crawler\data\naver_paper_articles.db
%USERPROFILE%\.naver_news_crawler\config.json
%USERPROFILE%\.naver_news_crawler\crawler_error.log
```

## CLI 자동 실행

작업 스케줄러용 목록 수집만 수행합니다. 본문은 GUI에서 선택 기사 또는 현재 검색 결과에 대해서만 수집합니다.

```bat
python main.py --crawl-today-with-prompt
python main.py --crawl-today --no-gui
python main.py --crawl-date 20260514 --no-gui
python main.py --crawl-rss --no-gui
python main.py --crawl-online --no-gui
```

EXE도 같은 옵션을 사용할 수 있습니다.

```bat
NaverPaperCrawler.exe --crawl-today-with-prompt
NaverPaperCrawler.exe --crawl-today --no-gui
NaverPaperCrawler.exe --crawl-date 20260514 --no-gui
NaverPaperCrawler.exe --crawl-rss --no-gui
NaverPaperCrawler.exe --crawl-online --no-gui
```

## Windows 작업 스케줄러 설정 예시

배포 폴더의 `install_scheduler.bat`를 실행하면 현재 EXE 또는 로컬 Python 환경 기준으로 아래 작업이 자동 등록됩니다.

- `NaverPaperCrawler_MorningReportTelegram`: 매일 오전 6시, 당일 지면 기사와 전날 오후 6시부터 당일 오전 6시까지의 온라인 기사를 수집해 아침보고를 텔레그램으로 발송

작업은 `예약된 시작 시간을 놓친 경우 가능한 빨리 작업 시작` 설정으로 등록됩니다. 제거하려면 배포 폴더의 `uninstall_scheduler.bat`를 실행합니다.

## 온라인 자동 수집

RSS가 정상 동작하는 뉴시스, 연합뉴스, SBS, JTBC, TV조선의 정치/사회 후보와, RSS가 제공되지 않는 뉴스1/KBS/MBC/채널A/노컷뉴스의 네이버 API 감시어 후보를 함께 수집하려면 작업 스케줄러에 별도 작업을 만듭니다.

- 트리거 시작: 매일 오전 5시 50분
- 반복 간격: 3시간
- 반복 기간: 1일
- 프로그램: `NaverPaperCrawler_YYYYMMDD_HHMMSS.exe`
- 인수: `--crawl-online --no-gui`

RSS가 XML로 응답하지 않거나 HTTP 오류가 나면 안전 폴더의 로그와 DB `rss_errors` 테이블에 매체, 섹션, URL, 오류 사유가 저장됩니다.

GUI는 시작 후 백그라운드로 온라인 후보를 확인합니다. 마지막 온라인 수집 후 3시간이 지나지 않았으면 다시 호출하지 않습니다. `키워드 기사 찾기`도 메인 화면을 멈추지 않고 백그라운드에서 온라인 후보를 먼저 갱신한 뒤 결과를 보여줍니다.

온라인 수집은 기간별 완료 기록을 DB에 저장합니다. 같은 기간을 다시 검색하면 이미 저장된 기사만 다시 조회하고 RSS/API를 새로 호출하지 않습니다.

네이버 API 보완 수집은 네이버 뉴스 URL의 언론사 OID와 `sid` 값으로 매체 및 정치/사회 섹션을 구분하며, API 키는 `.env` 또는 환경변수에서 읽습니다.

네이버 API 보완 수집은 잡기사 유입을 줄이기 위해 기본 감시 검색어 목록에 있는 표현이 기사 제목에 실제로 포함된 경우만 저장합니다.

## 주요 기능

- 날짜, 언론사, 게재면, 키워드, 카테고리 복합 검색
- 기사 유형 필터: 지면, 방송, 통신, 온라인
- 키워드 기사 찾기 결과에서 유형 필터로 지면/방송/통신/온라인만 다시 보기
- 검색 범위: 제목 / 제목+요약 / 제목+요약+본문
- 기사 선택 후 본문 수집 및 DB 캐시
- 현재 검색 결과 본문 일괄 수집
- 목록 수집 완료 후 키워드 기사 본문 수집 여부 확인
- 환경 설정 또는 수집 완료 팝업에서 본문 수집 키워드 저장/수정
- CSV 내보내기
- 선택 기사 TXT 저장
- 기존 카테고리 드롭다운 및 새 카테고리 입력
- 다중 선택 기사 카테고리 일괄 부여
- 환경 설정 탭에서 Gemini API Key 저장
