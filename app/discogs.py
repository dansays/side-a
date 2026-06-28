"""Discogs collection sync.

Mirrors the user's collection into SQLite and caches cover thumbnails locally so
identification can match against a closed set. Respects Discogs rate limits
(60 req/min authenticated; image fetches are limited per day, so thumbnails are
downloaded once and reused).
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

from . import db
from .config import Settings, get_settings

API = "https://api.discogs.com"


class DiscogsClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Discogs token={settings.discogs_token}",
                "User-Agent": settings.discogs_user_agent,
            }
        )

    def _get(self, url: str, **kwargs) -> requests.Response:
        """GET with simple rate-limit courtesy based on Discogs headers."""
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        remaining = resp.headers.get("X-Discogs-Ratelimit-Remaining")
        if remaining is not None and int(remaining) <= 2:
            time.sleep(2.0)  # let the per-minute window refill
        else:
            time.sleep(1.0)  # stay comfortably under 60/min
        return resp

    # --- collection ---

    def iter_collection(self):
        """Yield basic_information dicts for every release in folder 0 (All)."""
        page = 1
        while True:
            url = (
                f"{API}/users/{self.settings.discogs_username}"
                f"/collection/folders/0/releases"
            )
            data = self._get(
                url, params={"per_page": 100, "page": page}
            ).json()
            for item in data.get("releases", []):
                yield item.get("basic_information", {})
            pagination = data.get("pagination", {})
            if page >= pagination.get("pages", 1):
                break
            page += 1

    def get_release_detail(self, release_id: int) -> dict:
        """Full release record (tracklist, notes, genres) for intro scripting."""
        return self._get(f"{API}/releases/{release_id}").json()

    def download_thumb(self, release_id: int, url: str) -> str | None:
        """Download a cover thumbnail to DATA_DIR/thumbnails; return relative path."""
        dest = self.settings.thumbnails_dir / f"{release_id}.jpg"
        rel = str(dest.relative_to(self.settings.data_dir))
        if dest.exists():
            return rel
        try:
            resp = self._get(url)
        except requests.HTTPError:
            return None  # likely hit the daily image limit; skip, retry next sync
        dest.write_bytes(resp.content)
        return rel


def _artist_names(basic: dict) -> str:
    artists = basic.get("artists", [])
    names = [a.get("name", "").strip() for a in artists if a.get("name")]
    return ", ".join(names) if names else "Unknown Artist"


def sync_collection() -> int:
    """Pull the whole collection into SQLite + cache thumbnails. Returns count."""
    settings = get_settings()
    db.init_db()
    client = DiscogsClient(settings)

    count = 0
    for basic in client.iter_collection():
        release_id = basic.get("id")
        if not release_id:
            continue
        artist = _artist_names(basic)
        title = basic.get("title", "").strip() or "Untitled"
        labels = basic.get("labels", [])
        label = labels[0].get("name") if labels else None
        thumb_url = basic.get("thumb") or None
        cover_url = basic.get("cover_image") or None

        thumb_path = None
        if thumb_url:
            thumb_path = client.download_thumb(release_id, thumb_url)

        with db.connect() as conn:
            db.upsert_release(
                conn,
                release_id=release_id,
                artist=artist,
                title=title,
                year=basic.get("year") or None,
                label=label,
                genres=basic.get("genres"),
                thumb_url=thumb_url,
                cover_url=cover_url,
                thumb_path=thumb_path,
                raw=basic,
            )
        count += 1

    return count


def main() -> None:
    """`side-a-sync` console entry point."""
    n = sync_collection()
    print(f"Synced {n} releases into {get_settings().db_path}")


if __name__ == "__main__":
    main()
