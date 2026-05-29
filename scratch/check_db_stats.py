import sqlite3
import os
import sys

# Reconfigure stdout to use utf-8
sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Database

db = Database()
with db.connect() as conn:
    print("Non-paper articles for date '20260529' in DB by newspaper:")
    rows = conn.execute("""
        SELECT newspaper, COUNT(*) 
        FROM articles 
        WHERE date = '20260529' AND article_type != '지면'
        GROUP BY newspaper
    """).fetchall()
    for r in rows:
        print(f"  - {r[0]}: {r[1]}")
        
    print("\nNon-paper articles for date '20260529' in DB by article_type:")
    rows = conn.execute("""
        SELECT article_type, COUNT(*) 
        FROM articles 
        WHERE date = '20260529' AND article_type != '지면'
        GROUP BY article_type
    """).fetchall()
    for r in rows:
        print(f"  - {r[0]}: {r[1]}")
        
    print("\nCheck if there are any Newsis/News1 articles for today regardless of type:")
    rows = conn.execute("""
        SELECT newspaper, article_type, COUNT(*) 
        FROM articles 
        WHERE date = '20260529' AND newspaper IN ('뉴시스', '뉴스1', '노컷뉴스', '법률신문')
        GROUP BY newspaper, article_type
    """).fetchall()
    for r in rows:
        print(f"  - {r[0]} ({r[1]}): {r[2]}")
