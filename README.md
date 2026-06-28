# Side A

Hold a vinyl record up to a camera; Side A identifies the album, scripts a short
"DJ intro," speaks it over a HomePod, and logs the play.

Identification is **gated to your Discogs collection** — the answer is always a
record you actually own, so it's far more accurate than open-ended "ask an AI which
album this is."

## How it works

```
HA button ─► POST /trigger ─► app:
   light_on → wait → HA camera snapshot → light_off
   → Claude reads cover  → fuzzy-match vs synced Discogs collection
                         → (if ambiguous) Claude visually confirms vs cover thumbs
   → Claude scripts a DJ intro from the release metadata
   → ElevenLabs renders it to MP3 (served at /media/<file>.mp3)
   → HA media_player.play_media on the HomePod
   → play logged to SQLite
```

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

The app itself sequences the flash light, snapshot, and playback — the automation
only needs to forward the button press.

## Verification

- **Collection sync:** `side-a-sync` → check `data/side-a.db` and `data/thumbnails/`.
- **Offline identify:** `python scripts/identify_image.py photo_of_an_owned_record.jpg`
  → confirms it resolves to the correct release (try look-alike covers too).
- **End-to-end (no button):** `curl -X POST http://localhost:8099/trigger` → the
  flash light toggles, a snapshot is taken, an MP3 lands in `data/media/`, and the
  intro plays on the HomePod. Check `GET /healthz` for the collection count.

## Deployment

Runs as a Docker container on a Synology NAS, called by Home Assistant over the
LAN. See [DEPLOY.md](DEPLOY.md) and `scripts/deploy-nas.sh`.

## Scope

v1 is identify + intro + log. The `plays` table is structured so a future "records
due for washing by play count" report is a single SQL query — but that reporting
is intentionally out of scope for now.

## Roadmap

- **WLED "flash" sequence.** Today the flash is a single HA `light` entity toggled
  on→snapshot→off (`app/homeassistant.py`, `app/pipeline.py`). Replace it with a
  WLED strip sequence: trigger a bright "flash" preset/config for the snapshot, a
  "loading" animation while the album is being identified + the intro generated,
  then revert to the neutral light setting when playback starts. Implement as
  `flash()` / `loading()` / `restore()` on the HA client (WLED exposes presets via
  `light.turn_on`/`select`/effect attributes or its JSON API), and sequence them in
  `pipeline.run_trigger`.
- **Play-count / "due for washing" report** (deferred, see Scope).
