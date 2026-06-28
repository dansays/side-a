"""Orchestrates one trigger.

Lights (WLED via the HA `lights` script) move through three phases:
  flash      -> bright, for the camera snapshot
  processing -> loading animation during identify + intro + TTS
  done       -> revert to neutral as the audio fires
The lights are always returned to `done` on any exit path, so a mid-run failure
never leaves the strip stuck in flash/processing.
"""

from __future__ import annotations

import logging
import time

from . import db, intro, scrobble, tts
from .config import get_settings
from .discogs import DiscogsClient
from .homeassistant import get_ha
from .identify import identify

log = logging.getLogger("side-a.pipeline")


def run_trigger() -> dict:
    """Execute the full flow. Returns a summary dict; raises on hard failure."""
    settings = get_settings()
    ha = get_ha()

    lights_reset = False  # ensure the strip always returns to `done`
    ha.lights("flash")
    try:
        # 1. Flash + snapshot.
        time.sleep(settings.flash_delay_seconds)
        image = ha.camera_snapshot()

        # 2. Identify against the Discogs collection (loading animation).
        ha.lights("processing")
        result = identify(image)
        if result is None:
            log.warning("no candidates — is the collection synced?")
            return {
                "status": "no_match",
                "collection_count": db.collection_count(),
            }

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

        # 5. Revert lights to neutral, then record the play and scrobble.
        #    Do this BEFORE play_media: HA's media_player.play_media blocks until
        #    the HomePod confirms playback (the AirPlay handshake can exceed the
        #    HTTP timeout). We must not let a slow/timed-out confirmation abort
        #    the local log + scrobble — the audio still plays HA-side regardless.
        ha.lights("done")
        lights_reset = True
        db.log_play(result.release_id, result.artist, result.title)

        scrobbled = 0
        try:
            scrobbled = scrobble.scrobble_album(release, detail)
        except Exception:
            log.exception("scrobble step failed")

        # 6. Trigger playback (best effort). A confirmation that exceeds the HTTP
        #    timeout still plays the intro; treat it as non-fatal.
        played = True
        try:
            ha.play_media(tts.public_url(mp3))
        except Exception:
            played = False
            log.warning(
                "play_media did not confirm in time; the HomePod likely still "
                "plays the intro",
                exc_info=True,
            )

        return {
            "status": "played" if played else "play_unconfirmed",
            "release_id": result.release_id,
            "artist": result.artist,
            "title": result.title,
            "method": result.method,
            "intro": intro_text,
            "media_url": tts.public_url(mp3),
            "scrobbled": scrobbled,
            "candidates": result.candidates,
        }
    finally:
        # Never leave the strip stuck mid-sequence (no-match return, or any error).
        if not lights_reset:
            try:
                ha.lights("done")
            except Exception:
                log.exception("failed to reset lights to done")
