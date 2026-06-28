"""Last.fm scrobbling.

Last.fm scrobbles are per-track, so an album play is submitted as one scrobble per
track. The app can't observe the turntable, so the whole album is scrobbled at
identification time, backdated so it "just finished now" — every timestamp lands
in the past, which Last.fm reliably accepts (it drops future ones).

Best-effort by design: a no-op when unconfigured, and never raises into the
trigger flow (the local play log is the source of truth regardless).
"""

from __future__ import annotations

import logging
import sqlite3
import time

import pylast

from .config import get_settings

log = logging.getLogger("side-a.scrobble")

# Discogs tracklist entries that aren't actual playable tracks.
_NON_TRACK_TYPES = {"heading", "index"}


def parse_duration(value: str | None, default: int) -> int:
    """Parse a Discogs duration ('4:33' or '1:02:03') to seconds; default if blank."""
    if not value:
        return default
    parts = value.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return default
    if len(parts) == 2:
        return nums[0] * 60 + nums[1]
    if len(parts) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return default


def _track_artist(track: dict) -> str | None:
    """Track-level artist (for compilations); None to fall back to album artist."""
    artists = track.get("artists") or []
    names = [a.get("name", "").strip() for a in artists if a.get("name")]
    joined = ", ".join(n for n in names if n)
    return joined or None


def extract_tracks(detail: dict, default_secs: int) -> list[dict]:
    """Playable tracks from a Discogs release detail, in order."""
    tracks: list[dict] = []
    for t in detail.get("tracklist") or []:
        if t.get("type_") in _NON_TRACK_TYPES:
            continue
        title = (t.get("title") or "").strip()
        if not title:
            continue
        tracks.append(
            {
                "title": title,
                "artist": _track_artist(t),
                "duration": parse_duration(t.get("duration"), default_secs),
            }
        )
    return tracks


def build_batch(
    tracks: list[dict],
    *,
    album_artist: str,
    album_title: str,
    now: int,
) -> list[dict]:
    """Backdated scrobble dicts so the last track ends at `now`."""
    total = sum(t["duration"] for t in tracks)
    ts = now - total
    batch: list[dict] = []
    for t in tracks:
        batch.append(
            {
                "artist": t["artist"] or album_artist,
                "title": t["title"],
                "album": album_title,
                "album_artist": album_artist,
                "timestamp": ts,
                "duration": t["duration"],
            }
        )
        ts += t["duration"]
    return batch


def scrobble_album(release: sqlite3.Row, detail: dict | None) -> int:
    """Scrobble every track of the identified album. Returns count (0 if skipped)."""
    settings = get_settings()
    if not settings.lastfm_configured:
        log.info("last.fm not configured; skipping scrobble")
        return 0
    if not detail:
        log.warning("no release detail/tracklist; skipping scrobble")
        return 0

    tracks = extract_tracks(detail, settings.default_track_seconds)
    if not tracks:
        log.warning("no scrobblable tracks for '%s'; skipping", release["title"])
        return 0

    batch = build_batch(
        tracks,
        album_artist=release["artist"],
        album_title=release["title"],
        now=int(time.time()),
    )

    try:
        network = pylast.LastFMNetwork(
            api_key=settings.lastfm_api_key,
            api_secret=settings.lastfm_api_secret,
            session_key=settings.lastfm_session_key,
        )
        network.scrobble_many(batch)
    except Exception:
        log.exception("last.fm scrobble failed")
        return 0

    log.info(
        "scrobbled %d tracks: %s — %s",
        len(batch),
        release["artist"],
        release["title"],
    )
    return len(batch)
