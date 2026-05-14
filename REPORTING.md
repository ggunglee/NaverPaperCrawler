# Morning report generator

`report_generator.py` is a second-stage analysis script. It is intentionally separate from the GUI EXE build because report analysis can use heavy NLP packages.

Install the lightweight report dependencies:

```bat
venv\Scripts\python.exe -m pip install -r requirements-report.txt
```

Optional: install SentenceTransformers for stronger semantic similarity. If this is not installed, the script falls back to a local lexical embedding backend.

```bat
venv\Scripts\python.exe -m pip install -r requirements-report-sentence.txt
```

Seed the one-time exclusive-claim comparison DB:

```bat
venv\Scripts\python.exe report_generator.py --backfill-source --from 20260414 --to 20260513
venv\Scripts\python.exe report_generator.py --seed-exclusive --from 20260414 --to 20260513 --embedding-backend lexical
```

Generate a morning report:

```bat
venv\Scripts\python.exe report_generator.py --date today --output-file
```

Suggest or manually assign issue categories:

```bat
venv\Scripts\python.exe report_generator.py --suggest-categories --from 20260414 --to 20260513
venv\Scripts\python.exe report_generator.py --suggest-categories --date today --classify-uncertain
```

The generated Markdown format follows the desk-report style:

```md
※Title/Source Page
-New facts and situation changes only.
URL

## 걸러진 스트레이트/반복 기사

- Title / Source (similarity 0.91)
  URL
```
