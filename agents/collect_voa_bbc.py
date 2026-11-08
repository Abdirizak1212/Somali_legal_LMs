import html
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from processing.database import create_tables, get_connection, insert_document  # noqa: E402

VOA_FEED_URL = "https://www.voasomali.com/api/zp-eoerzmit"
BBC_FEED_URL = "https://feeds.bbci.co.uk/somali/rss.xml"
REQUEST_DELAY_SECONDS = 3
REQUEST_TIMEOUT = 30
HEADERS = {
    "User-Agent": "Somali Legal LM research collector (RSS feed reader)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

VOA_BODY_SELECTORS = (
    "[itemprop='articleBody']",
    ".article__body",
    ".article-body",
    ".wsw",
    "#article-content",
    ".body-container",
    "article",
)


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].casefold()


def _child_text(element, names):
    for child in element.iter():
        if child is element or _local_name(child.tag) not in names:
            continue
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def _entry_link(entry):
    for child in entry:
        if _local_name(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
    return ""


def _clean_text(value):
    if not value:
        return ""
    text = BeautifulSoup(html.unescape(value), "html.parser").get_text(" ", strip=True)
    return " ".join(text.split())


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    entries = [
        element for element in root.iter()
        if _local_name(element.tag) in ("item", "entry")
    ]
    parsed = []
    for entry in entries:
        title = _clean_text(_child_text(entry, {"title"}))
        link = _entry_link(entry)
        description = _clean_text(
            _child_text(entry, {"description", "summary", "subtitle"})
        )
        if title and link:
            parsed.append({
                "title": title,
                "url": link,
                "description": description,
            })
    return parsed


def _fetch(session, url):
    try:
        response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)


def _extract_voa_body(response_text):
    soup = BeautifulSoup(response_text, "html.parser")
    for element in soup.select("script, style, nav, header, footer, aside, form"):
        element.decompose()

    for selector in VOA_BODY_SELECTORS:
        body = soup.select_one(selector)
        if body:
            text = body.get_text(" ", strip=True)
            if text:
                return " ".join(text.split())
    return ""


def _existing_urls(source_name):
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT source_url FROM documents WHERE source_name = ?",
            (source_name,),
        ).fetchall()
        return {row["source_url"] for row in rows if row["source_url"]}
    finally:
        connection.close()


def _store_article(source, article, text_content):
    word_count = len(text_content.split())
    insert_document({
        "title": article["title"],
        "doc_type": "news_article",
        "institution": source,
        "language": "so",
        "source_name": source,
        "source_url": article["url"],
        "text_content": text_content,
        "word_count": word_count,
        "somali_word_count": word_count,
        "download_status": "success",
        "provenance": f"{source} Somali RSS: {article['url']}",
    })
    return word_count


def collect_voa(session):
    source = "VOA"
    print(f"\nCollecting VOA Somali articles from {VOA_FEED_URL}...")
    try:
        feed = _fetch(session, VOA_FEED_URL)
        articles = parse_feed(feed.text)
    except (requests.RequestException, ET.ParseError, ValueError) as error:
        print(f"VOA feed unavailable: {error}")
        return {"source": source, "articles": 0, "words": 0}

    existing = _existing_urls(source)
    collected = 0
    total_words = 0
    for article in articles:
        if article["url"] in existing:
            continue
        try:
            response = _fetch(session, article["url"])
            body = _extract_voa_body(response.text)
            if not body:
                print(f"  Skipped (article body not found): {article['url']}")
                continue
            total_words += _store_article(source, article, body)
            existing.add(article["url"])
            collected += 1
        except requests.RequestException as error:
            print(f"  Article request failed ({article['url']}): {error}")

    print(f"VOA: collected {collected} article(s), {total_words:,} words.")
    return {"source": source, "articles": collected, "words": total_words}


def collect_bbc(session):
    source = "BBC"
    print(f"\nCollecting BBC Somali RSS entries from {BBC_FEED_URL}...")
    try:
        feed = _fetch(session, BBC_FEED_URL)
        articles = parse_feed(feed.text)
    except (requests.RequestException, ET.ParseError, ValueError) as error:
        print(f"BBC feed unavailable: {error}")
        return {"source": source, "articles": 0, "words": 0}

    existing = _existing_urls(source)
    collected = 0
    total_words = 0
    for article in articles:
        if article["url"] in existing:
            continue
        # BBC entries are limited to their RSS title and description; article
        # pages are not fetched or copied.
        rss_text = " ".join(
            part for part in (article["title"], article["description"]) if part
        )
        if not rss_text:
            continue
        total_words += _store_article(source, article, rss_text)
        existing.add(article["url"])
        collected += 1

    print(
        f"BBC: collected {collected} RSS entry/entries, {total_words:,} words "
        "(titles and descriptions only)."
    )
    return {"source": source, "articles": collected, "words": total_words}


def run():
    previous_directory = Path.cwd()
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        os.chdir(PROJECT_ROOT)
        create_tables()
        with requests.Session() as session:
            results = (collect_voa(session), collect_bbc(session))

        print("\nWord counts collected this run:")
        for result in results:
            print(
                f"  {result['source']}: {result['articles']} article(s), "
                f"{result['words']:,} words"
            )
    finally:
        os.chdir(previous_directory)


if __name__ == "__main__":
    run()
