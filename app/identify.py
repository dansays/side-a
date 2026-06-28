"""Discogs-gated album identification.

The whole accuracy strategy: never identify open-world. The answer is always one
of the records the user owns, so we (1) read the cover with Claude vision,
(2) fuzzy-match the read against the cached collection, and (3) when the match is
ambiguous, ask Claude to visually confirm against the candidate cover thumbnails.
"""

from __future__ import annotations

import base64
import sqlite3
from dataclasses import dataclass, field

import anthropic
from pydantic import BaseModel
from rapidfuzz import fuzz, process

from . import db
from .config import get_settings

# Accept the top fuzzy match outright only when it's both strong and clearly
# ahead of the runner-up; otherwise fall through to visual confirmation.
ACCEPT_SCORE = 92.0
ACCEPT_MARGIN = 10.0
TOP_K = 5


class CoverRead(BaseModel):
    artist: str
    title: str
    catalog_no: str | None = None
    label: str | None = None
    visible_text: str = ""
    confidence: float = 0.0


class ConfirmResult(BaseModel):
    # release_id of the chosen candidate, or 0 if none match.
    release_id: int


@dataclass
class IdentifyResult:
    release_id: int
    artist: str
    title: str
    method: str  # "fuzzy" | "visual" | "fuzzy-fallback"
    read: CoverRead
    candidates: list[dict] = field(default_factory=list)


def _media_type(image: bytes) -> str:
    if image[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def _image_block(image: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _media_type(image),
            "data": base64.standard_b64encode(image).decode(),
        },
    }


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def read_cover(client: anthropic.Anthropic, image: bytes) -> CoverRead:
    settings = get_settings()
    resp = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    _image_block(image),
                    {
                        "type": "text",
                        "text": (
                            "This is a photo of someone holding a vinyl record up "
                            "to a camera. Read the album cover and extract the "
                            "primary recording artist, the album title, and any "
                            "visible catalog number, label, and other text. If the "
                            "image is unclear, give your best guess and a low "
                            "confidence. Do not invent details that aren't visible."
                        ),
                    },
                ],
            }
        ],
        output_format=CoverRead,
    )
    return resp.parsed_output


def fuzzy_candidates(
    read: CoverRead, k: int = TOP_K
) -> list[tuple[sqlite3.Row, float]]:
    rows = db.all_releases()
    if not rows:
        return []
    by_key: dict[str, sqlite3.Row] = {}
    for row in rows:
        # Last writer wins on duplicate match_keys; acceptable for candidates.
        by_key[row["match_key"]] = row
    query = db.make_match_key(read.artist, read.title)
    matches = process.extract(
        query, list(by_key.keys()), scorer=fuzz.WRatio, limit=k
    )
    return [(by_key[key], score) for key, score, _ in matches]


def visual_confirm(
    client: anthropic.Anthropic,
    image: bytes,
    candidates: list[tuple[sqlite3.Row, float]],
) -> int | None:
    """Ask Claude to pick the matching release from candidate cover thumbnails."""
    thumbs = db.thumb_paths_for([row["release_id"] for row, _ in candidates])
    if not thumbs:
        return None  # nothing to compare visually

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "First image is the photographed record. The remaining images are "
                "candidate album covers from the owner's collection, each labeled "
                "with its release_id. Choose the release_id whose cover matches the "
                "photographed record. If none match, return release_id 0."
            ),
        },
        _image_block(image),
    ]
    for row, _ in candidates:
        path = thumbs.get(row["release_id"])
        if not path:
            continue
        content.append(
            {
                "type": "text",
                "text": f"release_id {row['release_id']}: {row['artist']} — {row['title']}",
            }
        )
        content.append(_image_block(path.read_bytes()))

    settings = get_settings()
    resp = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=512,
        messages=[{"role": "user", "content": content}],
        output_format=ConfirmResult,
    )
    chosen = resp.parsed_output.release_id
    valid = {row["release_id"] for row, _ in candidates}
    return chosen if chosen in valid else None


def identify(image: bytes) -> IdentifyResult | None:
    """Run the full read -> match -> confirm pipeline. None if no candidates."""
    client = _client()
    read = read_cover(client, image)
    candidates = fuzzy_candidates(read)
    if not candidates:
        return None

    cand_dicts = [
        {
            "release_id": row["release_id"],
            "artist": row["artist"],
            "title": row["title"],
            "score": round(score, 1),
        }
        for row, score in candidates
    ]

    top_row, top_score = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0.0

    if top_score >= ACCEPT_SCORE and (top_score - second_score) >= ACCEPT_MARGIN:
        return IdentifyResult(
            release_id=top_row["release_id"],
            artist=top_row["artist"],
            title=top_row["title"],
            method="fuzzy",
            read=read,
            candidates=cand_dicts,
        )

    chosen = visual_confirm(client, image, candidates)
    if chosen is not None:
        row = db.get_release(chosen)
        if row is not None:
            return IdentifyResult(
                release_id=row["release_id"],
                artist=row["artist"],
                title=row["title"],
                method="visual",
                read=read,
                candidates=cand_dicts,
            )

    # Visual confirm declined or unavailable: fall back to best fuzzy guess.
    return IdentifyResult(
        release_id=top_row["release_id"],
        artist=top_row["artist"],
        title=top_row["title"],
        method="fuzzy-fallback",
        read=read,
        candidates=cand_dicts,
    )
