# Deploying

The app is a normal container: one web process, no database, no background worker.
It is deployed to [Render](https://render.com) using the blueprint in `render.yaml`,
and the same image runs anywhere else Docker does.

## What gets deployed

| | |
|---|---|
| Process | `uvicorn app:app --host 0.0.0.0 --port $PORT` (see `Dockerfile`) |
| Health check | `GET /api/status` |
| Backend | `offline` - no API key, no cost. Answers are quoted passages with citations. |
| Uploads | off (`QA_ALLOW_UPLOADS=0`), because the URL is public |
| Documents | the four sample files baked into the image at `data/docs/` |

## Deploying to Render

Render needs the code in a Git repository, and the account is yours - these steps
are the ones only you can do.

1. **Push the repository to GitHub** (done, if the repo link is in the README).
2. Sign in at [dashboard.render.com](https://dashboard.render.com) with GitHub.
3. **New > Blueprint**, pick this repository, and Render reads `render.yaml`.
   It proposes one free web service named `genai-qa-assistant`.
4. Approve. The first build takes about 3-5 minutes.
5. The URL is `https://genai-qa-assistant.onrender.com` (Render adds a suffix if
   that name is taken).

**Free plan behaviour:** the service sleeps after roughly 15 minutes without
traffic, and the next visit waits about 30 seconds for it to wake. That is worth
knowing before sending the link to an interviewer - open it yourself a minute
first. The disk is temporary: anything written at runtime disappears on restart.

## Switching on real Claude answers

The deployment runs offline until a key is set. To change that:

1. Render dashboard > the service > **Environment**.
2. Set `ANTHROPIC_API_KEY` to your key, and `QA_BACKEND` to `claude` (or leave it
   `auto`, which picks Claude whenever a key is present).
3. Save. Render restarts the service.

The key is entered in Render's dashboard and stored by Render. It is never in
this repository: `render.yaml` declares the variable with `sync: false`, which
tells Render to ask for the value rather than read it from the file.

**Before doing this on a public URL, understand the cost.** Anyone with the link
can then ask questions that spend your API credit. Options, cheapest first: leave
it offline for the public demo and show real answers locally; or keep the URL
unshared; or add an access gate before setting the key.

## Running the container anywhere else

```bash
docker build -t genai-qa-assistant .
docker run -p 8000:8000 genai-qa-assistant
```

Then open http://127.0.0.1:8000. To run it with real answers and uploads enabled:

```bash
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... -e QA_BACKEND=claude -e QA_ALLOW_UPLOADS=1 genai-qa-assistant
```

Environment variables are listed in `.env.example` and defined in `config.py`.

## Verified

**Live at <https://genai-qa-assistant.onrender.com> since 2026-09-18.** Checked
against the running site: `/api/status` reports the offline backend and 28
passages, an annual-leave question came back with two citations into
`leave-policy.md`, a follow-up in the same session resolved to the carry-over
rule, "What is the dress code?" was declined, `POST /api/upload` returned 403,
the upload box is hidden in the page, and plain http redirects to https.

Before that, built with `docker build` and run locally with Render's settings
(`PORT=10000`, `QA_BACKEND=offline`, `QA_ALLOW_UPLOADS=0`):

- `GET /api/status` reports the offline backend, 28 passages, uploads disabled.
- `POST /api/ask` answered "What is the hotel limit per night?" with a citation
  to `expense-policy.md`.
- `POST /api/upload` returned 403.
- The process runs as `appuser`, not root.

Not verified: behaviour with a real API key on the deployment - it has never run
there with `QA_BACKEND=claude`.
