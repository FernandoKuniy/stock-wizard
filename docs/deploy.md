# Deploying Stock Wizard

The backend (`api/`) runs on **Render**, the frontend (`web/`) on **Vercel**, and both talk to the
same **Supabase** project (Auth + Postgres). Everything below fits on free tiers.

There's a chicken-and-egg in the config: the backend needs the frontend's URL (for CORS) and the
frontend needs the backend's URL. So the order is: prep Supabase, deploy the backend, deploy the
frontend, then wire the two together. Follow the steps in order.

## 0. Prerequisites

- A Supabase project (the one this repo already points at is fine).
- Free accounts on [Render](https://render.com) and [Vercel](https://vercel.com), each connected
  to the GitHub repo.
- Your API keys ready: Finnhub, Twelve Data, and OpenAI (optional).
- Pick a **`SIGNUP_CODE`**, a long random invite code. This one is a real secret: it's the
  only code that grants an uncapped tutor. Generate one:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(24))"
  ```
- Pick a **`DEMO_SIGNUP_CODE`** too, the one published in the README. Not a secret (it's public
  by design), so make it short and memorable rather than random. It must differ from
  `SIGNUP_CODE`; the API refuses to start if they match. Whatever you choose here has to match
  the README exactly, or the published code simply won't work.

## 1. Supabase

In the project dashboard:

- **Data API → turn it off** (or set Exposed schemas to none). We reach Postgres directly, never
  through PostgREST, so nothing needs it, and leaving it on exposes the tables. RLS is also enabled
  deny-by-default by migration `0006`, but turning the Data API off is the real fix. See
  [decisions.md](decisions.md), 2026-07-28.
- **Authentication → Sign In / Providers**: JWT signing keys must be **asymmetric (ES256/RS256)** —
  the default for new projects. The API rejects the legacy shared HS256 secret.
- **Email confirmation**: leave it **on** for a public environment. It's the only thing stopping
  one person minting unlimited accounts with throwaway addresses, which matters now that an
  invite code is published in the README. Turning it off locally is still fine and makes signup a
  single step. Supabase's built-in mailer is rate-limited and can land in spam; custom SMTP is a
  deliberate non-goal for a demo.
- **Email template**: Authentication → Emails → **Confirm signup**. Point the link at the app's
  own callback so clicking it signs the user in:
  ```
  {{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=signup
  ```
  The default `{{ .ConfirmationURL }}` also works, because `/auth/confirm` handles both shapes,
  but only in the same browser the signup happened in (it's a PKCE exchange against a cookie).
  The `token_hash` form verifies on its own, so signing up on a laptop and opening the email on a
  phone works. That split is common enough to be worth the edit.
- Leave the **Site URL / Redirect URLs** for now; you'll set them to the Vercel URL in step 4.

## 2. Backend on Render

The repo ships a blueprint at [`render.yaml`](../render.yaml).

1. Render dashboard → **Blueprints → New Blueprint Instance** → pick this repo. It reads
   `render.yaml` and creates the `stock-wizard-api` web service (build with uv, migrate on start,
   health check at `/health`).
2. Fill in the env vars it marks as required (`sync: false`): `DATABASE_URL`, `SUPABASE_URL`,
   `FINNHUB_API_KEY`, `TWELVE_DATA_API_KEY`, `OPENAI_API_KEY`, `SIGNUP_CODE`, `DEMO_SIGNUP_CODE`.
   Leave `FRONTEND_ORIGIN` blank or set a placeholder for now, you'll set it in step 4.
   `DEMO_TUTOR_MESSAGE_LIMIT` is already in the blueprint as `1`; don't convert it to
   `sync: false`, because a blank value there can't parse as an integer and the service won't
   boot. Set it to `0` any time you want to switch the demo tutor off.
3. Deploy. The start command runs `alembic upgrade head` before serving, so the schema (including
   the `is_sample` column from migration `0007`) is applied automatically.
4. When it's live, note the URL (e.g. `https://stock-wizard-api.onrender.com`) and check it:
   - `GET /health` → `{"status":"ok"}`
   - `GET /health/ready` → `{"status":"ready"}` (proves the database is reachable)

## 3. Frontend on Vercel

1. Vercel → **Add New → Project** → import this repo.
2. Set the **Root Directory** to `web`. Vercel auto-detects Next.js; no other build config needed.
3. Environment variables:
   - `NEXT_PUBLIC_API_URL` → the Render URL from step 2.
   - `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` → from Supabase's API
     settings (the publishable `sb_publishable_...` key, never the secret one).
4. Deploy, and note the Vercel URL (e.g. `https://stock-wizard.vercel.app`).

## 4. Wire them together

Now that both URLs exist:

- **Render → `FRONTEND_ORIGIN`** → the Vercel URL (no trailing slash), then redeploy the backend.
  This is what lets the browser call the API cross-origin. Comma-separate if you also want a
  preview URL or custom domain allowed.
- **Supabase → Authentication → URL Configuration** → set **Site URL** to the Vercel URL and add
  it under **Redirect URLs**, so confirmation and password emails point at the deployed app, not
  localhost. Signup asks Supabase to send people back to `<your site>/auth/confirm`, and Supabase
  refuses any redirect target that isn't on this list, so add `https://<your-app>.vercel.app/**`
  (and `http://localhost:3000/**` if you want to test the email flow locally). A confirmation link
  that lands on `/login?confirmed=0` instead of the dashboard usually means this list is missing
  the URL.

## 5. Keep it warm

The free Render instance spins down after ~15 minutes idle, and the Supabase project pauses after
7 days with no database activity. The [`keep-warm`](../.github/workflows/keep-warm.yml) workflow
pings `/health/ready` (a `SELECT 1`) to hold both awake.

- GitHub → **Settings → Secrets and variables → Actions → Variables** → add `API_HEALTH_URL` =
  `<Render URL>/health/ready`.

Until the variable is set, the workflow no-ops. Note: GitHub runs scheduled workflows only on the
default branch, and disables the schedule after 60 days with no repo activity.

**The schedule is a request, not a promise.** The cron asks for every 10 minutes; measured over 200
real runs GitHub delivered a median of one every 34 minutes, and once went 112. So each run pings
seven times, five minutes apart, covering about 30 minutes from inside the job, where nothing
throttles it. That is what actually keeps Render warm. A run fails only if *every* ping failed,
since a single 502 while the instance boots is noise, not an outage.

Keeping Supabase unpaused is the easy half: even the worst observed gap is far inside the 7-day
window. Waking Render is the hard half, and the honest ceiling here is that a gap longer than
~30 minutes still lets it go cold. If you want true cadence, point an external uptime monitor at
the same URL. Do not move this into a Supabase `pg_cron` job: a paused project stops running its
own cron, so the watchdog would die with the thing it is meant to protect, and `pg_net` is
fire-and-forget, so nothing would email you when it broke.

## 6. Smoke test

1. Open the Vercel URL, go to **Create account**, and sign up with the invite code.
2. You should land on a dashboard pre-filled with the sample portfolio (from `SEED_NEW_ACCOUNTS`),
   benchmark line and all, with the "this is a sample, hit reset to start your own" banner.
3. Search a ticker, buy a little, confirm it shows up. Open the tutor and ask "how am I doing?".

## 7. Finish the README

Fill in the two placeholders in [`README.md`](../README.md): the live demo URL, and a screenshot or
GIF (the Overview with the benchmark line, a stock page, the tutor panel).
