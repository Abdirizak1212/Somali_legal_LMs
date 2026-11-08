import html
import json
import os
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "metadata"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
METADATA_PATH = OUTPUT_DIR / "all_documents.json"
REPORT_PATH = PROJECT_ROOT / "data" / "collection_report.html"

SOMALIA_DOCUMENTS = [
    {
        "title": "Federal Republic of Somalia - Provisional Constitution (2012)",
        "url": "https://www.constituteproject.org/constitution/Somalia_2012.pdf",
        "source": "Constitute Project",
    },
    {
        "title": "Federal Constitution of Somalia (Final)",
        "url": "https://unsom.unmissions.org/sites/default/files/old_dnn/docs/FEDERAL_CONSTITUTION_OF_SOMALIA_FINAL.pdf",
        "source": "United Nations Assistance Mission in Somalia",
    },
    {
        "title": "Somalia legal document (Refworld 5b7988f54)",
        "url": "https://www.refworld.org/pdfid/5b7988f54.pdf",
        "source": "UNHCR Refworld",
    },
    {
        "title": "Somalia legal document (Refworld 4b4f5e612)",
        "url": "https://www.refworld.org/pdfid/4b4f5e612.pdf",
        "source": "UNHCR Refworld",
    },
    {
        "title": "Somalia legal document (Refworld 4b4f5e3c2)",
        "url": "https://www.refworld.org/pdfid/4b4f5e3c2.pdf",
        "source": "UNHCR Refworld",
    },
]


def download_document(document):
    filename = Path(urlparse(document["url"]).path).name
    filepath = RAW_DIR / filename
    temporary_path = filepath.with_name(filepath.name + ".part")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Somali Legal LM Research Project)"
    }

    try:
        print(f"Downloading: {document['title']}")
        with requests.get(
            document["url"],
            headers=headers,
            timeout=(15, 60),
            stream=True,
        ) as response:
            response.raise_for_status()
            size = 0
            prefix = bytearray()
            with temporary_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if len(prefix) < 5:
                        prefix.extend(chunk[: 5 - len(prefix)])
                    output.write(chunk)
                    size += len(chunk)

            if not prefix.startswith(b"%PDF-"):
                raise ValueError("Response content is not a PDF")

        os.replace(temporary_path, filepath)
        print(f"  Saved: {filepath.relative_to(PROJECT_ROOT)} ({size:,} bytes)")
        return {
            "filename": filename,
            "local_path": str(filepath.relative_to(PROJECT_ROOT)),
            "status": "success",
            "bytes": size,
        }
    except (requests.RequestException, OSError, ValueError) as error:
        if temporary_path.exists():
            temporary_path.unlink()
        print(f"  Failed: {error}")
        return {
            "filename": filename,
            "local_path": None,
            "status": "failed",
            "bytes": 0,
            "error": str(error),
        }


