# InsightBoard — test deployment (Vercel frontend + ngrok backend)

Goal: a **live test build** where invited users register, connect Instagram,
and check insights. No hosting account or card needed for the backend.

Architecture:

- **Frontend** → Vercel (static Vite build). Already connected to this repo.
- **Backend** → your own machine, exposed via ngrok
  (`https://ranked-student-tadpole.ngrok-free.dev`). Keep it running while
  testers use the site.

## 1. Backend (your machine)

1. Start the API: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
   (from the `backend/` directory).
2. Start the tunnel: `ngrok http 8000`
   (must be the `ranked-student-tadpole` subdomain already registered with Meta).
3. In `backend/.env`, add your Vercel URL to `CORS_ORIGINS`, e.g.
   `CORS_ORIGINS=https://insight-board.vercel.app` (comma-separated if several),
   then restart the API.

## 2. Frontend (Vercel)

1. Vercel → project → **Settings → General** → **Root Directory** = `frontend`.
2. **Settings → Environment Variables** → add
   `VITE_API_URL=https://ranked-student-tadpole.ngrok-free.dev`
   (no trailing slash).
3. **Deployments → Redeploy** so the env var is baked into the build.
   (The frontend sends `ngrok-skip-browser-warning` on API calls so ngrok's
   interstitial page doesn't break them.)

## 3. Meta — nothing to change

`https://ranked-student-tadpole.ngrok-free.dev/api/instagram/callback` is
already registered as a redirect URI. When testers authorize, Meta redirects
their browser to it; if ngrok shows a "Visit Site" interstitial, they click
through once — the OAuth `code`/`state` survive the reload.

## 4. Invite testers (still required until App Review)

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

## Limits of this setup

- Your machine + ngrok must stay on while testers use the site.
- Data lives in the local SQLite file (fine for testing).
- Later: move the backend to Oracle Cloud — same code, just set the env vars
  (`render.yaml` lists them), point `VITE_API_URL` and the Meta redirect URI
  at the new host.
