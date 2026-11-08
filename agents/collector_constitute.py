import requests
import json
import os
from datetime import datetime

OUTPUT_DIR = "data/metadata"
RAW_DIR = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

# Known Somalia legal document URLs - direct and reliable
SOMALIA_DOCUMENTS = [
    {
        "title": "Federal Republic of Somalia - Provisional Constitution 2012",
        "url": "https://www.constituteproject.org/constitution/Somalia_2012.pdf",
        "type": "constitution",
        "year": 2012,
        "source": "Constitute Project"
    },
    {
        "title": "Somalia - Transitional Federal Charter 2004",
        "url": "https://www.refworld.org/pdfid/4ff53d262.pdf",
        "type": "charter",
        "year": 2004,
        "source": "UNHCR Refworld"
    }
]

def download_document(doc):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        print(f"Downloading: {doc['title']}")
        response = requests.get(doc["url"], headers=headers, timeout=30)
        response.raise_for_status()
        filename = doc["url"].split("/")[-1]
        filepath = os.path.join(RAW_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(response.content)
        print(f"  Saved: {filepath} ({len(response.content)} bytes)")
        return filepath
    except Exception as e:
        print(f"  Failed: {e}")
        return None

def run():
    print("Starting Somalia Legal Document collection...")
    results = []
    for doc in SOMALIA_DOCUMENTS:
        filepath = download_document(doc)
        results.append({
            **doc,
            "local_path": filepath,
            "collected_at": datetime.now().isoformat(),
            "status": "success" if filepath else "failed"
        })
    metadata_path = os.path.join(OUTPUT_DIR, "somalia_documents.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    success = sum(1 for r in results if r["status"] == "success")
    print(f"\nDone. {success}/{len(results)} documents downloaded.")
    print(f"Metadata saved to {metadata_path}")

if __name__ == "__main__":
    run()
