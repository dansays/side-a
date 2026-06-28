"""Generate expert 'listening notes' for an album using Claude.

The goal is the stuff musicians and seasoned aficionados of the record's genre
hear that a casual listener would miss — a modal shift, a soloist's entrance, a
rhythmic displacement, a production choice, a quoted melody — pinned to the track
and (approximately) when it happens.

The model only has metadata, not the audio, so it's told to favour structural
cues and approximate timestamps over fabricated precision.
"""

from __future__ import annotations

import json
import sqlite3

import anthropic
from pydantic import BaseModel, Field

from .config import get_settings

SYSTEM = (
    "You are a friendly, expert listening guide writing for someone who loves "
    "music but has NO formal training. They can't read music and don't know terms "
    "like 'modal', 'quartal voicing', 'syncopation', or 'the head'. Your job is to "
    "point out the subtle, easy-to-miss things that musicians and lifelong fans "
    "notice — and explain each one in plain, vivid language so a complete beginner "
    "can actually hear it.\n\n"
    "For every observation: say what to listen for in everyday words and describe "
    "what it SOUNDS or FEELS like, not the music theory behind it. If a technical "
    "idea is essential, translate it on the spot — not 'a quartal voicing' but 'a "
    "chord spaced so wide it sounds open and unsettled, like a question left "
    "hanging'; not 'a 12-bar blues' but 'a short chord pattern that loops around "
    "and around'. Never use jargon as a shortcut, and avoid note names, scale "
    "names, time signatures, and insider shorthand.\n\n"
    "Cover what an expert ear catches: a particular instrument slipping in or "
    "answering another, a shift in mood or intensity, the drummer quietly changing "
    "the feel, a moment that sounds 'wrong' but is intentional, the personality of "
    "a solo, or how the recording itself was made. Adapt to the album's genre — "
    "hear it the way a devoted fan of THAT music would, whether it's jazz, "
    "classical, hip-hop, soul, electronic, or rock.\n\n"
    "Pin each note to a moment a beginner can find: a plain-language marker ('the "
    "opening', 'the first trumpet solo', 'when the saxophone takes over', 'the "
    "final minute') or an approximate time like '~1:30'. You are working from "
    "metadata, not the audio, so prefer honest approximate cues and never invent a "
    "precise time, a musician, or an event that wouldn't be on this record. Be "
    "specific and concrete; skip generic praise. Fewer genuinely useful notes beat "
    "padding."
)


class ListeningCue(BaseModel):
    timestamp: str = Field(
        description="A spot a beginner can find: an approximate time like '~1:30' "
        "or a plain marker like 'the opening', 'the first trumpet solo', or 'the "
        "final minute'."
    )
    note: str = Field(
        description="The subtle thing to listen for here, explained in plain, "
        "everyday language a non-musician can understand and actually hear."
    )


class TrackGuide(BaseModel):
    position: str = ""
    title: str
    cues: list[ListeningCue] = Field(default_factory=list)


class ListeningNotes(BaseModel):
    overview: str = Field(
        default="",
        description="One or two sentences framing what makes this album worth a "
        "close listen.",
    )
    tracks: list[TrackGuide] = Field(default_factory=list)


def _tracklist_context(detail: dict | None) -> str:
    if not detail:
        return ""
    tracks = detail.get("tracklist") or []
    lines: list[str] = []
    for t in tracks:
        pos = (t.get("position") or "").strip()
        title = (t.get("title") or "").strip()
        if not title:
            continue
        dur = (t.get("duration") or "").strip()
        line = f"{pos} {title}".strip()
        if dur:
            line += f" ({dur})"
        lines.append(line)
    extra: list[str] = []
    credits = detail.get("extraartists") or []
    named = [
        f"{c.get('name')} — {c.get('role')}"
        for c in credits
        if c.get("name") and c.get("role")
    ]
    if named:
        extra.append("Credits: " + "; ".join(named[:25]))
    notes = detail.get("notes")
    if notes:
        extra.append("Liner notes: " + notes[:1000])
    out = ""
    if lines:
        out += "Tracklist (position, title, duration):\n" + "\n".join(lines)
    if extra:
        out += "\n" + "\n".join(extra)
    return out


def generate(release: sqlite3.Row, detail: dict | None = None) -> dict:
    """Produce listening notes as a plain dict (ListeningNotes serialized)."""
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    facts = {
        "artist": release["artist"],
        "title": release["title"],
        "year": release["year"],
        "label": release["label"],
        "genres": json.loads(release["genres"] or "[]"),
    }
    if detail:
        styles = detail.get("styles") or []
        if styles:
            facts["styles"] = styles

    user_text = (
        "Write listening notes for this album:\n"
        f"{json.dumps(facts, indent=2)}\n"
        f"{_tracklist_context(detail)}\n\n"
        "Cover every track that has something worth hearing, in order."
    )

    resp = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_text}],
        output_format=ListeningNotes,
    )
    return resp.parsed_output.model_dump()
