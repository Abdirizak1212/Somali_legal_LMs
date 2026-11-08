import bz2
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from processing.database import (  # noqa: E402
    create_tables,
    get_connection,
    insert_document,
    print_summary,
    update_stats,
)

CC100_DATASET = "statmt/cc100"
CC100_CONFIG = "so"
CC100_LIMIT = 50_000
WIKIPEDIA_DUMP_URL = (
    "https://dumps.wikimedia.org/sowiki/latest/"
    "sowiki-latest-pages-articles.xml.bz2"
)
WIKIPEDIA_DUMP_PATH = Path(PROJECT_ROOT) / "data" / "raw" / "sowiki.xml.bz2"


def _existing_titles(source_name):
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT title FROM documents WHERE source_name = ?",
            (source_name,),
        ).fetchall()
        return {row["title"] for row in rows}
    finally:
        connection.close()


def _ingest_dataset(dataset, source_name, dataset_reference, max_records=None):
    existing_titles = _existing_titles(source_name)
    inserted = 0
    skipped = 0

    for index, record in enumerate(dataset):
        if max_records is not None and index >= max_records:
            break

        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            skipped += 1
            continue

        title = record.get("title")
        if not isinstance(title, str) or not title.strip():
            title = f"{source_name} Somali record {index + 1}"
        else:
            title = title.strip()

        if title in existing_titles:
            skipped += 1
            continue

        word_count = len(text.split())
        insert_document({
            "title": title,
            "doc_type": "web_corpus",
            "institution": "HuggingFace",
            "language": "so",
            "source_name": source_name,
            "source_url": dataset_reference,
            "text_content": text,
            "word_count": word_count,
            "somali_word_count": word_count,
            "download_status": "success",
            "provenance": f"Hugging Face dataset: {dataset_reference}",
        })
        existing_titles.add(title)
        inserted += 1

        if inserted and inserted % 1000 == 0:
            print(f"{source_name}: inserted {inserted:,} records...")

    print(
        f"{source_name}: inserted {inserted:,} records; "
        f"skipped {skipped:,} empty or previously collected records."
    )
    return inserted


def collect_cc100():
    dataset_reference = f"{CC100_DATASET} (config {CC100_CONFIG})"
    print(f"Loading {dataset_reference} (first {CC100_LIMIT:,} records)...")
    from datasets import load_dataset

    dataset = load_dataset(
        CC100_DATASET,
        name=CC100_CONFIG,
        split="train",
        streaming=True,
        trust_remote_code=True,
    )
    return _ingest_dataset(
        dataset,
        "CC-100",
        f"https://huggingface.co/datasets/{CC100_DATASET}/tree/main",
        max_records=CC100_LIMIT,
    )


def _download_wikipedia_dump(dump_path, session=None):
    session = session or requests
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = dump_path.with_name(dump_path.name + ".part")
    headers = {
        "User-Agent": "Somali Legal LM research corpus collector",
    }

    try:
        with session.get(
            WIKIPEDIA_DUMP_URL,
            headers=headers,
            stream=True,
            timeout=(30, 180),
        ) as response:
            response.raise_for_status()
            downloaded = 0
            with temporary_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded % (100 * 1024 * 1024) < len(chunk):
                        print(f"  Downloaded {downloaded / (1024 ** 3):.2f} GiB...")
        os.replace(temporary_path, dump_path)
    except (requests.RequestException, OSError):
        if temporary_path.exists():
            temporary_path.unlink()
        raise

    print(f"  Dump saved to {dump_path} ({downloaded:,} bytes).")


def _clean_wikipedia_text(text):
    kept_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("{{", "==", "*")) or stripped.casefold().startswith("[[file:"):
            continue
        if stripped:
            kept_lines.append(stripped)
    return "\n".join(kept_lines).strip()


def _page_value(page, name):
    for element in page.iter():
        if element.tag.rsplit("}", 1)[-1] == name:
            return "".join(element.itertext())
    return ""


def _wikipedia_article_url(title):
    return "https://so.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))


def collect_wikipedia(dump_path=None):
    dump_path = Path(dump_path) if dump_path else WIKIPEDIA_DUMP_PATH
    print(f"Collecting Somali Wikipedia from {WIKIPEDIA_DUMP_URL}...")
    if not dump_path.exists():
        _download_wikipedia_dump(dump_path)
    else:
        print(f"  Using existing dump: {dump_path}")

    existing_titles = _existing_titles("Wikipedia-SO")
    articles = 0
    skipped = 0
    total_words = 0
    root = None

    with bz2.open(dump_path, "rb") as dump:
        for event, element in ET.iterparse(dump, events=("start", "end")):
            if event == "start" and root is None:
                root = element
            elif event == "end" and element.tag.rsplit("}", 1)[-1] == "page":
                title = _page_value(element, "title").strip()
                text_element = next(
                    (
                        child
                        for child in element.iter()
                        if child.tag.rsplit("}", 1)[-1] == "text"
                    ),
                    None,
                )
                text = (
                    "".join(text_element.itertext())
                    if text_element is not None
                    else ""
                )
                cleaned_text = _clean_wikipedia_text(text)

                if not title or not cleaned_text or title in existing_titles:
                    skipped += 1
                else:
                    word_count = len(cleaned_text.split())
                    insert_document({
                        "title": title,
                        "doc_type": "encyclopedia",
                        "institution": "Wikimedia Foundation",
                        "language": "so",
                        "source_name": "Wikipedia-SO",
                        "source_url": _wikipedia_article_url(title),
                        "text_content": cleaned_text,
                        "word_count": word_count,
                        "somali_word_count": word_count,
                        "download_status": "success",
                        "provenance": (
                            "Somali Wikipedia dump; CC BY-SA license. "
                            f"Source: {_wikipedia_article_url(title)}"
                        ),
                    })
                    existing_titles.add(title)
                    articles += 1
                    total_words += word_count

                    if articles % 1000 == 0:
                        print(
                            f"  Imported {articles:,} articles, "
                            f"{total_words:,} words..."
                        )

                element.clear()
                if root is not None:
                    root.clear()

    print(
        f"Wikipedia-SO: imported {articles:,} articles, "
        f"{total_words:,} words; skipped {skipped:,} empty or existing pages."
    )
    return {"articles": articles, "words": total_words, "skipped": skipped}


def run():
    previous_directory = os.getcwd()
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        os.chdir(PROJECT_ROOT)
        create_tables()

        for collector in (collect_cc100, collect_wikipedia):
            try:
                collector()
            except Exception as error:
                print(f"Collection failed for {collector.__name__}: {error}")

        update_stats()
        print_summary()
    finally:
        os.chdir(previous_directory)


if __name__ == "__main__":
    run()
