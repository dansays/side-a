# Side A

Hold a vinyl record up to a camera; Side A identifies the album, scripts a short
"DJ intro," speaks it over a HomePod, and logs the play.

Identification is **gated to your Discogs collection** — the answer is always a
record you actually own, so it's far more accurate than open-ended "ask an AI which
album this is."

## How it works

```
HA button ─► POST /trigger ─► app:
   lights("flash") → wait → HA camera snapshot
   → lights("processing")
   → Claude reads cover  → fuzzy-match vs synced Discogs collection
                         → (if ambiguous) Claude visually confirms vs cover thumbs
   → Claude scripts a DJ intro from the release metadata
   → ElevenLabs renders it to MP3 (served at /media/<file>.mp3)
   → lights("done") → HA media_player.play_media on the HomePod
   → play logged to SQLite
   → (optional) album scrobbled to Last.fm
```

The WLED strip is driven by an HA script (`HA_LIGHTS_SCRIPT`, default
`script.side_a_lights`) called with an `action` of `flash` / `processing` / `done`
at each phase. The app always returns the strip to `done`, even if a run fails.

Home Assistant owns all physical I/O (button, flash light, camera, HomePod). The
app is a headless Python service designed to run in Docker on a Synology NAS and
talks to HA over its REST API.

## Setup

1. Copy `.env.example` to `.env` and fill in the values:
   - Anthropic + ElevenLabs API keys (and an ElevenLabs voice id)
   - Discogs personal access token, username, and a descriptive User-Agent
   - HA base URL + long-lived access token, and the camera / light / media_player
     entity ids
   - `APP_PUBLIC_BASE_URL` — how HA reaches this app's `/media` route
2. `pip install -e .` (or use the Dockerfile).
3. Sync your collection: `side-a-sync` (or `POST /sync`). Re-run to pick up new
   records; thumbnails are cached and only downloaded once.
4. Run: `uvicorn app.main:app --host 0.0.0.0 --port 8099` (or `docker compose up`).

### Last.fm scrobbling (optional)

When an album is identified, Side A can scrobble the **whole album** to Last.fm.
Since Last.fm scrobbles are per-track, it submits each track from the Discogs
tracklist, **backdated** so the album "just finished now" (keeps every timestamp
in the past, which Last.fm reliably accepts). Where Discogs has no track duration,
`DEFAULT_TRACK_SECONDS` is used. It's a no-op until configured and never blocks the
core flow.

1. Create an API key + secret at https://www.last.fm/api/account/create and put
   them in `.env` (`LASTFM_API_KEY`, `LASTFM_API_SECRET`).
2. Mint a session key once: `python scripts/lastfm_auth.py` → paste the printed
   `LASTFM_SESSION_KEY=...` into `.env`. (Your password is used only to fetch the
   key and is never stored.)

## Home Assistant configuration

Add a `rest_command` and an automation. Example:

```yaml
# configuration.yaml
rest_command:
  side_a_trigger:
    url: "http://synology.local:8099/trigger"
    method: POST
```

```yaml
# automation: button press -> trigger Side A
- alias: "Side A - identify album"
  trigger:
    - platform: state
      entity_id: binary_sensor.album_button   # your button
      to: "on"
  action:
    - service: rest_command.side_a_trigger
```

The app itself sequences the lights (flash/processing/done), snapshot, and
playback — the automation only needs to forward the button press.

## Verification

- **Collection sync:** `side-a-sync` → check `data/side-a.db` and `data/thumbnails/`.
- **Offline identify:** `python scripts/identify_image.py photo_of_an_owned_record.jpg`
  → confirms it resolves to the correct release (try look-alike covers too).
- **End-to-end (no button):** `curl -X POST http://localhost:8099/trigger` → the
  WLED strip cycles flash → processing → done, a snapshot is taken, an MP3 lands in
  `data/media/`, and the intro plays on the HomePod. Check `GET /healthz` for the
  collection count.

## Deployment

Runs as a Docker container on a Synology NAS, called by Home Assistant over the
LAN. See [DEPLOY.md](DEPLOY.md) and `scripts/deploy-nas.sh`.

## Scope

v1 is identify + intro + log. The `plays` table is structured so a future "records
due for washing by play count" report is a single SQL query — but that reporting
is intentionally out of scope for now.

## Roadmap

- ~~**WLED flash sequence.**~~ Done — the strip is driven by the
  `HA_LIGHTS_SCRIPT` HA script with `flash` / `processing` / `done` actions (see
  *How it works*).
- **Play-count / "due for washing" report** (deferred, see Scope).
