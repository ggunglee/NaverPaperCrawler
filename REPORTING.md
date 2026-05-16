# Morning Legal Report Operation

This document describes the operating rules for the daily legal morning report.

The current production path is deterministic and does not call an LLM:

```bat
venv\Scripts\python.exe morning_report_task.py --date today --send-telegram --force --no-llm
```

The Windows scheduled task runs this command every day at 06:00.

## Scope

- Paper articles: report date.
- Online articles: previous day 18:00 through report date 06:00.
- Output path: `%USERPROFILE%\.naver_news_crawler\reports\YYYYMMDD_morning_report.md`.
- Delivery: Telegram.

The crawler must collect articles first. LLMs, if ever enabled manually, are only for downstream selection/summarization. They should not replace clean crawling.

## Keywords

The legal-monitoring keywords are:

- `대검찰청`, `대검`, `대법원`, `대법`, `헌법재판소`, `헌재`
- `서울중앙지검`, `서울고검`, `법무부`, `공수처`
- `검찰`, `법원`, `특검`
- `행정법원`, `회생법원`, `가정법원`
- `서울중앙지법`, `서울고법`
- `변협`, `대한변호사협회`, `서울지방변호사회`

Additional strong legal-report signals include:

- `불기소`, `약식기소`, `기소`, `감찰`, `감찰위`
- `보완수사권`, `중수청`, `공소청`, `검찰개혁`
- `비자`, `출입국`, `체류변경`
- `파산`, `회생`
- `김건희`, `결심공판`, `구형`, `알선수재`, `공판`, `재판`

## Inclusion Rules

Include articles that have concrete legal/prosecution/court/MOJ/legal-policy value.

Include even without `[단독]` when the article is substantively desk-relevant:

- Prosecution or special-counsel action.
- Prosecutorial decisions such as `불기소`, `약식기소`, `기소`.
- Ministry of Justice or immigration decisions, including visa status decisions.
- Court rulings, appeal developments, recusal motions, sentencing, trial conclusion, or request for sentence.
- Legal-system and prosecution-reform issues.
- Bar association, bankruptcy/rehabilitation, legal profession, or major court administration issues.

Examples the user explicitly treated as report-worthy:

- Humidifier-disinfectant victims' complaint where prosecutors declined to indict SK Chemical/Aekyung.
- Ministry of Justice refusal to change a Nepal dementia mother's visa status.
- Kim Gun-hee special-counsel/court item about first-instance proceedings and requested sentence.

## Exclusion Rules

Exclude from selected report items:

- Police-led articles where police are the main actor.
- Generic violent crime or accident articles unless the legal decision is the main news.
- Foreign incident articles sourced mainly from overseas media, such as Daily Mail/Reuters/AP/BBC/CNN, unless there is a concrete Korean legal-system angle.
- Event schedules such as `[오늘의 주요일정]법조`.
- Opinion/editorial/column items unless they contain a concrete legal-policy development.
- Election-campaign diary items such as campaign-office openings, launch events, stump speeches, and routine candidate moves.
- Political rally or partisan attack items where legal words appear only as rhetoric, such as 사법쿠데타, 조작기소, 하야 집회. Polling stories can remain if the legal issue is the substance of the poll.
- Business, industry, shopping, tourism, or culture stories with merely incidental legal wording.
- Non-legal policy stories that only contain phrases such as `법적 근거`.
- Legal-advice/lifestyle items such as radio 상담소, 사연자, 생활법률, 상간녀/상간남 상담 stories.

Foreign incident articles sourced mainly from overseas media are outside the user's interest and should be dropped silently, not shown in skipped candidates.
Legal-advice/lifestyle items and exact same-event duplicates are also dropped silently from the Telegram report.

Excluded keyword candidates should still be visible in the report diagnostics.

## Duplicate Priority

When same-day articles cover the same event:

- Prefer `[단독]` if present.
- Otherwise prefer the earlier uploaded article.
- Prefer the paper article when it is the expected morning-paper item.
- Put duplicates under `걸러진 스트레이트/반복 기사`.

Do not hide duplicates completely. The user wants to see what was filtered.

## Report Format

Selected report blocks must use:

```text
※기사 제목/언론사 면수
-핵심 새 내용 1~3문장. 보고체 말투.
URL
```

Examples:

```text
※검찰, 박영수 前 특검 딸 ‘대장동 특혜 분양’ 약식기소/국민 13면
-검찰이 화천대유자산관리에서 근무했던 박영수 전 특별검사의 딸 박모씨를 대장동 아파트 분양 과정에서 특혜를 받은 혐의로 약식기소. 검찰은 지난해 6월 대법원이 “미계약 주택이 발생했는데 예비입주자가 없는 경우 사업 주체는 ‘공개모집’ 절차를 준수해야 한다”고 판시한 점 등을 근거로 기소를 결정.
https://...
```

Paper source/page examples:

- `경향 10면`
- `국민 13면`
- `중앙 14면`
- `한겨레 6면`

Online examples:

- `연합뉴스 정치`
- `뉴시스 사회`
- `TV조선 사회`

## Report Tone

Use compact desk-report Korean. Avoid polite prose.

Preferred endings:

- `처분.`
- `약식기소.`
- `확인됨.`
- `포착.`
- `파악.`
- `통보.`
- `요구.`
- `예정.`
- `진행.`
- quoted speech as `"..."고.`

Avoid:

- `했습니다`, `합니다`, `습니다`, `입니다`
- `했다`, `하였다`, `한다`
- dangling endings such as `통해.`, `보다도.`, `저마다.`, `판단하면서다.`
- reporter names, email addresses, AI-summary notices, copyright notices, `많이 본 뉴스`

## Skipped Candidate Sections

Reports should include skipped candidates when there are filtered keyword candidates:

```text
## 걸러진 스트레이트/반복 기사

- 제목 / 언론사 (동일 사안 1.00)
  URL

## 기타 제외 기사

- 제목 / 언론사 (경찰 주체 제외)
  URL
- 제목 / 언론사 (법조 초점 낮음)
  URL
```

This is not optional in normal operation. It is how the user audits borderline decisions.

## Validation Commands

Install dependencies:

```bat
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-report.txt
```

Preflight:

```bat
venv\Scripts\python.exe report_generator.py --preflight --embedding-backend lexical
```

Generate without sending:

```bat
venv\Scripts\python.exe morning_report_task.py --date today --force --no-llm
```

Generate a fixed-date report from the existing DB:

```bat
venv\Scripts\python.exe morning_report_task.py --date 20260515 --force --no-crawl --no-llm
```

Send after inspecting:

```bat
venv\Scripts\python.exe morning_report_task.py --date today --force --no-llm --send-telegram
```

## Manual QA Checklist

Before sending:

- Confirm selected item count is plausible by checking raw morning-scope keyword candidates if the report looks too short.
- Confirm skipped candidates are present when filters excluded keyword hits.
- Confirm every selected item has headline/source, summary, and URL.
- Confirm summaries use the compact report style.
- Confirm no body noise leaked into the report.
- Confirm police-led and non-legal incidental keyword hits appear only as skipped candidates.

## 2026-05-15 Known Good Snapshot

The corrected 2026-05-15 report had:

- 14 keyword candidates.
- 6 selected report items.
- 1 same-event duplicate.
- 7 excluded candidates.

The first version incorrectly showed too few articles because `desk_focus` filtering happened before skipped-candidate diagnostics. That bug is fixed.
