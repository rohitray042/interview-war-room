# Optional accounts and cloud workspaces

Guests keep using IndexedDB without signup. Verified account holders use a private
Supabase PostgreSQL workspace through FastAPI. The existing SQLite application logic
runs in a disposable database for each operation. There is no shared user database
inside the Render container and no service-role key in the application.

## Activate on Render

1. Create a Supabase project. Run `supabase/migrations/0001_accounts.sql` in its SQL
   Editor once. This is a separate cloud migration, not an Alembic migration.
2. Enable Email authentication and **Confirm email**. Require passwords of at least
   8 characters. Configure your site's HTTPS URL in Auth settings.
3. In both **Confirm signup** and **Reset password** email templates, include
   `Your verification code: {{ .Token }}`. This app uses typed email codes, not
   URL fragments containing tokens. Configure SMTP appropriate for your users and
   review Supabase's email delivery/rate limits before a public rollout.
4. Set backend Render environment variables:

   ```text
   WAR_ROOM_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
   WAR_ROOM_SUPABASE_ANON_KEY=YOUR_PUBLISHABLE_OR_LEGACY_ANON_KEY
   WAR_ROOM_PUBLIC_ACCESS=true
   WAR_ROOM_STORAGE_MODE=browser
   ```

   Use the project's publishable/anon key, never the service-role/secret key.
   Do not prefix these variables with `VITE_` or commit keys. For local testing,
   configure them in ignored `.env` and restart the backend.
5. Deploy updated code. Open **Profile & account** (settings icon on phones) and
   create an account. Enter the email code, then optionally import guest progress.
6. Test with two real accounts and two devices before announcing availability.

Without the two Supabase variables, the app stays in guest mode and the account
panel reports that cloud accounts are not configured. No automatic cloud upload occurs.

The ignored local `.env` is not deployed to Render. For an existing Render service,
add both Supabase variables under Environment and select Save, rebuild, and deploy.
Blueprint `sync: false` entries prompt during initial setup; they do not populate an
existing service automatically. Verify `/api/v1/cloud/session` returns `enabled: true`
after deployment. Never add a service-role key or Gmail password to these variables.

## Privacy and isolation

- User identity is verified with Supabase Auth; request bodies cannot choose the owner.
- Access/refresh tokens live in same-origin HttpOnly cookies, Secure on the public
  HTTPS deployment, with SameSite=Strict. Tokens are not stored in localStorage or
  returned to frontend JavaScript. Refresh tokens are rotated by Supabase.
- Cloud writes require a trusted Origin. The device gateway rejects recursive access
  to cloud endpoints. Account-switch headers and cross-tab reloads prevent stale tabs
  from silently writing into another account.
- PostgreSQL row-level security restricts reads to `auth.uid()`. Writes use narrowly
  scoped functions that derive the owner from `auth.uid()` and check verified users.
  There is no function argument for selecting another owner. SQL functions pin their
  search path and deny anonymous execution.
- Snapshot saves and answer drafts use revision checks. Conflicting concurrent writes
  return 409; the client does not silently retry over a newer version. Copy an unsaved
  answer before reloading a conflict. This is not real-time collaborative editing.
- Signed-in snapshots and drafts are not cached in IndexedDB. Logout clears account
  cookies and reloads all tabs into the separate guest workspace. The pre-existing
  guest workspace remains on that browser until explicitly deleted.
- Guest import is explicit and only allowed into an empty account. It retains the
  guest copy and never automatically merges or replaces existing cloud work.
- Account deletion requires password confirmation in the UI/backend. PostgreSQL
  cascades deletion to snapshots and drafts. Provider backups/log retention is subject
  to Supabase's policy; this is not a claim of immediate deletion from every backup.
- AI processing still requires the existing separate consent. Cloud storage is not
  end-to-end encryption: your configured hosting/database providers process this data.

Account snapshots contain submitted profiles, extracted resume/JD text, comparisons,
question sets, interview answers and evaluations. Original uploaded files and audio
recordings are not stored. Guest imports and JSON exports currently include submitted
workspace data, not unsubmitted answer drafts. Drafts are saved separately after an
800 ms pause in typing, to the browser for guests or the private account for members.
Wait for **Draft saved** before changing devices. Interrupted requests can require
retrying; do not assume an operation succeeded until the app confirms it.

## Operations and limits

Application account-attempt throttling is in-memory (10 attempts/IP/minute, bounded
to 10,000 entries) and resets on restart. Supabase Auth limits also apply. AI quota
protection is separate and still needs a deployment-level policy for broad public use.
There are no extra Redis, Kafka or orchestration services.

Workspace snapshots retain the 12 MB / 20,000-record limits and current schema
revision. Cloud backup export is supported; restore goes through a guest workspace
and explicit import into an empty account. No merge UI or background device sync:
reload/reopen a session to see another device's changes. There is no offline cloud mode.

## Verification

```sh
cd backend
../.venv/bin/pytest tests/test_cloud.py tests/test_hosting.py
cd ../frontend
PLAYWRIGHT_CHANNEL=chrome npm test -- --config=playwright.device.config.ts tests/accounts.spec.ts
```

Backend tests fake Supabase HTTP, while browser tests fake only the cloud service and
exercise real guest processing. No test uses live credentials. SQL policy tests can
run with an isolated PostgreSQL build via PGlite:

```sh
npm install --prefix /tmp/warroom-sql-check @electric-sql/pglite
node supabase/test_accounts.mjs /tmp/warroom-sql-check/node_modules/@electric-sql/pglite/dist/index.js
```

This executes the migration and checks two-user read isolation, anonymous denial,
revision conflicts, draft conflicts and account-deletion cascades. It does not replace
testing email delivery and policies in the configured Supabase project.

References: [Supabase Auth](https://supabase.com/docs/guides/auth),
[row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security),
[Auth API](https://supabase.github.io/auth/).
