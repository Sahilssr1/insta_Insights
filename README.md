# InsightBoard — Instagram Insights Analytics

A production-ready web app where users connect their **own Instagram
Professional accounts** (Business or Creator) using **only Meta's official
OAuth and APIs**. No scraping, no unofficial APIs, no browser automation, and
no Instagram passwords are ever collected.

- **Backend:** FastAPI + async SQLAlchemy + Alembic, JWT app auth, Fernet-encrypted
  Instagram tokens stored server-side.
- **Frontend:** React 18 + TypeScript + Vite, responsive (desktop sidebar /
  mobile bottom nav), hand-rolled SVG charts (no chart dependency).
- **Data honesty:** metrics the official API doesn't provide are shown as
  *unavailable* — never invented.

## Quick start (development)

Prerequisites: Python 3.12+, Node 20+.

```bash
# 1. Configure
cp .env.example .env
# edit .env — at minimum set a JWT_SECRET. Meta credentials are needed
# for a real Instagram connection (see META_INSTAGRAM_SETUP.md).

# 2. Backend
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head        # create tables (also runs on startup)
.venv/bin/uvicorn app.main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

Without Meta credentials you can still explore the whole UI with the
development-only mock provider:

```bash
# in .env
INSTAGRAM_PROVIDER=mock
```

> The mock provider is **refused in production** (`ENVIRONMENT=production`
> raises at startup). It is clearly labelled as fixture data.

## Production deployment

```bash
# .env
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/insightboard
JWT_SECRET=<long random string, min 32 chars>
TOKEN_ENCRYPTION_KEY=<fernet key>   # required in production
INSTAGRAM_PROVIDER=meta
META_APP_ID=<...>
META_APP_SECRET=<...>
META_REDIRECT_URI=https://your-domain.com/api/instagram/callback
FRONTEND_URL=https://your-domain.com
CORS_ORIGINS=https://your-domain.com
```

The app refuses to boot in production when `JWT_SECRET` is the default,
`TOKEN_ENCRYPTION_KEY` is empty, or `INSTAGRAM_PROVIDER=mock`.

Build the frontend and serve `frontend/dist` from your web server / CDN:

```bash
cd frontend && npm run build
```

### Scheduled sync

There is no in-process scheduler by design; use cron/systemd on the host.
The CLI syncs directly against the database (no HTTP/JWT needed):

```bash
# Sync every 30 minutes (example cron; run from the backend directory)
*/30 * * * * cd /opt/insightboard/backend && ./.venv/bin/python -m app.sync_cli >> /var/log/insightboard-sync.log 2>&1
```

Per-account throttling (`SYNC_MIN_INTERVAL_SECONDS`, default 300s) keeps this
safe even if the schedule overlaps with manual "Sync now" clicks; pass
`--force` to skip the throttle, `--email user@example.com` to sync a single
user. Tokens are refreshed automatically when fewer than 7 days remain.

## API overview

All `/api/instagram/*` routes require the app's JWT (`Authorization: Bearer`).

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | Local account auth |
| GET | `/api/instagram/connect` | Returns the Meta authorization URL |
| GET | `/api/instagram/callback` | OAuth callback (Meta redirects here) |
| GET | `/api/instagram/account` | Connected account + safe token status |
| POST | `/api/instagram/disconnect` | Disconnect and delete all synced data |
| GET | `/api/instagram/meta` | Which metrics the official API provides |
| POST | `/api/instagram/sync` | Run a sync (`?force=true` to skip throttle) |
| GET | `/api/instagram/sync/status` | Last sync status |
| GET | `/api/instagram/insights` | Totals + deltas for 7/30/90 days |
| GET | `/api/instagram/insights/timeseries` | Daily series for chosen metrics |
| GET | `/api/instagram/media?sort=` | Media list (`latest,views,likes,comments,shares,saves`) |
| GET | `/api/instagram/media/{id}` | Media detail |
| GET | `/api/instagram/media/{id}/insights` | Lifetime per-media metrics |
| GET | `/api/instagram/audience` | Follower demographics (`age,gender,city,country`) |
| GET | `/api/instagram/media/{id}/comments` | Comments on own media |
| POST | `/api/instagram/comments/{id}/replies` | Reply (ownership-verified) |
| POST | `/api/instagram/comments/{id}/hide?hide=` | Hide/unhide (ownership-verified) |
| DELETE | `/api/instagram/comments/{id}` | Delete (ownership-verified) |

## Development

```bash
cd backend
.venv/bin/python -m pytest tests/ -q   # 33 tests
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
.venv/bin/mypy app

cd frontend
npm run typecheck   # tsc --noEmit
npm run build
```

## Data model & security

- Instagram access tokens are **Fernet-encrypted at rest**; only token status
  (connected/expired/expiry/scopes) is ever exposed via the API.
- OAuth `state` is single-use, SHA-256-hashed in the DB, and expires after 15
  minutes (CSRF protection).
- Comment write operations verify through Meta that the comment's parent media
  is owned by the connected account before acting.
- Syncs are idempotent, throttled, and logged (`instagram_sync_logs`).

## Limitations (honest)

- Insights can lag **up to 48 hours**; data retained ~2 years.
- No per-media insights for items inside albums; story insights are limited.
- `impressions` is deprecated by Meta for media created after 2024-07-02.
- Audience demographics need ≥100 followers.
- Metrics Meta doesn't expose (profile views, website clicks, …) are listed
  under `GET /api/instagram/meta` as unavailable — the UI shows them as such
  instead of guessing.

See `META_INSTAGRAM_SETUP.md` for the Meta developer-console walkthrough.
