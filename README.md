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

---

## Requirements

- **Python 3.12+**
- **Node.js 20+** (and npm)
- **ngrok** (free, required only when connecting real Instagram accounts locally via Meta OAuth)

---

## Quickstart Guide

You can run this project in two modes:
1. **Mock Mode (Instant):** Explore the complete UI and features immediately with rich fixture data without needing any Meta API keys.
2. **Meta Mode (Live Instagram):** Connect your real Instagram Professional account (Business/Creator) using Meta's official Graph API.

---

### Step 1: Clone and Configure Environment

```bash
git clone https://github.com/Sahilssr1/insta_Insights.git
cd insta_Insights
```

Copy the example environment configuration into the `backend/` folder:

- **Linux / macOS:**
  ```bash
  cp .env.example backend/.env
  ```
- **Windows (PowerShell):**
  ```powershell
  Copy-Item .env.example backend\.env
  ```

Open `backend/.env` in your editor:

#### Mode A: Mock Mode (Recommended for first run)
```ini
INSTAGRAM_PROVIDER=mock
JWT_SECRET=any-random-secret-key-at-least-32-chars
```

#### Mode B: Live Instagram (Meta OAuth)
```ini
INSTAGRAM_PROVIDER=meta
META_APP_ID=your_meta_app_id
META_APP_SECRET=your_meta_app_secret
META_REDIRECT_URI=https://your-tunnel-url.ngrok-free.app/api/instagram/callback
JWT_SECRET=any-random-secret-key-at-least-32-chars
```

> **Why ngrok is required for Live Instagram:** Meta's Instagram Business API strictly requires an **HTTPS** callback URL and rejects plain `http://localhost`. For local development, use ngrok to expose your backend over HTTPS (see [Connecting Live Instagram with ngrok](#connecting-live-instagram-with-ngrok) below).

---

### Step 2: Start the Backend

Open a terminal in the project root:

**Linux / macOS:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

- Backend API: `http://localhost:8000`
- Interactive Swagger Docs: `http://localhost:8000/docs`

---

### Step 3: Start the Frontend

Open a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

- Frontend App: `http://localhost:5173`

---

### Step 4: Access the App

1. Open [http://localhost:5173](http://localhost:5173) in your browser.
2. Register a new local account (email & password).
3. Navigate to **Connect** in the sidebar:
   - In **Mock Mode:** Click **Connect Instagram** &rarr; instantly connects with fixture data.
   - In **Meta Mode:** Click **Connect Instagram** &rarr; redirects to Instagram/Meta to authorize.
4. Click **Sync now** (top-right or bottom-left) to fetch your latest insights, reels, views, and reach!

---

## Connecting Live Instagram with ngrok

When using `INSTAGRAM_PROVIDER=meta`, follow these 4 quick steps:

1. **Install and authenticate ngrok (free):**
   - Download from [ngrok.com](https://ngrok.com) or install via package manager (`winget install ngrok.ngrok` / `brew install ngrok`).
   - Add your authtoken:
     ```bash
     ngrok config add-authtoken <your-ngrok-token>
     ```
2. **Start the tunnel to your backend:**
   ```bash
   ngrok http 8000
   ```
   You will receive a public HTTPS URL like:
   `https://xxxx-xxxx.ngrok-free.app`
3. **Update `backend/.env`:**
   Set `META_REDIRECT_URI` to your ngrok URL with `/api/instagram/callback`:
   ```ini
   META_REDIRECT_URI=https://xxxx-xxxx.ngrok-free.app/api/instagram/callback
   ```
4. **Configure Meta Developer Console:**
   - In your [Meta App Dashboard](https://developers.facebook.com/apps), navigate to **Instagram** &rarr; **API setup with Instagram Login**.
   - Under **Valid OAuth Redirect URIs**, paste the exact same URL:
     `https://xxxx-xxxx.ngrok-free.app/api/instagram/callback`
   - Click **Save Changes**.
   - *(Note: Free ngrok domains show a one-time security warning in your browser — simply click **"Visit Site"** once).*

---

## Common Questions & Troubleshooting

- **Account Type Requirement:** The Instagram account must be a **Professional account** (Creator or Business). Personal accounts cannot access Instagram Graph Insights. You can switch for free in Instagram app: *Settings &rarr; Account &rarr; Switch to Professional Account*.
- **"Demographics Unavailable":** Meta's privacy policy only releases audience demographic breakdowns (Age, Gender, City, Country) for accounts with **at least 100 followers**. Accounts under 100 followers will see views, reach, reels, and engagement, while the Demographics tab safely displays an informative placeholder.
- **"Insufficient developer role" during Meta login:** While your Meta app is in Development mode, only users added as **Instagram Testers** can log in. In Meta Console: *App roles &rarr; Roles &rarr; Add Instagram Tester*, then accept the invite on Instagram at [https://www.instagram.com/accounts/manage_access/](https://www.instagram.com/accounts/manage_access/).

---

## Scheduled sync (optional)

The app has no in-process scheduler by design; use cron on the host. The CLI
syncs directly against the database (no HTTP/JWT needed):

```bash
cd backend
./.venv/bin/python -m app.sync_cli             # sync all users
./.venv/bin/python -m app.sync_cli --force     # skip the 5-min throttle
./.venv/bin/python -m app.sync_cli --email you@example.com
```

Example cron (every 30 minutes):

```cron
*/30 * * * * cd /opt/insightboard/backend && ./.venv/bin/python -m app.sync_cli >> /var/log/insightboard-sync.log 2>&1
```

Tokens are refreshed automatically when fewer than 7 days remain.

## Production deployment

```bash
# backend/.env
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

The app **refuses to boot** in production when `JWT_SECRET` is the default,
`TOKEN_ENCRYPTION_KEY` is empty, or `INSTAGRAM_PROVIDER=mock`.

Build the frontend and serve `frontend/dist` from your web server / CDN:

```bash
cd frontend && npm run build
```

Generate a Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

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

## Development checks

```bash
cd backend
.venv/bin/python -m pytest tests/ -q   # 39 tests
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

See [META_INSTAGRAM_SETUP.md](META_INSTAGRAM_SETUP.md) for the Meta developer-console walkthrough.
