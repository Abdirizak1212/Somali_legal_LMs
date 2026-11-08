import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime

BASE_URL = "https://www.fao.org/faolex/results/en/"
SEARCH_URL = "https://www.fao.org/faolex/results/en/?details=1&q=somalia&type=ALL&subject=ALL&lng=ALL"
OUTPUT_DIR = "data/metadata"
RAW_DIR = "data/raw"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

def fetch_page(url):
    headers = {"User-Agent": "Mozilla/5.0 (Research Bot - Somali Legal LM Project)"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def parse_documents(html):
    soup = BeautifulSoup(html, "lxml")
    documents = []
    results = soup.find_all("div", class_="result-item")
    for item in results:
        try:
            title = item.find("h3").get_text(strip=True) if item.find("h3") else "Unknown"
            link_tag = item.find("a", href=True)
            link = link_tag["href"] if link_tag else ""
            date = item.find("span", class_="date")
            date_text = date.get_text(strip=True) if date else "Unknown"
            documents.append({
                "title": title,
                "url": link,
                "date": date_text,
                "source": "FAO FAOLEX",
                "collected_at": datetime.now().isoformat()
            })
        except Exception as e:
            print(f"Parse error: {e}")
    return documents

def save_metadata(documents):
    path = os.path.join(OUTPUT_DIR, "fao_documents.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(documents)} documents to {path}")

def run():
    print("Starting FAO FAOLEX collection...")
    html = fetch_page(SEARCH_URL)
    if html:
        docs = parse_documents(html)
        save_metadata(docs)
        print(f"Collected {len(docs)} documents")
    else:
        print("Failed to fetch page")

if __name__ == "__main__":
    run()
