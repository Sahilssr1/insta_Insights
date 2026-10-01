# InsightBoard — test deployment (Vercel + Render)

Goal: a **live test build** where invited users register, connect Instagram,
and check insights. Storage is **ephemeral by design** (see step 4) — if the
backend sleeps, testers just register and reconnect.

Architecture:

- **Frontend** → Vercel (static Vite build). Already connected to this repo.
- **Backend** → Render free web service (FastAPI). Blueprint: `render.yaml`.

## 1. Deploy the backend on Render

1. Go to dashboard.render.com → **New → Blueprint** → select
   `Sahilssr1/insta_Insights`.
2. Render reads `render.yaml` and pre-fills most values. Fill the manual ones:
   - `TOKEN_ENCRYPTION_KEY` — generate one locally and paste it:
     `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
     (Save it somewhere safe — changing it later invalidates stored tokens.)
   - `META_APP_SECRET` — the Instagram app secret from the Meta console.
   - `META_REDIRECT_URI` — `https://insightboard-api.onrender.com/api/instagram/callback`
     (use your actual Render URL once the service is created; keep `/api/instagram/callback`).
   - `FRONTEND_URL` — your Vercel URL, e.g. `https://insight-board.vercel.app`.
   - `CORS_ORIGINS` — same Vercel URL.
3. Deploy. Note the service URL, e.g. `https://insightboard-api.onrender.com`.

## 2. Point the frontend at the backend

1. In Vercel → your project → **Settings → General** → confirm **Root Directory**
   is `frontend` (so Vercel builds the Vite app, not the repo root).
2. **Settings → Environment Variables** → add
   `VITE_API_URL=https://insightboard-api.onrender.com` (your Render URL, no
   trailing slash).
3. **Deployments → Redeploy** so the new env var is baked into the build.

## 3. Register the callback URL with Meta

Meta rejects unknown redirect URIs, so:

1. Meta console → **My Apps → InsightBoard → Use cases → Customize
   "Manage messaging & content on Instagram" → API setup with Instagram login
   → Step 4 "Set up Instagram business login" → Set up**.
2. Add `https://insightboard-api.onrender.com/api/instagram/callback`
   (your exact Render URL + `/api/instagram/callback`) → **Save**.
   (Your ngrok URI can stay registered alongside it.)

## 4. Ephemeral data (accepted for testing)

The free Render instance has no persistent disk: when it sleeps (~15 min idle)
the SQLite file is wiped. The app rebuilds a fresh database on boot
(migrations run automatically). Testers simply **register again and reconnect** —
nothing to restore.

## 5. Invite testers (still required until App Review)

Deploying does **not** remove Meta's tester rule in Development mode:

1. Tester registers on your live site.
2. They give you their Instagram username (must be a Professional account).
3. Meta console → **App roles → Roles → Add people → Instagram Tester** →
   add them; they accept at `instagram.com/accounts/manage_access/`.
4. They click **Connect Instagram** on your site → authorize → **Sync now**.

## Quick smoke test

1. Open the Vercel URL → register → log in.
2. **Connect** → Connect Instagram → authorize as a tester account.
3. You should land back on `/connect?connected=1` → **Sync now** → dashboard
   fills with real data.

## Later: Oracle Cloud

When testing is verified, move the backend to your Oracle VM: same code, just
set the env vars from `render.yaml` (plus a persistent `DATABASE_URL`, e.g.
Postgres) and point `VITE_API_URL` / Meta redirect URI at the new host.
