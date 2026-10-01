# Connecting Instagram — Meta Developer Console Setup

This app uses **only** Meta's official OAuth and APIs ("Instagram API with
Instagram Login"). No scraping, no unofficial APIs, no browser automation, and
we never ask for anyone's Instagram password.

## What you need

- A Meta developer account: https://developers.facebook.com
- An **Instagram Professional account** (Business or Creator). Personal
  accounts cannot use the insights APIs.
- The Instagram account must be usable by the app's configured users
  (see "App review / access levels" below).

## 1. Create the Meta app

1. Go to https://developers.facebook.com/apps → **Create App**.
2. Choose the **"Other"** use case → type **Business**.
3. Name it (e.g. "InsightBoard") and create it.
4. In the app dashboard sidebar, find **"Instagram"** under *Add products* and
   click **Set up**. This enables the *Instagram API with Instagram Login*
   product.

## 2. Configure Instagram settings

In the app dashboard → **Instagram** → **API setup with Instagram Login**:

1. **Valid OAuth Redirect URIs** — add your exact callback URL:
   - **Local development (Requires HTTPS):** Meta strictly rejects `http://localhost` for Instagram Business login. Use a free HTTPS tunnel like [ngrok](https://ngrok.com/):
     ```bash
     # Start the tunnel to your local backend
     ngrok http 8000
     ```
     Copy the generated HTTPS URL (e.g. `https://xxxx.ngrok-free.app`) and enter:
     `https://xxxx.ngrok-free.app/api/instagram/callback`
   - **Production:** `https://your-domain.com/api/instagram/callback`
   - **Important:** Must match `META_REDIRECT_URI` in your `backend/.env` **exactly** (scheme, host, port, path — no trailing slash differences).
   - *(Note: On free ngrok accounts, when redirected back for the first time, click **"Visit Site"** on the one-time ngrok security screen).*
2. **Deauthorize callback URL** (optional):
   `https://your-domain.com/api/instagram/deauthorize`
3. **Data deletion request callback URL** (optional):
   `https://your-domain.com/api/instagram/data-deletion`

## 3. Permissions (scopes)

This app requests exactly these Instagram Login permissions:

| Scope | Why |
|---|---|
| `instagram_business_basic` | Read the profile and media list of the connected account |
| `instagram_business_manage_insights` | Read account & media insights (views, reach, likes, …) |
| `instagram_business_manage_comments` | Read comments; reply, hide or delete comments on the user's own media |

## 4. Copy credentials into `.env`

From the app dashboard → **App settings** → **Basic**:

- **App ID** → `META_APP_ID`
- **App secret** → click *Show* → `META_APP_SECRET` (server-side only; the
  backend never sends it to the browser)

```bash
cp .env.example .env
# then edit .env
```

## 5. Add test users (before app review)

Until the app passes Meta **App Review**, only users with a role on the app
(or added as testers) can connect:

1. Dashboard → **App roles** → **Roles** → **Add people** → choose
   **"Instagram Tester"** → enter the Instagram username (e.g. `nemivibess`)
   → send the invite.
2. **Accept the invite from the Instagram account**: the reliable place is
   https://www.instagram.com/accounts/manage_access/ → **Tester Invites** tab
   on the web (the phone app path Settings → Apps and Websites → Tester
   Invites is not always visible). Until accepted, connecting fails with
   "Insufficient developer role".
3. Each tester must use an **Instagram Professional** account (Business or
   Creator).

> Your Facebook (developer) account and your Instagram account **can be
> completely different** — that is the normal setup. The Facebook account
> owns the app; the Instagram account is added as a tester and authorizes
> the app by logging in with its own Instagram credentials.

> Meta reshuffles the console often: if "Instagram" is not under
> **Add products**, look for **Use cases** in the sidebar → the Instagram API
> use case → **API setup with Instagram login**.

## 6. App review / access levels

- In **development mode**, the permissions above work for app roles/testers.
- For **public** users you must request **Advanced Access** for each
  permission via **App Review** → **Permissions and Features**, and Meta must
  approve the app. This typically requires a screencast showing the login
  flow and how each permission is used, plus a privacy policy URL.

## 7. Verify the connection

1. Start the backend and frontend (see `README.md`).
2. Register an account in the app, open **Connect**, click **Connect Instagram**.
3. You are redirected to instagram.com to authorize — the app never sees your
   password.
4. After approval you land back on `/connect?connected=1`.
5. Press **Sync now** on any page. Insights may take **up to 48 hours** to
   appear for brand-new accounts (Meta's delay, not a bug).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `error=not_configured` | `META_APP_ID` / `META_APP_SECRET` are empty on the server |
| `error=invalid_state` / `state_expired` | The 15-minute authorization window expired, or the URL was reused — start over |
| "URL blocked: This redirect failed" on instagram.com | `META_REDIRECT_URI` is not registered verbatim in the app dashboard |
| `(#10) This message is not available` / permission errors | The user hasn't granted all three scopes, or the app lacks Advanced Access for non-testers |
| Empty insights after sync | Normal for the first ~48h; also check the account is Professional and has activity |
| `account_taken` | That Instagram account is already connected to a different app user |
| Token expired | The app refreshes long-lived tokens automatically on sync; if refresh fails (password change / revoked access), reconnect |

## Security notes

- The OAuth `client_secret` is used **only** in server-to-server calls.
- Instagram access tokens are **Fernet-encrypted at rest** and never sent to
  the frontend; all Meta API calls happen backend-side.
- Comment reply/hide/delete first verifies via Meta that the comment's parent
  media is owned by the connected account (403 otherwise).
