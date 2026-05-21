# NaverPaperCrawler Handoff

Last updated: 2026-05-20 KST

This repo now runs the legal morning report primarily through GitHub Actions, not a local Windows scheduler.

## Repository

- GitHub: `https://github.com/ggunglee/NaverPaperCrawler`
- Branch: `main`
- Latest verified operating commit before this doc-only handoff: `0314e58 Fix runtime cache workflow permissions`
- This handoff document itself is expected to be committed after that operating commit.

On another computer:

```powershell
git clone https://github.com/ggunglee/NaverPaperCrawler.git
cd NaverPaperCrawler
git pull origin main
```

If the repo already exists:

```powershell
cd path\to\NaverPaperCrawler
git pull origin main
```

## Operating Model

The production path is deterministic no-LLM reporting.

Do not assume any LLM is needed for the scheduled job. The scheduled job uses:

```powershell
python morning_report_task.py --date today --no-llm
```

The GitHub workflow adds the relevant mode and Telegram flags.

## GitHub Actions Schedule

### Morning Report

Workflow: `.github/workflows/morning-report.yml`

Schedules:

- `05:07 KST`: initial report
  - GitHub cron: `7 20 * * *`
  - Includes report-date paper articles.
  - Includes online articles from previous day 18:00 through report date 06:00.
  - Sends Telegram report.

- `06:55 KST`: online-only follow-up
  - GitHub cron: `55 21 * * *`
  - Checks online articles from 06:00 through 06:50.
  - Sends `[추가 보고]` only if new report-worthy items exist.
  - Sends a separate feedback guide message after the follow-up run.

Manual dry-run without Telegram:

```powershell
gh workflow run morning-report.yml --repo ggunglee/NaverPaperCrawler --ref main -f send_telegram=false -f mode=initial
gh workflow run morning-report.yml --repo ggunglee/NaverPaperCrawler --ref main -f send_telegram=false -f mode=update
```

Manual run with Telegram:

```powershell
gh workflow run morning-report.yml --repo ggunglee/NaverPaperCrawler --ref main -f send_telegram=true -f mode=initial
```

### Telegram Feedback

Workflow: `.github/workflows/telegram-feedback.yml`

Schedule:

- `11:00 KST`
  - GitHub cron: `0 2 * * *`
  - Collects pending feedback commands.
  - Sends `이민경 피드백 내놓으라고` if no feedback command has been collected for the day.

- `12:00 KST`
  - GitHub cron: `0 3 * * *`
  - Collects feedback commands from Telegram.
  - Stores collected messages in SQLite and JSON artifacts.

- `15:00 KST`
  - GitHub cron: `0 6 * * *`
  - Compares `/final` with the archived initial draft.
  - Sends a Telegram proposal asking how to apply the differences.

- `23:30 KST`
  - GitHub cron: `30 14 * * *`
  - Collects `/apply_feedback` answers.
  - Saves approved feedback memory to `feedback_rules.json`.

Manual run:

```powershell
gh workflow run telegram-feedback.yml --repo ggunglee/NaverPaperCrawler --ref main
```

## Required GitHub Secrets

Already expected:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Recommended for broader online discovery:

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

LLM secrets are not used. The reporting path is deterministic, and `--no-llm` is kept only as a compatibility flag for existing commands.

## Google Drive Backup Secrets

Runtime cache still uses GitHub Actions cache for day-to-day continuity. Google Drive is an extra zip backup after each morning/feedback run.

For a personal My Drive folder, use OAuth user credentials:

- `GOOGLE_DRIVE_FOLDER_ID`
  - Folder ID from a Drive folder URL.
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REFRESH_TOKEN`

For a Google Workspace Shared Drive, a service account can be used instead:

- `GOOGLE_DRIVE_FOLDER_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
  - Full Google Cloud service-account key JSON.
  - Put it in GitHub Secrets, not in a committed file.
  - Share the Shared Drive/folder with the service account email.
  - Service accounts cannot upload into normal personal My Drive folders because they have no storage quota.

Optional:

- `GOOGLE_DRIVE_DB_FILE_ID`
  - Use only if one existing DB file should be overwritten every run.

- `GOOGLE_DRIVE_QA_DOC_ID`
  - Use only if GitHub Actions should write directly to a Google Doc.

The backup workflow uploads `naver-runtime-backup-YYYYMMDDTHHMMSSZ.zip` and keeps the latest 14 backup zips.

Current QA log doc used manually through the Google Drive connector:

```text
https://docs.google.com/document/d/1k2BSnYBZfgat311DaHSxLml_mvXTvVeeHZ3CrjZ-BtQ
```

## Runtime Persistence

GitHub runners are ephemeral. The repo persists runtime state with Google Drive first and GitHub Actions cache as a secondary continuity layer:

- Google Drive backup: `naver-runtime-backup-YYYYMMDDTHHMMSSZ.zip`
- Restored at workflow startup with `backup_runtime_data.py --restore --skip-if-unconfigured`
- Uploaded at workflow end with `backup_runtime_data.py --skip-if-unconfigured --keep 14`
- Cache path: `~/.naver_news_crawler`
- Cache key prefix: `naver-news-runtime-`

