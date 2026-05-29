import os
import glob

search_path = "C:/Users/admin/Desktop/코딩 모음/My Morning Report/NaverPaperCrawler/**/*.py"
query = "def show_rows"

for filepath in glob.glob(search_path, recursive=True):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if query in line:
                    print(f"{filepath}:{line_no}: {line.strip()}")
    except Exception as e:
        pass
