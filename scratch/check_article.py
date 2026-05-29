import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from report_generator import is_obvious_foreign, is_foreign_incidental_article

db = Database()
with db.connect() as conn:
    row = conn.execute("SELECT * FROM articles WHERE title LIKE '%볼리비아%' OR summary LIKE '%볼리비아%'").fetchone()

if row:
    row = dict(row)
    print("Article ID:", row["id"])
    print("Article Title:", row["title"])
    print("Article Summary:", row["summary"])
    print("Article Body Length:", len(row["body"]) if row["body"] else 0)
    print("Article Body Snippet:", row["body"][:200] if row["body"] else None)
    
    print("is_obvious_foreign?:", is_obvious_foreign(row))
    print("is_foreign_incidental_article?:", is_foreign_incidental_article(row))
else:
    print("No Bolivia article found.")