def generate_report(documents, report_path=REPORT_PATH):
    total = len(documents)
    successful = sum(document["status"] == "success" for document in documents)
    total_bytes = sum(document.get("bytes", 0) for document in documents)

    rows = []
    for document in documents:
        safe_title = html.escape(document["title"])
        safe_source = html.escape(document["source"])
        safe_url = html.escape(document["url"], quote=True)
        if document["status"] == "success":
            local_path = Path(document["local_path"])
            download_link = html.escape(
                os.path.relpath(
                    PROJECT_ROOT / local_path,
                    Path(report_path).resolve().parent,
                ).replace(os.sep, "/"),
                quote=True,
            )
            status = '<span class="status success">Downloaded</span>'
            file_cell = (
                f'<a class="file-link" href="{download_link}">'
                f'{html.escape(document["filename"])}</a>'
            )
            detail = f'{document.get("bytes", 0):,} bytes'
        else:
            status = '<span class="status failed">Failed</span>'
            file_cell = '<span class="muted">Not saved</span>'
            detail = html.escape(document.get("error", "Download failed"))

        rows.append(
            "<tr>"
            f"<td><strong>{safe_title}</strong><small>{safe_source}</small></td>"
            f'<td><a href="{safe_url}" target="_blank" rel="noopener noreferrer">'
            "View source</a></td>"
            f"<td>{file_cell}</td>"
            f"<td>{status}<small>{detail}</small></td>"
            "</tr>"
        )

    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    report_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Somalia Legal Document Collection</title>
  <style>
    :root {{ color-scheme: light; --ink: #172b3a; --muted: #647789;
      --paper: #f3f7f6; --accent: #087f70; --line: #e2e9e8; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink);
      font: 15px/1.5 "Segoe UI", Arial, sans-serif; }}
    header {{ padding: 48px max(24px, calc((100% - 1120px) / 2));
      color: white; background: linear-gradient(120deg, #123b4a, #087f70); }}
    header p {{ margin: 8px 0 0; color: #d3efea; }}
    h1 {{ margin: 0; font-size: clamp(1.8rem, 4vw, 2.7rem); }}
    main {{ width: min(1120px, calc(100% - 40px)); margin: 28px auto 60px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 14px; margin-bottom: 22px; }}
    .card, .panel {{ border: 1px solid var(--line); border-radius: 14px;
      background: white; box-shadow: 0 5px 18px #1833430b; }}
    .card {{ padding: 19px 21px; }}
    .card span {{ display: block; color: var(--muted); font-size: .82rem; }}
    .card strong {{ display: block; margin-top: 3px; font-size: 1.65rem; }}
    .panel {{ overflow: hidden; }}
    .panel-heading {{ padding: 19px 22px; border-bottom: 1px solid var(--line); }}
    h2 {{ margin: 0; font-size: 1.1rem; }}
    .panel-heading p {{ margin: 4px 0 0; color: var(--muted); font-size: .88rem; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th, td {{ padding: 15px 18px; border-bottom: 1px solid var(--line);
      vertical-align: top; }}
    th {{ color: var(--muted); background: #fbfcfc; font-size: .76rem;
      letter-spacing: .06em; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: 0; }}
    td small {{ display: block; margin-top: 4px; color: var(--muted);
      overflow-wrap: anywhere; }}
    a {{ color: #087f70; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .status {{ display: inline-block; padding: 3px 9px; border-radius: 999px;
      font-size: .78rem; font-weight: 700; }}
    .success {{ color: #146c43; background: #e5f5ec; }}
    .failed {{ color: #9c3d37; background: #fff0ed; }}
    .muted {{ color: var(--muted); }}
    footer {{ padding: 16px 2px; color: var(--muted); font-size: .82rem; }}
  </style>
</head>
<body>
  <header>
    <h1>Somalia Legal Document Collection</h1>
    <p>Download status and source links for the selected legal documents.</p>
  </header>
  <main>
    <section class="cards" aria-label="Collection summary">
      <div class="card"><span>Documents listed</span><strong>{total}</strong></div>
      <div class="card"><span>PDFs downloaded</span><strong>{successful} / {total}</strong></div>
      <div class="card"><span>Total downloaded</span><strong>{total_bytes:,} bytes</strong></div>
    </section>
    <section class="panel">
      <div class="panel-heading">
        <h2>Documents</h2>
        <p>Failed downloads include the reported error for troubleshooting.</p>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Document</th><th>Source</th><th>Local PDF</th>
            <th>Result</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    <footer>Report generated {html.escape(generated_at)} · Files are stored in data/raw/.</footer>
  </main>
</body>
</html>
"""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_html, encoding="utf-8")
    return report_path


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("Starting Somalia legal document collection...")

    results = []
    for document in SOMALIA_DOCUMENTS:
        download = download_document(document)
        results.append({
            **document,
            **download,
            "collected_at": datetime.now().astimezone().isoformat(),
        })

    METADATA_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path = generate_report(results)
    successful = sum(document["status"] == "success" for document in results)
    print(f"\nDone. {successful}/{len(results)} PDFs downloaded.")
    print(f"Metadata saved to {METADATA_PATH}")
    print(f"HTML report saved to {report_path}")
    if not webbrowser.open(report_path.resolve().as_uri()):
        print("Could not automatically open the report in a browser.")


if __name__ == "__main__":
    run()
