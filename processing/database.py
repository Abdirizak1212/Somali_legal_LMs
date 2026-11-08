import sqlite3
import os
from datetime import datetime

DB_PATH = "data/somali_legal.db"
os.makedirs("data", exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            title               TEXT NOT NULL,
            doc_type            TEXT,
            institution         TEXT,
            legal_domain        TEXT,
            year                INTEGER,
            language            TEXT,
            status              TEXT DEFAULT 'in_force',
            version             TEXT,
            source_name         TEXT,
            source_url          TEXT,
            local_path          TEXT,
            text_content        TEXT,
            word_count          INTEGER DEFAULT 0,
            somali_word_count   INTEGER DEFAULT 0,
            approved            INTEGER DEFAULT 1,
            provenance          TEXT,
            collected_at        TEXT,
            processed_at        TEXT,
            download_status     TEXT DEFAULT 'pending',
            error_message       TEXT
        );

        CREATE TABLE IF NOT EXISTS corpus_stats (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at     TEXT,
            total_documents INTEGER DEFAULT 0,
            total_words     INTEGER DEFAULT 0,
            somali_words    INTEGER DEFAULT 0,
            english_words   INTEGER DEFAULT 0,
            target_words    INTEGER DEFAULT 2000000
        );

        CREATE TABLE IF NOT EXISTS sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            base_url    TEXT,
            access_type TEXT,
            notes       TEXT,
            added_at    TEXT
        );
    """)
    conn.commit()

    # Insert known sources
    conn.execute("""
        INSERT OR IGNORE INTO sources (id, name, base_url, access_type, notes, added_at) VALUES
        (1, 'Somalia Ministry of Justice', 'http://www.moj.gov.so', 'official_partner', 'Primary official source', ?),
        (2, 'Somalia Federal Parliament', 'http://www.parliament.gov.so', 'web', 'Federal legislation', ?),
        (3, 'Constitute Project', 'https://constituteproject.org', 'web', 'Constitution texts', ?),
        (4, 'UNHCR Refworld', 'https://www.refworld.org', 'web', 'Refugee and legal docs', ?),
        (5, 'ILO NATLEX', 'https://natlex.ilo.org', 'web', 'Labour laws', ?),
        (6, 'UN Digital Library', 'https://digitallibrary.un.org', 'web', 'UN documents', ?),
        (7, 'UNDP Somalia', 'https://www.undp.org/somalia', 'web', 'Development documents', ?)
    """, [datetime.now().isoformat()] * 7)
    conn.commit()
    conn.close()
    print(f"Database created: {DB_PATH}")

def insert_document(doc: dict) -> int:
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO documents (
            title, doc_type, institution, legal_domain, year, language,
            status, version, source_name, source_url, local_path,
            text_content, word_count, somali_word_count, approved,
            provenance, collected_at, download_status, error_message
        ) VALUES (
            :title, :doc_type, :institution, :legal_domain, :year, :language,
            :status, :version, :source_name, :source_url, :local_path,
            :text_content, :word_count, :somali_word_count, :approved,
            :provenance, :collected_at, :download_status, :error_message
        )
    """, {
        "title":            doc.get("title", ""),
        "doc_type":         doc.get("doc_type", ""),
        "institution":      doc.get("institution", ""),
        "legal_domain":     doc.get("legal_domain", ""),
        "year":             doc.get("year"),
        "language":         doc.get("language", ""),
        "status":           doc.get("status", "in_force"),
        "version":          doc.get("version", ""),
        "source_name":      doc.get("source_name", ""),
        "source_url":       doc.get("source_url", ""),
        "local_path":       doc.get("local_path", ""),
        "text_content":     doc.get("text_content", ""),
        "word_count":       doc.get("word_count", 0),
        "somali_word_count":doc.get("somali_word_count", 0),
        "approved":         doc.get("approved", 1),
        "provenance":       doc.get("provenance", ""),
        "collected_at":     datetime.now().isoformat(),
        "download_status":  doc.get("download_status", "pending"),
        "error_message":    doc.get("error_message", ""),
    })
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return doc_id

def update_stats():
    conn = get_connection()
    row = conn.execute("""
        SELECT 
            COUNT(*) as total_docs,
            SUM(word_count) as total_words,
            SUM(CASE WHEN language='Somali' THEN word_count ELSE 0 END) as somali_words,
            SUM(CASE WHEN language='English' THEN word_count ELSE 0 END) as english_words
        FROM documents WHERE download_status='success'
    """).fetchone()
    conn.execute("""
        INSERT INTO corpus_stats (recorded_at, total_documents, total_words, somali_words, english_words)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), row[0], row[1] or 0, row[2] or 0, row[3] or 0))
    conn.commit()
    conn.close()

def print_summary():
    conn = get_connection()
    rows = conn.execute("""
        SELECT language, doc_type, COUNT(*) as count, SUM(word_count) as words
        FROM documents WHERE download_status='success'
        GROUP BY language, doc_type ORDER BY language, doc_type
    """).fetchall()
    total = conn.execute(
        "SELECT COUNT(*), SUM(word_count) FROM documents WHERE download_status='success'"
    ).fetchone()
    conn.close()

    print("\n" + "="*55)
    print("  CORPUS STATUS vs TARGET (2,000,000 words)")
    print("="*55)
    print(f"  Total documents : {total[0]}")
    print(f"  Total words     : {total[1] or 0:,} / 2,000,000")
    pct = ((total[1] or 0) / 2000000) * 100
    bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
    print(f"  Progress        : [{bar}] {pct:.1f}%")
    print("-"*55)
    for r in rows:
        print(f"  {r['language']:<12} | {r['doc_type']:<20} | {r['count']} docs | {r['words'] or 0:,} words")
    print("="*55)

if __name__ == "__main__":
    create_tables()
    print_summary()
