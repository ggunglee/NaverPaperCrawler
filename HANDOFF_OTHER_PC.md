# Other PC Handoff

This repo contains the source code for the Naver paper crawler and morning report generator.
Do not commit `.env`, SQLite DB files, `dist/`, `build/`, virtual environments, or release zip files.

## Current Git State

- Remote: `https://github.com/ggunglee/NaverPaperCrawler`
- Branch: `main`
- Latest known feature commit after morning-report hardening: `732ebf4 Polish morning report filtering`

## What To Move To Another PC

Use GitHub for code:

```powershell
git clone https://github.com/ggunglee/NaverPaperCrawler.git
cd NaverPaperCrawler
```

Move these local runtime files separately if you want to reproduce the current state exactly:

- `.env`
- SQLite DB directory: `C:\Users\leeyk\.naver_news_crawler\data\`
- Existing generated reports, if needed: `C:\Users\leeyk\.naver_news_crawler\reports\`

Do not put the `.env` file or DB dump in GitHub. The `.env` contains API keys, and the DB is runtime state.

## Setup On The Other PC

Create and activate a virtual environment:

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install -r requirements-report.txt
```

For better semantic similarity, optionally install the heavier sentence-transformers stack:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-report-sentence.txt
```

## Required `.env`

The morning report generator needs a Gemini key:

```dotenv
GEMINI_API_KEY=...
```

The crawler may also need Naver API credentials depending on the flow being tested:

```dotenv
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
```

## Validation Commands

Check local readiness:

```powershell
.\venv\Scripts\python.exe report_generator.py --preflight --embedding-backend lexical
```

Refresh stored exclusive-claim vectors if the DB was copied from an older run:

```powershell
.\venv\Scripts\python.exe report_generator.py --refresh-claim-embeddings --embedding-backend lexical
```

Generate a real report with Gemini:

```powershell
.\venv\Scripts\python.exe report_generator.py --date 20260514 --limit 20 --embedding-backend lexical --output-file
```

For a no-LLM smoke test:

```powershell
.\venv\Scripts\python.exe report_generator.py --date 20260514 --limit 20 --embedding-backend lexical --no-llm --output-file
```

## Expected Behavior

- The report is saved under `%USERPROFILE%\.naver_news_crawler\reports\`.
- Similar same-day articles should appear under `걸러진 스트레이트/반복 기사` with links.
- Ambiguous or broad legal/crime articles should appear under `분류 필요 기사`, not as filtered duplicates.
- Articles containing `종합특검` should auto-classify as `2차 종합특검`.
- Old one-month exclusive claims are used as comparison baseline, then new report-worthy claims continue accumulating.

## Notes For The Next Codex

The user wants hands-on verification, not advice-only output. Run the commands and inspect the generated Markdown. If anything is unstable, fix it and rerun. Keep `.env` and local DB out of git.
