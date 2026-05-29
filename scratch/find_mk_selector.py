from bs4 import BeautifulSoup
import os

filepath = "C:/Users/admin/.gemini/antigravity-cli/brain/5fcafc07-abe8-4072-8d30-f296f91a6061/.system_generated/steps/627/content.md"
with open(filepath, "r", encoding="utf-8") as f:
    html = f.read()

idx = html.find("<!doctype html>")
if idx != -1:
    html = html[idx:]

soup = BeautifulSoup(html, "html.parser")

for div in soup.find_all(["div", "section", "article"]):
    classes = div.get("class") or []
    if "news_cnt_detail_wrap" in classes:
        print(f"Tag: {div.name}, Class: {classes}")
        print("Text snippet:", div.get_text(strip=True)[:400])
