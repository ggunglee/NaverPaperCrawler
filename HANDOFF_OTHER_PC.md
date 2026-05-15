# Other PC Handoff

This repository contains the Naver paper crawler, online candidate collector, and legal morning report sender.

Do not commit `.env`, SQLite DB files, `dist/`, `build/`, virtual environments, generated reports, or release zip files.

## Current Operating Goal

Every day at 06:00 on a Windows PC that is powered on and logged in, the app should:

1. Crawl the report date's Naver newspaper-page articles.
2. Crawl online candidate articles published from the previous day 18:00 through the report date 06:00.
3. Fetch and clean article bodies before analysis.
4. Select Korean legal-desk candidates using the configured legal keywords.
5. Generate a morning-report Markdown file.
6. Include both selected report items and skipped candidate articles with exclusion reasons.
7. Send the report to Telegram.

The scheduled production command is:

```powershell
.\venv\Scripts\python.exe morning_report_task.py --date today --send-telegram --force --no-llm
```

`--no-llm` is intentional for the scheduled job. The current stable operating path uses deterministic extractive summaries and rule-based filtering rather than Gemini or Ollama.

## Current Git State

- Remote: `https://github.com/ggunglee/NaverPaperCrawler`
- Main branch: `main`
- Work completed on 2026-05-15:
  - Morning Telegram automation.
  - Legal-desk morning scope: report-date paper plus previous-day 18:00 to report-day 06:00 online articles.
  - Body cleanup before storing fetched article text.
  - Report wording normalization to the user's morning-report style.
  - Skipped candidate section in the delivered report.
  - Same-event duplicate preference: exclusive or earlier article wins.
  - Police-led articles excluded from final legal report, but keyword candidates can still appear in skipped candidates with a reason.
  - GUI table sorting for date, newspaper, section/page, published time, title, and URL.
  - Windows Task Scheduler job consolidated to one 06:00 Telegram morning-report task.

## Runtime Files To Move Separately

Use GitHub for code:

```powershell
git clone https://github.com/ggunglee/NaverPaperCrawler.git
cd NaverPaperCrawler
```

Move these local runtime files separately if exact continuity is needed:

- `.env`
- SQLite DB directory: `%USERPROFILE%\.naver_news_crawler\data\`
- Existing generated reports: `%USERPROFILE%\.naver_news_crawler\reports\`

The SQLite DB contains crawl history and analysis state. The code can run without copying old reports, but copying the DB preserves previous articles and duplicate-comparison context.

## Required `.env`

Create `.env` at the repository root. Do not commit it.

Minimum for Telegram operation:

```dotenv
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

For online candidate discovery using the Naver API:

```dotenv
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
```

LLM keys are optional for the current scheduled no-LLM workflow:

```dotenv
GEMINI_API_KEY=...
REPORT_LLM_BACKEND=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=exaone3.5:2.4b
```

Notes:

- The user previously used `GEMINI_API_KEY`.
- Ollama was tested as an optional local summarization backend, but the scheduled job now uses `--no-llm` because the deterministic report path was more stable for the required format.
- Never paste real API keys into GitHub, commits, issue comments, or handoff docs.

## Setup On Another Windows PC

Create and activate a virtual environment:

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install -r requirements-report.txt
```

Optional semantic-similarity dependency:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-report-sentence.txt
```

The deterministic fallback uses lexical embeddings, so sentence-transformers is not required for operation.

## Validation Commands

Check readiness:

```powershell
.\venv\Scripts\python.exe report_generator.py --preflight --embedding-backend lexical
```

Run a no-send morning-report smoke test:

```powershell
.\venv\Scripts\python.exe morning_report_task.py --date today --force --no-llm
```

Run for a fixed historical date without crawling:

```powershell
.\venv\Scripts\python.exe morning_report_task.py --date 20260515 --force --no-crawl --no-llm
```

Expected output path:

```text
%USERPROFILE%\.naver_news_crawler\reports\YYYYMMDD_morning_report.md
```

Send to Telegram after inspecting the Markdown:

```powershell
.\venv\Scripts\python.exe morning_report_task.py --date today --force --no-llm --send-telegram
```

Register the Windows scheduled task:

```powershell
.\venv\Scripts\python.exe main.py --install-scheduler --no-gui
```

Verify registration:

```powershell
schtasks /Query /TN NaverPaperCrawler_MorningReportTelegram /FO LIST /V
```

The expected task command is:

```text
...\venv\Scripts\python.exe "...NaverPaperCrawler\morning_report_task.py" --date today --send-telegram --force --no-llm
```

Remove the scheduled task:

```powershell
.\venv\Scripts\python.exe main.py --uninstall-scheduler --no-gui
```

## Report Rules Now Encoded

- Report scope:
  - Paper: report date.
  - Online: previous day 18:00 through report date 06:00.
- Keywords include:
  - `대검찰청`, `대검`, `대법원`, `대법`, `헌법재판소`, `헌재`
  - `서울중앙지검`, `서울고검`, `법무부`, `공수처`
  - `검찰`, `법원`, `특검`
  - `행정법원`, `회생법원`, `가정법원`
  - `서울중앙지법`, `서울고법`
  - `변협`, `대한변호사협회`, `서울지방변호사회`
- Police-led articles are excluded from final selected report items.
- Legal candidates excluded by filters should still be listed under skipped candidates with a reason.
- Same-event duplicates are retained as skipped candidates. The report prefers exclusives and earlier uploaded items.
- The report tone avoids polite endings such as `습니다`.
- Report summaries should end in the compact desk style:
  - `불기소 처분.`
  - `확인됨.`
  - quoted speech as `"..."고.`
- The report includes newspaper/page suffixes where available, for example `경향 10면`, `중앙 14면`.

## 2026-05-15 Verification Snapshot

The final checked 2026-05-15 report had:

- 14 keyword candidates in morning scope.
- 6 selected report items.
- 1 same-event duplicate under `걸러진 스트레이트/반복 기사`.
- 7 excluded candidates under `기타 제외 기사`.

Notable bug fixed that day:

- The first implementation looked like only 3 legal candidates existed because `desk_focus` removed legal candidates before skipped-candidate rendering. This was fixed so keyword candidates excluded by filters still appear in the report diagnostics.

## Notes For The Next Codex

The user wants hands-on verification, not advice-only output. Run the commands, inspect the generated Markdown, and fix code before sending if the report looks wrong.

Do not expose or commit:

- `.env`
- Telegram bot token
- Telegram chat ID
- Gemini or Google API keys
- SQLite DB files
- generated report files
