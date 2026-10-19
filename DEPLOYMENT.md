# WaveBook Deployment Guide (VPS)

WaveBook runs on a single Ubuntu VPS. There is **no Netlify / serverless deployment** —
the backend is a FastAPI app served by systemd + uvicorn behind nginx.

## VPS details

| Item | Value |
| --- | --- |
| SSH alias | `wavebook` (defined in `~/.ssh/config`) |
| Host | `138.68.188.110` |
| User | `root` |
| App directory | `/opt/wavebook/backend` |
| Systemd unit | `wavebook.service` |
| App URL | `https://getwavebook.com` (nginx proxies to `127.0.0.1:8000`) |
| Database | SQLite at `/opt/wavebook/backend/data/wavebook.db` |

## Deploy steps (run from this repo)

```bash
# 1. Commit + push your changes to main (the VPS pulls from GitHub)
git add -A && git commit -m "..." && git push

# 2. SSH to the VPS, pull, install, restart
ssh wavebook "cd /opt/wavebook/backend && \
  git pull --ff-only && \
  .venv/bin/pip install -r requirements.txt -q && \
  systemctl restart wavebook.service"

# 3. Verify
ssh wavebook "systemctl is-active wavebook.service && curl -s http://127.0.0.1:8000/api/health"
```

Expected health response: `{"status":"ok","app":"WaveBook","version":"0.2.2"}`.

## Important rules

- **Always `git pull --ff-only`** — never force-push or rebase the VPS checkout.
- **DB migrations run automatically** on startup: `init_db()` in
  `backend/app/database.py` adds missing columns via `_ensure_column`. After a
  deploy that changes the schema, the first restart applies the migration —
  check the service is active and hit `/api/health` before assuming success.
- **`backup.sh` has a local uncommitted tweak on the VPS** (a `gcloud ls || true`
  fix). Do not overwrite it; never run `git checkout .` / `git reset --hard` on
  the VPS. If a pull ever conflicts, stash it first: `git stash && git pull --ff-only && git stash pop`.
- **Admin access requires the password** (`ADMIN_PASSWORD` in
  `/opt/wavebook/backend/.env`). The `?access=<ADMIN_ACCESS_TOKEN>` link only
  routes to the admin login page — it never auto-logs in.
- **Env vars live in `/opt/wavebook/backend/.env`** on the VPS (gitignored).
  New settings added to `backend/app/config.py` must be added there too.
- Backups run daily via cron (`backup.sh` → private GCS bucket).

## Useful commands

```bash
ssh wavebook "systemctl status wavebook.service"          # service status + logs tail
ssh wavebook "journalctl -u wavebook.service -n 100"      # recent app logs
ssh wavebook "sqlite3 /opt/wavebook/backend/data/wavebook.db 'PRAGMA table_info(businesses);'"
ssh wavebook "cd /opt/wavebook/backend && .venv/bin/python seed_demo.py"   # demo account
```

## Local dev (no VPS involvement)

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env                           # then fill in values
python run.py                                    # http://localhost:8000
```

Tests: `cd backend && .\.venv_test\Scripts\python -m pytest -q`
Flutter: `flutter test` and `flutter analyze` from the repo root.
