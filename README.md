# Payroll Validation

AI-assisted payroll validation layer: departments submit payroll data,
deterministic rules and AI-assisted judgement flag exceptions, a payroll
specialist reviews and queries them, and clean data gets exported.

- `backend/` — FastAPI + SQLAlchemy (SQLite for local dev, Postgres in production)
- `frontend/` — React + TypeScript + Vite

## Local development

**Backend**

```bash
cd backend
python -m venv venv
./venv/Scripts/pip install -r requirements.txt   # (or venv/bin/pip on macOS/Linux)
cp .env.example .env   # leave DATABASE_URL unset/commented to use local SQLite
./venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

With no `DATABASE_URL` set, the app uses a local SQLite file and
auto-creates tables + seeds demo data on startup — no migration step needed.
This path is dev-only; see below for production.

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Demo logins (password `password123` for all): `k.owusu@company.com`
(specialist), `a.mensah@company.com` / `j.tetteh@company.com` (submitters).

---

## Deployment

### 1. Supabase (production Postgres)

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **Project Settings → Database → Connection string** and copy the
   **Transaction pooler** string (port `6543`), *not* the direct connection
   (port `5432`). Vercel functions are short-lived serverless processes; the
   pooler is what makes that safe against connection exhaustion.
3. That string is your `DATABASE_URL`. It looks like:
   ```
   postgresql://postgres.xxxxxxxx:[YOUR-PASSWORD]@aws-0-region.pooler.supabase.com:6543/postgres
   ```
4. Apply the schema (from `backend/`, with `DATABASE_URL` exported to your
   shell or in `backend/.env`):
   ```bash
   cd backend
   ./venv/Scripts/python -m alembic upgrade head
   ```
5. Seed demo data (optional, safe to (re-)run — it's idempotent and will not
   duplicate or touch existing rows if a `Department` row already exists):
   ```bash
   ./venv/Scripts/python -m app.seed
   ```

Never commit a real `DATABASE_URL` or `.env` file — both are gitignored.

### 2. Vercel

This is one Vercel project with two [Services](https://vercel.com/docs/services)
defined in the root `vercel.json`: `frontend` (Vite static build) and
`backend` (FastAPI, auto-detected via `backend/asgi.py`). A top-level rewrite
sends `/api/*` to the backend and everything else to the frontend, so both
live on the same domain — no CORS needed in production, and the frontend
never needs a hardcoded backend URL.

**Required environment variables** (Project Settings → Environment Variables,
set for Production — and Preview if you want preview deployments to have a
working API):

| Variable | Value |
|---|---|
| `DATABASE_URL` | The Supabase transaction-pooler string from above |
| `JWT_SECRET` | A long random string — do not reuse the local dev default |
| `ANTHROPIC_API_KEY` | Optional. Omit to run on the built-in AI mock fallback |
| `AI_MODEL` | Optional, defaults to `claude-sonnet-4-5` |
| `CORS_ORIGINS` | Optional. Only needed if you ever call the API from a *different* origin than the deployed frontend |

`VITE_API_URL` does **not** need to be set in Vercel — `frontend/.env.production`
(committed, not a secret) already points the production build at the
same-origin `/api` path.

**Deploy:**

```bash
npx vercel link      # first time only
npx vercel --prod
```

Or connect the Git repository in the Vercel dashboard for automatic deploys.

**How `/api` routing works:** FastAPI's own routes (in `backend/app/main.py`)
are unprefixed — the same code path used by local `uvicorn`. `backend/asgi.py`
is the Vercel-only entrypoint; it mounts that app under `/api`, and Vercel's
`/api/(.*)` rewrite forwards the full path (including the `/api` prefix)
through to it, so nothing in the router files needed to change.

**Running migrations against production:** run `alembic upgrade head` from
your machine (or CI) with `DATABASE_URL` pointed at Supabase — Vercel does not
run migrations automatically on deploy, by design, so a bad migration can
never auto-apply against live data.

### Notes

- SQLite remains fully supported for local dev; it is never used in
  production. `IS_SQLITE` in `backend/app/config.py` gates the auto
  create-tables-and-seed behavior so it only ever runs locally.
- The seed script (`backend/app/seed.py`) checks for an existing `Department`
  row before doing anything, so running it against a database that already
  has real data is a safe no-op.
