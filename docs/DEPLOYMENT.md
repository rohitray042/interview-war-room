# Deploy for phone access

Use one Render Free Docker web service. It serves the React build and FastAPI on
the same HTTPS `onrender.com` URL. No database service or purchased domain is needed
with browser storage. Free services sleep after inactivity, so the first visit can
be slow. Availability, Gemini free quota and hosting free-plan limits are not guaranteed.

## Put this project in its own GitHub repository

Create an **empty** GitHub repository named `interview-war-room` (private is fine).
This folder currently sits inside another repository. Run these commands from the
exact project folder to create a separate repository before adding the remote:

```sh
cd /Users/rohitray/Development/github/interview-war-room
git init -b main
git add .
git status --short
git diff --cached --name-only
git commit -m "Prepare Interview War Room for private browser workspaces"
git remote add origin https://github.com/rohitray042/interview-war-room.git
git push -u origin main
```

Before committing, confirm `.env`, `data/`, backups and personal documents are not
staged. `.gitignore` excludes the existing secrets/data directories; `.dockerignore`
also prevents them from entering the build context. Never push the parent project's
remote for this app. If this folder already has its own repository, inspect its remote
and reuse it instead of repeating initialization.

## Deploy on Render

1. Sign in to https://dashboard.render.com/ and connect GitHub.
2. Choose **New > Blueprint**, select the `interview-war-room` repository and `main`.
3. Render reads `render.yaml`. Verify the service plan is **Free**.
4. Enter your configured `GEMINI_MODEL` and `GEMINI_API_KEY` in Render's environment
   fields. The `.env` file on your laptop is not deployed. Do not put the key in GitHub.
5. Deploy and wait for **Live**. Open the service's assigned HTTPS URL on your phone.
6. The browser asks for credentials: username **warroom**, password is the generated
   `WAR_ROOM_ACCESS_PASSWORD` in the service's Environment settings. Keep it private.

Render provides `RENDER_EXTERNAL_URL`; the app uses it to allow the correct hostname
and origin. For another host, set `WAR_ROOM_PUBLIC_URL=https://your-hostname` and
`WAR_ROOM_ACCESS_PASSWORD` to a strong random value of at least 16 characters.
Public hosting refuses legacy server-database mode and missing/short passwords.
The shared password gates use of the service/API quota; it is not a user account.
Each browser still owns its own data even if several people know the password.

## Phone and desktop data

The deployed URL starts with an empty workspace on each device. Upload a resume
on your phone, or use **Profile & settings > Export backup** on the laptop and
**Restore backup** on the phone. There is no automatic sync. Localhost, the public
URL, different browser profiles and different devices each have separate storage.
Backups are readable personal data; transfer them privately.

The backend processes workspace data in memory. AI receives selected context with
consent. Restarting/sleeping the service does not delete the browser's saved data.
Keep browser backups: clearing site data or private browsing can still remove it.

## Verify the deployment

- Check `/api/v1/health` returns `status: ok`.
- Open the root URL: the access-password prompt should appear before the app.
- After signing in, `/api/v1/storage` should return `mode: browser`.
- Save a profile, refresh, upload a resume and test one short AI evaluation.
- Open a separate browser profile/device and verify its workspace starts empty.
- Never put the Gemini key in the frontend or an environment variable prefixed `VITE_`.

## Local container check

```sh
docker build -t interview-war-room .
docker run --rm -p 8001:10000 --env-file .env interview-war-room
```

The built frontend is served at http://127.0.0.1:8001. This is a different browser
storage origin from the Vite development URL. Docker is required for these checks.

References: [Render web services](https://render.com/docs/web-services),
[Blueprint settings](https://render.com/docs/blueprint-spec),
[Free-tier limits](https://render.com/docs/free).
