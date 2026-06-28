# Deploying Side A to the Synology NAS (Docker)

Side A runs as one Docker container on the NAS. Home Assistant (also on the LAN)
calls `POST /trigger` and fetches the intro MP3 from `GET /media/...`, so the app
only needs to be reachable on the LAN — no public exposure, no PWA/HTTPS needed
(unlike shoppr). This mirrors the shoppr deployment model; the SSH/sudo setup is
shared between the two apps.

## Layout on the NAS

Both live under `/volume1/docker/side-a/`:

- `app/` — the synced repo (this project; where `docker-compose.yml` runs).
- `data/` — the SQLite db, cached thumbnails, and generated MP3s, bind-mounted to
  `/data`. It's a **sibling** of `app/`, so `deploy-nas.sh`'s `rsync --delete` on
  `app/` never touches it. The collection sync and play log survive every rebuild.

## One-time setup

1. **SSH key auth + passwordless sudo-docker on the NAS.** If you already deployed
   shoppr, this is done — `/etc/sudoers.d/shoppr-docker` grants NOPASSWD for the
   docker binary across all compose projects, so nothing more is needed. If not,
   follow shoppr's `DEPLOY.md` → "Remote updates over SSH" once.
2. **Get the code onto the NAS** at `/volume1/docker/side-a/app` (first time):
   ```
   ssh dansays@Synology.local 'mkdir -p /volume1/docker/side-a/app'
   rsync -av --exclude .git --exclude .venv ./ \
     dansays@Synology.local:/volume1/docker/side-a/app/
   ```
   or clone into that path.
3. **Create the env file** on the NAS, next to `docker-compose.yml`:
   ```
   cp .env.example side-a.env      # then fill in all values (see README)
   ```
   Set `APP_PUBLIC_BASE_URL` to the NAS's LAN address, e.g.
   `http://Synology.local:8099`, so HA can fetch `/media/...`.
4. **Pre-create the data dir** (deploy-nas.sh also does this idempotently):
   ```
   ssh dansays@Synology.local 'mkdir -p /volume1/docker/side-a/data'
   ```

## Build & run

**Container Manager GUI:** Project → Create → name `side-a`, path
`/volume1/docker/side-a/app` → it detects `docker-compose.yml` → Build.

**Or via SSH:**
```
cd /volume1/docker/side-a/app && sudo docker compose up -d --build
```

Verify: `curl -s http://Synology.local:8099/healthz` → `{"status":"ok","collection_count":N}`.

## Updating (from the Mac)

With the `docker` share mounted at `/Volumes/docker` (Finder → Connect to Server):
```
./scripts/deploy-nas.sh             # rsync repo → NAS, rebuild, wait for health
./scripts/deploy-nas.sh --no-cache  # force a full rebuild
```

## First run

After the container is up, sync your Discogs collection once:
```
curl -X POST http://Synology.local:8099/sync     # or run `side-a-sync` in the container
```
Re-run any time to pick up new records; thumbnails are cached and fetched once.

## Home Assistant

See the README for the `rest_command` + automation. Point `rest_command.side_a_trigger`
at `http://Synology.local:8099/trigger`.
