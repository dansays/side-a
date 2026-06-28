"""Script a short spoken 'DJ intro' for an identified album using Claude."""

from __future__ import annotations

import json
import sqlite3

import anthropic

from .config import get_settings

SYSTEM = (
    "You are a warm, knowledgeable vinyl DJ introducing the next record on a "
    "home hi-fi. Write a short spoken introduction — about 3 to 5 sentences — that "
    "sets the mood and shares a genuinely interesting detail about the album, "
    "artist, or era. It will be read aloud by a text-to-speech voice, so write "
    "only the words to be spoken: no stage directions, no markdown, no emoji, no "
    "track numbers. Be specific and evocative, never generic. Do not state facts "
    "you are unsure of."
)


def _detail_context(detail: dict | None) -> str:
    if not detail:
        return ""
    parts: list[str] = []
    genres = detail.get("genres") or []
    styles = detail.get("styles") or []
    if genres or styles:
        parts.append("Genres/styles: " + ", ".join([*genres, *styles]))
    tracklist = detail.get("tracklist") or []
    titles = [t.get("title") for t in tracklist if t.get("title")]
    if titles:
        parts.append("Tracks: " + ", ".join(titles[:12]))
    notes = detail.get("notes")
    if notes:
        parts.append("Notes: " + notes[:800])
    return "\n".join(parts)


def script_intro(release: sqlite3.Row, detail: dict | None = None) -> str:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    facts = {
        "artist": release["artist"],
        "title": release["title"],
        "year": release["year"],
        "label": release["label"],
        "genres": json.loads(release["genres"] or "[]"),
    }
    user_text = (
        "Introduce this record:\n"
        f"{json.dumps(facts, indent=2)}\n"
        f"{_detail_context(detail)}"
    )

    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_text}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
