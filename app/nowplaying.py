"""Ephemeral 'current album' state for the Now Playing web page.

This is deliberately in-memory and not persisted: the page reflects whatever
record was last scanned, nothing more. The pipeline (running in a worker thread)
writes here; the web routes (another thread) read here — so every access is
guarded by a lock.

A monotonic `version` is bumped on every mutation. The web page polls and
re-renders whenever it changes, which covers both transitions we care about: a
new album being scanned, and the (slower) listening notes becoming ready for the
album already on screen.
"""

from __future__ import annotations

import threading
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class CurrentAlbum:
    release_id: int
    artist: str
    title: str
    year: int | None
    label: str | None
    cover_url: str | None
    allmusic_url: str
    genres: list[str] = field(default_factory=list)
    # Listening notes are generated after identification, so they lag the rest of
    # the metadata. status: "pending" | "ready" | "error".
    notes_status: str = "pending"
    notes: dict | None = None
    scanned_at: str = ""


_lock = threading.Lock()
_current: CurrentAlbum | None = None
_version = 0


def _allmusic_url(artist: str, title: str) -> str:
    query = urllib.parse.quote(f"{artist} {title}".strip())
    return f"https://www.allmusic.com/search/albums/{query}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_album(
    *,
    release_id: int,
    artist: str,
    title: str,
    year: int | None,
    label: str | None,
    cover_url: str | None,
    genres: list[str] | None = None,
) -> int:
    """Record a freshly identified album; resets notes to pending. Returns version."""
    global _current, _version
    with _lock:
        _current = CurrentAlbum(
            release_id=release_id,
            artist=artist,
            title=title,
            year=year,
            label=label,
            cover_url=cover_url,
            allmusic_url=_allmusic_url(artist, title),
            genres=genres or [],
            notes_status="pending",
            notes=None,
            scanned_at=_now_iso(),
        )
        _version += 1
        return _version


def set_notes(release_id: int, notes: dict) -> None:
    """Attach generated listening notes, but only if that album is still current.

    A newer scan during generation supersedes the old notes, so we drop stale
    results instead of clobbering the album now on screen.
    """
    global _version
    with _lock:
        if _current is None or _current.release_id != release_id:
            return
        _current.notes = notes
        _current.notes_status = "ready"
        _version += 1


def set_notes_error(release_id: int) -> None:
    global _version
    with _lock:
        if _current is None or _current.release_id != release_id:
            return
        _current.notes_status = "error"
        _version += 1


def snapshot() -> dict:
    """Current state plus version, for the polling endpoint."""
    with _lock:
        if _current is None:
            return {"version": _version, "album": None}
        return {"version": _version, "album": asdict(_current)}