The cache contains:

- `data/naver_paper_articles.db`
- article history
- `article_embeddings`
- `exclusive_claims`
- `article_analysis`
- `report_runs`
- `telegram_feedback.db`
- `config.json`
- `feedback_rules.json`
- `feedback_review_state.json`
- generated reports and feedback JSONs
- mode-specific report archives such as `YYYYMMDD_initial_morning_report.md`

Cleanup:

- `cleanup_runtime_data.py --days 30`
- Keeps only the latest 30 days of runtime DB rows and report/feedback files.
- Workflows also prune old runtime cache entries, keeping the 5 newest `naver-news-runtime-` caches.

Important: artifacts are for inspection, not persistence. Google Drive backup is the durable persistence layer; cache is a convenience fallback.

## Verified GitHub Runs

These runs were verified on GitHub before handoff:

- `25967639973`: morning-report initial dry-run
  - Success.
  - Runtime cache saved.
  - QA pass.

- `25967673574`: morning-report update dry-run
  - Success.
  - Restored runtime cache from `naver-news-runtime-25967639973`.
  - `online_inserted=0` after restoring cache, confirming duplicate persistence worked.
  - QA warn only because there were zero selected update items.

- `25967703425`: telegram-feedback dry-run
  - Success.
  - Restored runtime cache from `naver-news-runtime-25967673574`.
  - `updates_seen=0`, `feedback_collected=0`.
  - `telegram_feedback.db` existed and was pruned successfully.

One failed run was intentionally diagnosed and fixed:

- `25967597800`
  - Failed because the default GitHub token lacked Actions cache permissions and cleanup imported `report_generator` before dependencies were installed.
  - Fixed by adding workflow permissions and making cleanup dependency-light.

## Report Rules

Current important editorial rules:

- Lawtimes/법률신문 is now crawled directly from its latest/news pages because it is not covered by the existing RSS set and today's `/final` feedback included Lawtimes articles.
- Feedback from `/final` is confirmed to reach GitHub: the Telegram Feedback workflow opens `feedback-review` issues when the final report differs from the draft. On 2026-05-20 it opened issue #7 with 6 user-added and 23 user-removed items.
- The recurring 2026-05-20 misses were caused by weak recall terms (`배임죄`, `특례법`, `대법관`, `고법판사`, `국적판정불가`, `사증 발급`) and by Lawtimes not being collected. Those terms were added as monitor/desk-focus signals.
- Repeated unwanted items came from narrow same-event duplicate keys. The report now groups common update rewrites for `관저 이전 구속영장`, `김용현 비화폰 1심`, `타이어뱅크 탈세 구형`, and `윤석열 특검 소환/강제구인`.
- Foreign/overseas incident stories sourced from overseas media are silently excluded.
- 생활법률, 상담소, 사연자, radio advice style items are silently excluded.
- Exact same-event duplicates are silently excluded from Telegram.
- Same-event priority:
  - first: `단독`
  - second: `연합뉴스`
  - then other outlets
- Polling stories stay if the legal issue is substantive.
- Campaign diary items such as 선거사무소, 개소식, 출정식 are excluded.
- Political-rhetorical attack items are excluded when legal words are only rhetoric.
- Important straight legal stories should be included when uncertain rather than over-filtered.

Report format:

```text
[보고 기사]

※제목/매체 면수 또는 섹션
-보고체 요약.
URL

[보류/제외 기사]
...
```

Telegram splitting:

- Report and hold/exclusion sections are separate Telegram messages.
- Follow-up report is prefixed with `[추가 보고]` if it has items.
- Feedback guide is a separate Telegram message after the follow-up run.
- Multiple Telegram recipients are supported with `TELEGRAM_CHAT_IDS`; `TELEGRAM_GROUP_CHAT_ID` is sent first. Set repository variable `TELEGRAM_GROUP_ONLY=true` to send only to the group chat.

## Storage Note

Google Drive zip backup is still the best current persistence option for this repo because it preserves SQLite DBs, generated reports, feedback JSON, and rule state as one runtime snapshot. Google Docs or Sheets would be better for human review logs and editable rule tables, but not as the primary DB backup unless the app is redesigned to write structured rows instead of SQLite files.

## 2026-05-21 Selection Quality Branch

Branch: `codex/fix-morning-report-feedback-recall`

This branch changes morning report selection quality, not just keyword recall.

Implemented:

