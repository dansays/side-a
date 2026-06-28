"""Orchestrates one trigger: flash -> snapshot -> identify -> intro -> play -> log."""

from __future__ import annotations

import logging
import time

from . import db, intro, tts
from .config import get_settings
from .discogs import DiscogsClient
from .homeassistant import get_ha
from .identify import identify

log = logging.getLogger("side-a.pipeline")


def run_trigger() -> dict:
    """Execute the full flow. Returns a summary dict; raises on hard failure."""
    settings = get_settings()
    ha = get_ha()

    # 1. Flash + snapshot. Always turn the light back off, even on error.
    ha.light_on()
    try:
        time.sleep(settings.flash_delay_seconds)
        image = ha.camera_snapshot()
    finally:
        try:
            ha.light_off()
        except Exception:  # don't mask an upstream error with a light failure
            log.exception("failed to turn flash light off")

    # 2. Identify against the Discogs collection.
    result = identify(image)
    if result is None:
        log.warning("no candidates — is the collection synced?")
        return {"status": "no_match", "collection_count": db.collection_count()}

    log.info(
        "identified %s — %s (method=%s)",
        result.artist,
        result.title,
        result.method,
    )

    # 3. Optional richer metadata for the intro (best effort).
    detail = None
    try:
        detail = DiscogsClient(settings).get_release_detail(result.release_id)
    except Exception:
        log.exception("release detail fetch failed; using basic metadata")

    # 4. Script + synthesize the intro.
    release = db.get_release(result.release_id)
    intro_text = intro.script_intro(release, detail)
    mp3 = tts.synthesize(
        intro_text, basename=f"{result.release_id}-{result.title}"
    )

    # 5. Play on the HomePod via HA, then log the play.
    ha.play_media(tts.public_url(mp3))
    db.log_play(result.release_id, result.artist, result.title)

    return {
        "status": "played",
        "release_id": result.release_id,
        "artist": result.artist,
        "title": result.title,
        "method": result.method,
        "intro": intro_text,
        "media_url": tts.public_url(mp3),
        "candidates": result.candidates,
    }
