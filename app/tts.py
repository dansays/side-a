"""Synthesize the DJ intro to an MP3 via ElevenLabs.

The app does not play audio itself — it writes an MP3 into the served media dir
and Home Assistant plays it on the HomePod by URL. So we just need bytes on disk.
"""

from __future__ import annotations

import re
from pathlib import Path

from elevenlabs.client import ElevenLabs

from .config import get_settings


def _slug(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:maxlen] or "intro"


def synthesize(text: str, *, basename: str) -> Path:
    """Render `text` to an MP3 in the media dir. Returns the file path."""
    settings = get_settings()
    client = ElevenLabs(api_key=settings.elevenlabs_api_key)

    audio = client.text_to_speech.convert(
        voice_id=settings.elevenlabs_voice_id,
        model_id=settings.elevenlabs_model_id,
        text=text,
        output_format="mp3_44100_128",
    )
    data = b"".join(audio)

    filename = f"{_slug(basename)}.mp3"
    dest = settings.media_dir / filename
    dest.write_bytes(data)
    return dest


def public_url(path: Path) -> str:
    """Public URL Home Assistant uses to fetch the MP3 from this app."""
    settings = get_settings()
    return f"{settings.app_public_base_url.rstrip('/')}/media/{path.name}"
