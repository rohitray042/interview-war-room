# Browser-owned workspace

Default: `WAR_ROOM_STORAGE_MODE=browser`.

## Persistence and processing

- Personal profile, extracted resume/JD text, reviews, targets, generated questions, bookmarks, answers, evaluations and learning history are persisted in IndexedDB for the site's origin and browser profile.
- The frontend sends a versioned JSON workspace with each private application operation to `/api/v1/device`. The API restores typed rows into an independent in-memory SQLite database, runs the existing M1-M6 services, returns the updated workspace and closes the database. No supplied SQL or database binary is executed. Public capabilities, content manifest and AI status do not transmit the workspace.
- Existing Alembic migrations build an empty in-memory template containing public curated content. Personal `data/war_room.db` is not opened in browser mode. Temporary SQL work and supported-size multipart uploads stay in memory.
- IndexedDB commits before the UI reports success. Web Locks serialize operations across same-origin tabs, preventing stale snapshots from overwriting another tab's completed changes. Failure to open/save browser storage produces an error; there is no shared-server fallback.
- Backend restart preserves nothing personal: the next browser request supplies its saved state. A disconnected request cannot corrupt server-side personal state because none exists. A lost AI response can require another provider call when retried; there is no cross-restart server idempotency cache.
- Backend requests carry the workspace, so this is not offline execution or end-to-end encryption. Configure HTTPS and avoid request/response body logging or proxy upload spooling when deploying. Gemini/OpenAI receive only the context selected by the existing consent checks, and their retention rules still apply.

## User controls

Profile & settings includes export, validated restore, and confirmed deletion. Backups are readable JSON and contain personal information. Restore and deletion reload open tabs. No automatic export/import of the old local SQLite database is performed.

Different browser profiles/devices start empty. A shared browser profile shares the workspace; use separate browser/OS profiles for separate people. Clearing site storage, incognito-session closure, browser eviction or changing the hostname/port can make saved data unavailable. Export before clearing data or moving to a new URL. IndexedDB requires available site storage; Web Locks require a secure context (HTTPS or localhost).

## Scope and limits

This reuses React, FastAPI, SQLite, existing provider adapters and versioned content. No account system, hosted database or new infrastructure was added. The workspace limit is 12 MB and 20,000 rows, with a 24 MB gateway envelope and existing upload/text limits. Sending/restoring the workspace per private operation is an MVP tradeoff; larger histories need a more granular transport or browser-side execution.

Browser backups are user-editable and include session snapshots/rubrics. Scores are private practice feedback, not tamper-proof credentials or exam results. API keys stay on the backend. Public deployment still needs HTTPS, production host/origin configuration and provider abuse/quota controls; this change does not publish the site.

Legacy `WAR_ROOM_STORAGE_MODE=local_sqlite` preserves old single-user installation/test behavior. It must remain loopback-only and must not serve a public multi-user installation. The default browser mode blocks direct personal REST requests, including guessed document/session IDs, and never accesses legacy personal data.

## Verification

```sh
cd backend
../.venv/bin/pytest
../.venv/bin/ruff check app tests migrations
../.venv/bin/ruff format --check app tests migrations
cd ../frontend
npm run build
PLAYWRIGHT_CHANNEL=chrome npm test
PLAYWRIGHT_CHANNEL=chrome npm test -- --config=playwright.device.config.ts
```

Device API tests cover independent users, guessed IDs, concurrent requests, file upload, restart recovery from browser state, existing-database preservation, malformed backups/foreign keys, gateway recursion, origin validation, private log exclusion and the complete target/interview/evaluation/follow-up/learning path using fake providers. Browser checks cover distinct browser contexts, same-origin tab races, refresh, duplicate submissions, failed AI requests, backup/restore, deletion across tabs, storage-full failure, the complete analyzer workflow and mobile layout.
