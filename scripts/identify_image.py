#!/usr/bin/env python3
"""Offline identification check: run the pipeline's ID stage on a local image.

Usage:
    python scripts/identify_image.py path/to/album_photo.jpg

Requires a synced collection (run `side-a-sync` first) and ANTHROPIC_API_KEY.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.identify import identify  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    image = Path(sys.argv[1]).read_bytes()
    result = identify(image)
    if result is None:
        print("No candidates — is the collection synced?")
        return
    print(json.dumps(
        {
            "release_id": result.release_id,
            "artist": result.artist,
            "title": result.title,
            "method": result.method,
            "read": result.read.model_dump(),
            "candidates": result.candidates,
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
