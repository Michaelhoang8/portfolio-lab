"""SQLite connection lifecycle and version-one schema."""
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
 priority TEXT NOT NULL CHECK(priority IN ('low','medium','high')),
 status TEXT NOT NULL DEFAULT 'backlog' CHECK(status IN ('backlog','active','done')),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
 detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 reorder_point INTEGER NOT NULL CHECK(reorder_point >= 0));
CREATE TABLE IF NOT EXISTS movements (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 delta INTEGER NOT NULL CHECK(delta != 0), note TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE IF NOT EXISTS movement_requests (
 request_key TEXT PRIMARY KEY, movement_id INTEGER NOT NULL REFERENCES movements(id),
 product_id INTEGER NOT NULL REFERENCES products(id), delta INTEGER NOT NULL,
 note TEXT NOT NULL, stock_after INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS movements_product ON movements(product_id);
CREATE TABLE IF NOT EXISTS experiments (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL,
 a_visitors INTEGER NOT NULL, a_conversions INTEGER NOT NULL,
 b_visitors INTEGER NOT NULL, b_conversions INTEGER NOT NULL,
 CHECK(a_visitors > 0 AND b_visitors > 0),
 CHECK(a_conversions BETWEEN 0 AND a_visitors),
 CHECK(b_conversions BETWEEN 0 AND b_visitors));
"""

def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript(SCHEMA)
        columns = {row['name'] for row in db.execute('PRAGMA table_info(tickets)')}
        for name in ('assignee','due_date'):
            if name not in columns:
                db.execute(f"ALTER TABLE tickets ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        if 'version' not in columns:
            db.execute("ALTER TABLE tickets ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        if 'archived' not in columns:
            db.execute("ALTER TABLE tickets ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))")
        product_columns={row['name'] for row in db.execute('PRAGMA table_info(products)')}
        if 'version' not in product_columns:
            db.execute("ALTER TABLE products ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        db.commit()
        from .rest_api import SCHEMA as REST_SCHEMA
        db.executescript(REST_SCHEMA)

def rows(cursor):
    return [dict(row) for row in cursor.fetchall()]
