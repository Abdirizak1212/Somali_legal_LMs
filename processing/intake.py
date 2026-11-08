import os
import sys
from datetime import datetime
from pathlib import Path

import pymupdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from processing.database import (  # noqa: E402
    create_tables,
    get_connection,
    insert_document,
    print_summary,
    update_stats,
)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
LANGUAGES = ("Somali", "English", "Arabic", "Bilingual")
DOCUMENT_TYPES = (
    "Constitution",
    "Legislation",
    "Regulation",
    "Policy",
    "Charter",
    "Judicial",
    "Other",
)
STATUSES = ("in_force", "historical", "draft")


def _normalized_path(path):
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return os.path.normcase(str(candidate.resolve()))


def _known_document_paths():
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT local_path FROM documents WHERE local_path IS NOT NULL AND local_path != ''"
        ).fetchall()
        return {_normalized_path(row["local_path"]) for row in rows}
    finally:
        connection.close()


def _ask_value(label, default=None):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        answer = input(f"{label}{suffix}: ").strip()
        if answer:
            return answer
        if default is not None:
            return default
        print("A value is required.")


def _ask_choice(label, options):
    choices = ", ".join(options)
    while True:
        answer = input(f"{label} ({choices}): ").strip()
        match = next(
            (option for option in options if option.casefold() == answer.casefold()),
            None,
        )
        if match:
            return match
        print(f"Please enter one of: {choices}.")


def _ask_year():
    while True:
        answer = input("Year (leave blank if unknown): ").strip()
        if not answer:
            return None
        try:
            year = int(answer)
        except ValueError:
            print("Enter a year as a number, or leave it blank.")
            continue
        if 1 <= year <= 9999:
            return year
        print("Enter a year between 1 and 9999, or leave it blank.")


def _collect_metadata(pdf_path):
    print(f"\nMetadata for: {pdf_path.name}")
    return {
        "title": _ask_value("Title", pdf_path.stem.replace("_", " ")),
        "language": _ask_choice("Language", LANGUAGES),
        "doc_type": _ask_choice("Document type", DOCUMENT_TYPES),
        "legal_domain": _ask_value("Legal domain"),
        "institution": _ask_value("Issuing institution"),
        "year": _ask_year(),
        "source_name": _ask_value("Source name"),
        "status": _ask_choice("Status", STATUSES),
    }


def _extract_text(pdf_path):
    with pymupdf.open(pdf_path) as document:
        text = "\n".join(page.get_text() for page in document).strip()
    return text, len(text.split())


def intake_pdf(pdf_path):
    try:
        text_content, word_count = _extract_text(pdf_path)
        extraction_error = ""
        print(f"Extracted {word_count:,} words.")
    except (pymupdf.FileDataError, RuntimeError, OSError, ValueError) as error:
        text_content = ""
        word_count = 0
        extraction_error = str(error)
        print(f"Text extraction failed: {error}")

    metadata = _collect_metadata(pdf_path)
    document = {
        **metadata,
        "source_url": "",
        "local_path": str(pdf_path.resolve().relative_to(PROJECT_ROOT)),
        "text_content": text_content,
        "word_count": word_count,
        "somali_word_count": word_count if metadata["language"] == "Somali" else 0,
        "download_status": "failed" if extraction_error else "success",
        "error_message": extraction_error,
        "provenance": "Manually added from data/raw/",
        "processed_at": datetime.now().isoformat(),
    }
    document_id = insert_document(document)
    print(f"Saved to database (document ID {document_id}).")
    return document_id


def run():
    previous_directory = Path.cwd()
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        # The database module uses a project-relative DB_PATH.
        os.chdir(PROJECT_ROOT)
        create_tables()
        known_paths = _known_document_paths()
        pdf_paths = sorted(
            (
                path
                for path in RAW_DIR.rglob("*")
                if path.is_file() and path.suffix.casefold() == ".pdf"
            ),
            key=lambda path: str(path).casefold(),
        )
        new_paths = [path for path in pdf_paths if _normalized_path(path) not in known_paths]

        if not new_paths:
            print("No new PDF files found in data/raw/.")
        else:
            print(f"Found {len(new_paths)} PDF(s) not yet in the database.")
            for pdf_path in new_paths:
                intake_pdf(pdf_path)

        update_stats()
        print_summary()
    finally:
        os.chdir(previous_directory)


if __name__ == "__main__":
    run()
