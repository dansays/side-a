"""SQLite storage: the cached Discogs collection and the play log.

The collection is a local mirror of the user's Discogs library so identification
can match against a closed set without hitting the API per request. The plays
table is structured so a future "records due for washing by play count" report is
a single GROUP BY query.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS collection (
    release_id   INTEGER PRIMARY KEY,
    artist       TEXT NOT NULL,
    title        TEXT NOT NULL,
    year         INTEGER,
    label        TEXT,
    genres       TEXT,            -- JSON array
    match_key    TEXT NOT NULL,   -- lowercased "artist title", for fuzzy matching
    thumb_url    TEXT,
    cover_url    TEXT,
    thumb_path   TEXT,            -- local cached thumbnail, relative to DATA_DIR
    raw_json     TEXT,            -- full basic_information blob
    synced_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collection_match_key ON collection(match_key);

CREATE TABLE IF NOT EXISTS plays (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id  INTEGER NOT NULL,
    artist      TEXT NOT NULL,
    title       TEXT NOT NULL,
    played_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plays_release ON plays(release_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def make_match_key(artist: str, title: str) -> str:
    return f"{artist} {title}".lower().strip()


def upsert_release(
    conn: sqlite3.Connection,
    *,
    release_id: int,
    artist: str,
    title: str,
    year: int | None,
    label: str | None,
    genres: list[str] | None,
    thumb_url: str | None,
    cover_url: str | None,
    thumb_path: str | None,
    raw: dict,
) -> None:
    conn.execute(
        """
        INSERT INTO collection (release_id, artist, title, year, label, genres,
            match_key, thumb_url, cover_url, thumb_path, raw_json, synced_at)
        VALUES (:release_id, :artist, :title, :year, :label, :genres,
            :match_key, :thumb_url, :cover_url, :thumb_path, :raw_json, :synced_at)
        ON CONFLICT(release_id) DO UPDATE SET
            artist=excluded.artist, title=excluded.title, year=excluded.year,
            label=excluded.label, genres=excluded.genres,
            match_key=excluded.match_key, thumb_url=excluded.thumb_url,
            cover_url=excluded.cover_url,
            thumb_path=COALESCE(excluded.thumb_path, collection.thumb_path),
            raw_json=excluded.raw_json, synced_at=excluded.synced_at
        """,
        {
            "release_id": release_id,
            "artist": artist,
            "title": title,
            "year": year,
            "label": label,
            "genres": json.dumps(genres or []),
            "match_key": make_match_key(artist, title),
            "thumb_url": thumb_url,
            "cover_url": cover_url,
            "thumb_path": thumb_path,
            "raw_json": json.dumps(raw),
            "synced_at": _now(),
        },
    )


def all_releases() -> list[sqlite3.Row]:
    with connect() as conn:
        return list(conn.execute("SELECT * FROM collection"))


def get_release(release_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        cur = conn.execute(
            "SELECT * FROM collection WHERE release_id = ?", (release_id,)
        )
        return cur.fetchone()


def collection_count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM collection").fetchone()[0]


def log_play(release_id: int, artist: str, title: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO plays (release_id, artist, title, played_at) VALUES (?, ?, ?, ?)",
            (release_id, artist, title, _now()),
        )


def set_thumb_path(conn: sqlite3.Connection, release_id: int, path: str) -> None:
    conn.execute(
        "UPDATE collection SET thumb_path = ? WHERE release_id = ?",
        (path, release_id),
    )


def thumb_paths_for(release_ids: Iterable[int]) -> dict[int, Path]:
    """Absolute paths to cached thumbnails for the given releases (if present)."""
    settings = get_settings()
    ids = list(release_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT release_id, thumb_path FROM collection "
            f"WHERE release_id IN ({placeholders}) AND thumb_path IS NOT NULL",
            ids,
        ).fetchall()
    out: dict[int, Path] = {}
    for row in rows:
        p = settings.data_dir / row["thumb_path"]
        if p.exists():
            out[row["release_id"]] = p
    return out
