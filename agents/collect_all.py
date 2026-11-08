import requests
import fitz  # PyMuPDF
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from processing.database import create_tables, insert_document, update_stats, print_summary

RAW_DIR = "data/raw"
os.makedirs(RAW_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

DOCUMENTS = [
    {
        "title": "Federal Republic of Somalia Provisional Constitution 2012 (English)",
        "url": "https://www.constituteproject.org/constitution/Somalia_2012.pdf",
        "doc_type": "Constitution", "institution": "Federal Government of Somalia",
        "legal_domain": "Constitutional", "year": 2012, "language": "English",
        "status": "in_force", "source_name": "Constitute Project",
        "provenance": "Public domain - Constitute Project open access"
    },
    {
        "title": "Somalia Labour Code 1972",
        "url": "https://www.ilo.org/dyn/natlex/docs/ELECTRONIC/11141/68786/F-903521977/SOM11141.pdf",
        "doc_type": "Legislation", "institution": "Government of Somalia",
        "legal_domain": "Labour", "year": 1972, "language": "English",
        "status": "historical", "source_name": "ILO NATLEX",
        "provenance": "ILO NATLEX public database"
    },
    {
        "title": "Charter of the Transitional National Government of Somalia 2000",
        "url": "https://www.refworld.org/pdfid/3ae6b5420.pdf",
        "doc_type": "Charter", "institution": "Transitional National Government",
        "legal_domain": "Constitutional", "year": 2000, "language": "English",
        "status": "historical", "source_name": "UNHCR Refworld",
        "provenance": "UNHCR Refworld public database"
    },
    {
        "title": "Somalia Transitional Federal Charter 2004",
        "url": "https://www.refworld.org/pdfid/411d13694.pdf",
        "doc_type": "Charter", "institution": "Transitional Federal Government",
        "legal_domain": "Constitutional", "year": 2004, "language": "English",
        "status": "historical", "source_name": "UNHCR Refworld",
        "provenance": "UNHCR Refworld public database"
    },
    {
        "title": "UN Security Council Resolution 1744 - AMISOM Somalia 2007",
        "url": "https://digitallibrary.un.org/record/590742/files/S_RES_1744%282007%29-EN.pdf",
        "doc_type": "Resolution", "institution": "UN Security Council",
        "legal_domain": "International", "year": 2007, "language": "English",
        "status": "in_force", "source_name": "UN Digital Library",
        "provenance": "UN Digital Library open access"
    },
    {
        "title": "UNDP Somalia Constitution 2012 Version",
        "url": "https://www.undp.org/sites/g/files/zskgke326/files/migration/so/undp-so-Constitution-2012.pdf",
        "doc_type": "Constitution", "institution": "Federal Government of Somalia",
        "legal_domain": "Constitutional", "year": 2012, "language": "Bilingual",
        "status": "in_force", "source_name": "UNDP Somalia",
        "provenance": "UNDP Somalia open access"
    },
]

def extract_text(filepath):
    try:
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        words = len(text.split())
        return text.strip(), words
    except Exception as e:
        print(f"    Text extraction failed: {e}")
        return "", 0

def download_and_store(doc, index, total):
    print(f"\n[{index}/{total}] {doc['title'][:60]}")
    try:
        r = requests.get(doc["url"], headers=HEADERS, timeout=30)
        r.raise_for_status()

        filename = doc["url"].split("/")[-1].split("?")[0]
        if not filename.lower().endswith(".pdf"):
            filename = filename + ".pdf"
        filepath = os.path.join(RAW_DIR, filename)

        with open(filepath, "wb") as f:
            f.write(r.content)
        size_kb = len(r.content) // 1024
        print(f"  Downloaded: {size_kb} KB")

        text, word_count = extract_text(filepath)
        print(f"  Extracted : {word_count:,} words")

        insert_document({
            **doc,
            "source_url": doc["url"],
            "local_path": filepath,
            "text_content": text,
            "word_count": word_count,
            "somali_word_count": word_count if doc["language"] == "Somali" else 0,
            "download_status": "success",
            "error_message": ""
        })
        print("  Saved to database")
        return True

    except Exception as e:
        print(f"  Failed: {e}")
        insert_document({
            **doc,
            "source_url": doc["url"],
            "local_path": "",
            "text_content": "",
            "word_count": 0,
            "somali_word_count": 0,
            "download_status": "failed",
            "error_message": str(e)
        })
        return False

def run():
    print("Starting Somalia legal document collection...")
    create_tables()
    successful = 0
    for index, document in enumerate(DOCUMENTS, start=1):
        if download_and_store(document, index, len(DOCUMENTS)):
            successful += 1
        if index < len(DOCUMENTS):
            time.sleep(1)

    update_stats()
    print(f"\nCollection complete: {successful}/{len(DOCUMENTS)} documents downloaded.")
    print_summary()

if __name__ == "__main__":
    run()