- Hard silent drops now run before desk-focus selection: obvious photo/video/board items, opinion columns, foreign DOJ/Trump/IRS stories, promo/education stories, and obvious local election snippets.
- Police-led filtering no longer drops prosecution-policy articles just because the title also contains police. Terms such as prosecution, supplementary investigation authority, investigation authority, prosecution reform, central investigation office, public prosecution office, and all-case transfer keep the article in the candidate pool.
- Special-counsel investigation stories are treated as high-confidence legal stories when the article has a real actor/action pair such as special counsel plus summons, search, indictment, arrest warrant, trial, rebellion charge, or Yoon Suk Yeol summons.
- Local filtering was expanded for province names and local election-board cases, while central institutions such as the Supreme Court, Constitutional Court, Prosecutor General's Office, Ministry of Justice, Seoul Central District Prosecutors' Office, Seoul Central District Court, and special counsel keep an item eligible.
- Representative article priority is now exclusive article, paper article, earliest publish time, outlet priority, then wire penalty. Yonhap and Newsis no longer outrank paper articles in same-event selection.
- Same-event dedupe now uses `normalized_event_key` plus fallback similarity/entity overlap, instead of relying only on hard-coded `article_event_key` entries.
- Silent drops and wire duplicates are no longer expanded in the markdown exclusion list. The report summarizes duplicate removals as a count.
- Non-exclusive Newsis items are capped more aggressively within a category unless they are exclusive or high-confidence special-counsel/prosecution/court stories.
- Diagnostic logs print per-outlet candidate, selected, and skipped counts as `selection_stats`.

Regression tests added in `tests/test_report_filters.py` cover:

- `[샷!]`, `[세계포럼]`, Trump/US DOJ, and promo/education exclusions.
- Supplementary-investigation authority stories that mention both prosecution and police.
- `2차 종합특검` / Yoon Suk Yeol rebellion-charge summons.
- Chungnam election-board county-election accusation exclusion.
- HD Hyundai Heavy Industries subcontract bargaining / Yellow Envelope Act dedupe.
- Kim Se-ui / Kim Soo-hyun defamation arrest-warrant and warrant-hearing dedupe.
- Exclusive over paper over wire representative priority.

Storage decision:

- Requirements [10] and [11] conflict. This branch keeps SQLite as the source of truth and does not replace the DB engine with Google Sheets.
- The safer next storage step is a Google Sheets mirror/export for operator review using columns such as date, published_at, source, article_type, paper_section, title, url, summary, body, crawl_source, body_fetch_status, normalized_event_key, main_actor, legal_relevance, locality, selection_status, exclusion_reason, duplicate_of, and selected_for_report.
- Full SQLite to Google Sheets migration should be a separate architecture branch because it changes persistence semantics, row update performance, dedupe keys, cache behavior, and GitHub Actions failure modes.
- Gemini should remain gray-zone only. Deterministic hard rules and duplicate rules should run first, and Gemini JSON decisions should be cached in `article_analysis` or a small side cache before any repeated use.

## Feedback Commands

Users can send feedback in Telegram with:

```text
/final
최종 완성본 전체

/exclude
제외해야 할 기사 제목 또는 제외 기준

/fix
원문: 어색한 문장
수정: 원하는 보고체 문장

/important
앞으로 꼭 넣어야 할 기사 유형

/apply_feedback
오후 3시 반영 확인 메시지에 대한 답변

/include_keyword
추가할 포함 키워드. 여러 개는 줄바꿈 또는 쉼표로 구분.

/exclude_keyword
추가할 배제 키워드. 여러 개는 줄바꿈 또는 쉼표로 구분.

/remove_include_keyword
삭제할 포함 키워드.

/remove_exclude_keyword
삭제할 배제 키워드.
```

The feedback workflow collects these commands. Keyword commands are applied to runtime `config.json` immediately. `/final` and `/fix` are collected for review. `/final` differences are proposed at 15:00 KST, and `/apply_feedback` answers are saved at 23:30 KST as runtime rules, not code changes.

## Local Validation Commands

Install:

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-report.txt
```

Compile check:

```powershell
.\venv\Scripts\python.exe -m py_compile morning_report_task.py report_generator.py report_qa.py telegram_feedback.py feedback_review.py backup_runtime_data.py cleanup_runtime_data.py
```

Generate without Telegram:

```powershell
.\venv\Scripts\python.exe morning_report_task.py --date today --mode initial --force --no-llm
.\venv\Scripts\python.exe morning_report_task.py --date today --mode update --no-llm
```

QA a generated report:

```powershell
.\venv\Scripts\python.exe report_qa.py "$env:USERPROFILE\.naver_news_crawler\reports\YYYYMMDD_morning_report.md"
```

Cleanup:

```powershell
.\venv\Scripts\python.exe cleanup_runtime_data.py --days 30
```

## Next Checks

1. Confirm the next real scheduled `05:07 KST` run starts early enough to deliver around the desired 06:00 window and has `paper_total > 0` when Naver paper pages are available.
2. Add `NAVER_CLIENT_ID` and `NAVER_CLIENT_SECRET` GitHub Secrets if broader online discovery is needed.
3. Decide whether GitHub Actions cache is enough, or whether Google Drive backup should be added with `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_DRIVE_FOLDER_ID`.
4. Implement feedback-to-rule review:
   - collect Telegram feedback,
   - summarize candidate rule changes,
   - optionally write a PR or update a rules file.

## Files Not To Commit

Do not commit:

- `.env`
- `venv/`
- `.codex/`
- `dist/`
- `build/`
- generated DB files
- generated reports
- release zip files
