import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from processing.database import create_tables, get_connection, insert_document  # noqa: E402

HEADERS = {
    "User-Agent": "Somali Legal LM Research Project (metadata-only news index)"
}
REQUEST_TIMEOUT = 20
PAGE_LIMIT = 3
ARTICLE_DELAY_SECONDS = 0.5
LEGAL_KEYWORDS = ("xeer", "dowlad", "maxkamad", "sharci", "xukuumad")

SITES = (
    {
        "name": "Hiiraan Online",
        "archive_url": "https://www.hiiraan.com/news/",
        "page_url": "https://www.hiiraan.com/news/?page={page}",
    },
    {
        "name": "Garowe",
        "archive_url": "https://www.garowe.com/news",
        "page_url": "https://www.garowe.com/news?page={page}",
    },
    {
        "name": "Caasimada Online",
        "archive_url": "https://www.caasimada.net/category/wararka/",
        "page_url": "https://www.caasimada.net/category/wararka/page/{page}/",
    },
)

ARTICLE_LINK_SELECTORS = (
    "article a[href]",
    "h1 a[href]",
    "h2 a[href]",
    "h3 a[href]",
    ".entry-title a[href]",
    ".post-title a[href]",
)
ARTICLE_BODY_SELECTORS = (
    "[itemprop='articleBody']",
    ".entry-content",
    ".post-content",
    ".article-content",
    ".article-body",
    "article",
    "main",
)


def _canonical_url(url):
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _fetch_html(session, url):
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _archive_page_urls(site, session):
    page_urls = [site["archive_url"]]
    current_url = site["archive_url"]

    while len(page_urls) < PAGE_LIMIT:
        try:
            soup = BeautifulSoup(_fetch_html(session, current_url), "html.parser")
        except requests.RequestException as error:
            print(f"  Archive page failed ({current_url}): {error}")
            break

        next_link = soup.select_one(
            "a[rel='next'], .pagination a.next, .nav-links a.next, "
            "a.next, a.page-numbers.next"
        )
        next_url = urljoin(current_url, next_link["href"]) if next_link else ""
        if not next_url or next_url in page_urls:
            page_number = len(page_urls) + 1
            next_url = site["page_url"].format(page=page_number)
        if next_url in page_urls:
            break

        page_urls.append(next_url)
        current_url = next_url

    return page_urls


def _article_links(soup, archive_url):
    archive_host = urlparse(archive_url).netloc.casefold()
    links = {}

    for selector in ARTICLE_LINK_SELECTORS:
        for anchor in soup.select(selector):
            title = anchor.get_text(" ", strip=True)
            href = anchor.get("href")
            if not title or not href:
                continue
            url = _canonical_url(urljoin(archive_url, href))
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                continue
            if parsed.netloc.casefold() != archive_host:
                continue
            links.setdefault(url, title)

    return links


def _article_text(soup):
    for element in soup.select("script, style, nav, header, footer, aside, form"):
        element.decompose()

    for selector in ARTICLE_BODY_SELECTORS:
        body = soup.select_one(selector)
        if body:
            text = body.get_text(" ", strip=True)
            if text:
                return text
    return soup.get_text(" ", strip=True)


def _matching_keywords(text):
    normalized_text = text.casefold()
    return [keyword for keyword in LEGAL_KEYWORDS if keyword in normalized_text]


def _existing_article_urls(source_name):
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT source_url FROM documents WHERE source_name = ?",
            (source_name,),
        ).fetchall()
        return {row["source_url"] for row in rows if row["source_url"]}
    finally:
        connection.close()


def collect_site(site, session=None):
    session = session or requests.Session()
    site_name = site["name"]
    existing_urls = _existing_article_urls(site_name)
    seen_urls = set()
    matched_count = 0
    inserted_count = 0
    words_reviewed = 0

    print(f"\nCollecting metadata from {site_name}...")
    for page_url in _archive_page_urls(site, session):
        try:
            archive_soup = BeautifulSoup(
                _fetch_html(session, page_url),
                "html.parser",
            )
        except requests.RequestException as error:
            print(f"  Could not read archive page {page_url}: {error}")
            continue

        for article_url, title in _article_links(archive_soup, page_url).items():
            if article_url in seen_urls:
                continue
            seen_urls.add(article_url)
            if article_url in existing_urls:
                continue

            try:
                article_soup = BeautifulSoup(
                    _fetch_html(session, article_url),
                    "html.parser",
                )
            except requests.RequestException as error:
                print(f"  Could not read article {article_url}: {error}")
                continue

            article_text = _article_text(article_soup)
            words_reviewed += len(article_text.split())
            matched = _matching_keywords(f"{title} {article_text}")
            if not matched:
                time.sleep(ARTICLE_DELAY_SECONDS)
                continue

            matched_count += 1
            insert_document({
                "title": title,
                "doc_type": "news_article",
                "institution": site_name,
                "language": "so",
                "source_name": site_name,
                "source_url": article_url,
                "text_content": "",
                "word_count": 0,
                "somali_word_count": 0,
                "download_status": "success",
                "provenance": (
                    "Metadata-only index; full article text is not stored. "
                    f"Matched keywords: {', '.join(matched)}."
                ),
            })
            existing_urls.add(article_url)
            inserted_count += 1
            print(f"  Indexed: {title}")
            time.sleep(ARTICLE_DELAY_SECONDS)

    print(
        f"{site_name}: {inserted_count} matching article(s) indexed; "
        f"{words_reviewed:,} article-body words reviewed (not stored)."
    )
    return {
        "site": site_name,
        "indexed": inserted_count,
        "matches": matched_count,
        "words_reviewed": words_reviewed,
    }


def run():
    previous_directory = Path.cwd()
    try:
        os.chdir(PROJECT_ROOT)
        create_tables()
        with requests.Session() as session:
            for site in SITES:
                try:
                    collect_site(site, session)
                except requests.RequestException as error:
                    print(f"Collection failed for {site['name']}: {error}")
    finally:
        os.chdir(previous_directory)


if __name__ == "__main__":
    run()
