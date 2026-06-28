"""FastAPI app: HA calls POST /trigger; HA fetches the intro from GET /media."""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse

from . import db
from .config import get_settings
from .discogs import sync_collection
from .pipeline import run_trigger

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("side-a")

app = FastAPI(title="Side A")


@app.on_event("startup")
def _startup() -> None:
    get_settings().ensure_dirs()
    db.init_db()


def _run_trigger_logged() -> None:
    try:
        result = run_trigger()
        log.info("trigger result: %s", result.get("status"))
    except Exception:
        log.exception("trigger failed")


@app.post("/trigger")
def trigger(background: BackgroundTasks) -> dict:
    """Called by Home Assistant on button press.

    Returns immediately so HA's rest_command doesn't block on the (multi-second)
    identify + TTS work, which runs in the background.
    """
    background.add_task(_run_trigger_logged)
    return {"status": "accepted"}


@app.post("/sync")
def sync(background: BackgroundTasks) -> dict:
    """Kick off a Discogs collection sync in the background."""
    background.add_task(sync_collection)
    return {"status": "accepted"}


@app.get("/media/{filename}")
def media(filename: str) -> FileResponse:
    settings = get_settings()
    # Prevent path traversal: only serve a bare filename inside media_dir.
    path = (settings.media_dir / filename).resolve()
    if path.parent != settings.media_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "collection_count": db.collection_count()}
