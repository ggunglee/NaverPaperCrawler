import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = os.path.expanduser('~') + '/.naver_news_crawler/data/naver_paper_articles.db'
if not os.path.exists(db_path):
    print("Database file not found:", db_path)
    sys.exit(1)

from database import Database, is_excluded_by_word_match
db = Database()

# We will test two scenarios:
# 1. An article with "사전투표" or "투표율" but no exact "투표" (should NOT be excluded by "투표" keyword)
# 2. An article with exact "투표" or "투표가/투표를" (should BE excluded by "투표" keyword)

# Let's mock a few article rows to test the filter directly
test_cases = [
    {
        "title": "사전투표가 시작되었습니다.",  # Exact '투표' is NOT present as a standalone word (it's "사전투표가")
        "summary": "전국 투표소 정보 안내.", # Exact '투표소' is present
        "body": "이번 선거 투표율은 대략 60% 예상됩니다." # Exact '투표율' is present
    },
    {
        "title": "법원, 가처분 기각",
        "summary": "찬반투표 결과 정당화",
        "body": "이에 대해 조합원들이 찬성 투표를 던졌습니다." # Exact '투표' with particle '를' is present
    },
    {
        "title": "선거일 일정",
        "summary": "투표하고 놀러갑시다.", # Exact '투표하고' is present (verb, not exact '투표' word)
        "body": "모두 투표에 동참합시다." # Exact '투표에' is present
    }
]

print("--- REGEX EXCLUDE FILTER TESTING ---")
for idx, case in enumerate(test_cases, start=1):
    excluded = is_excluded_by_word_match(case, ["투표"])
    print(f"Test case #{idx}:")
    print("  Title:", case["title"])
    print("  Summary:", case["summary"])
    print("  Body:", case["body"])
    print("  Excluded by ['투표']:", excluded)
    print()
