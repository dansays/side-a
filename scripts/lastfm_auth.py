#!/usr/bin/env python3
"""One-time: mint a Last.fm session key for scrobbling.

Reads LASTFM_API_KEY / LASTFM_API_SECRET from your .env, prompts for your Last.fm
username + password (used ONLY to fetch the long-lived session key -- neither is
stored), and prints the LASTFM_SESSION_KEY line to paste into your .env.

Get an API key/secret at https://www.last.fm/api/account/create

Usage:
    python scripts/lastfm_auth.py
"""

import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pylast  # noqa: E402


def _load_env_file() -> None:
    """Minimal .env loader so the two API creds are available without exporting."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def main() -> None:
    _load_env_file()
    api_key = os.environ.get("LASTFM_API_KEY")
    api_secret = os.environ.get("LASTFM_API_SECRET")
    if not api_key or not api_secret:
        print("Set LASTFM_API_KEY and LASTFM_API_SECRET in .env first.")
        print("Create them at https://www.last.fm/api/account/create")
        sys.exit(1)

    network = pylast.LastFMNetwork(api_key=api_key, api_secret=api_secret)
    username = input("Last.fm username: ").strip()
    password = getpass.getpass("Last.fm password (not stored): ")

    session_key = pylast.SessionKeyGenerator(network).get_session_key(
        username, pylast.md5(password)
    )

    print("\nAdd this line to your .env (and side-a.env on the NAS):\n")
    print(f"LASTFM_SESSION_KEY={session_key}")


if __name__ == "__main__":
    main()
