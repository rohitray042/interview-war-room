# Milestone 1 delivery

Completed 2026-09-26. Foundation only. No Milestone 2 implementation. No existing workspace files outside `interview-war-room/` were modified.

## Verification

| Check | Result |
| --- | --- |
| Backend automated suite | 9 passed |
| Browser automated suite | 2 passed against real FastAPI and an isolated SQLite database |
| SQLite persistence | Saved profile survives disposal and recreation of application/engine; browser refresh also retains saved fields |
| Migrations | Upgrade, repeated upgrade, downgrade to base, and re-upgrade passed on disposable databases |
| Local database revision | `0001 (head)` |
| Model/schema consistency | `alembic check`: no new upgrade operations detected |
| Frontend | TypeScript check and Vite production build passed |
| Python quality | Ruff lint and format checks passed |
| Sample content | Three questions and one anchored rubric load; invalid references and duplicate IDs rejected |
| API contracts | Strict validation, disabled AI, no secrets in capabilities, hidden rubric details excluded from content manifest |
| Foundation constraints | Evidence source matching, unsupported evidence-free claims, and maximum follow-up contract covered |
| Startup | FastAPI on 127.0.0.1:8001 and Vite on 127.0.0.1:5174 verified |
| Git exclusion | `git check-ignore -v` confirms `data/war_room.db`, `.env`, and `.venv/` ignored |
| Visual checks | Desktop overview and dark mobile profile screenshots inspected; no mobile horizontal overflow |

The backend suite emits one upstream Starlette warning that its TestClient use of httpx is deprecated. Tests pass. Browser output contains a terminal color environment warning; it does not affect app behavior.

## Exact source files created

All paths below are relative to `interview-war-room/`. Every listed source file is new; no pre-existing project source files were modified.

```text
.env.example
.gitignore
README.md
backend/alembic.ini
backend/pyproject.toml
backend/requirements.in
backend/requirements.txt
backend/app/__init__.py
backend/app/config.py
backend/app/content.py
backend/app/contracts.py
backend/app/db.py
backend/app/main.py
backend/app/models.py
backend/migrations/env.py
backend/migrations/script.py.mako
backend/migrations/versions/0001_profile.py
backend/tests/conftest.py
backend/tests/serve_browser.py
backend/tests/test_foundation.py
content/questions/snowflake-query-v1.json
content/questions/spark-shuffle-v1.json
content/questions/sql-dedup-v1.json
content/rubrics/technical-v1.json
docs/ARCHITECTURE.md
docs/MILESTONE-1.md
frontend/index.html
frontend/package.json
frontend/package-lock.json
frontend/playwright.config.ts
frontend/tsconfig.json
frontend/vite.config.ts
frontend/src/api.ts
frontend/src/main.tsx
frontend/src/style.css
frontend/tests/foundation.spec.ts
```

Generated, ignored artifacts: `.venv/`, `data/war_room.db`, frontend dependencies, `frontend/dist/`, Python test/lint caches, and `frontend/test-results/` containing browser result metadata and the three screenshots `overview-desktop.png`, `profile-dark.png`, and `profile-mobile.png`. Test databases use temporary directories rather than the personal database.

## Boundaries

No provider/model calls, document upload processing, question generation, interview sessions, answer submission endpoints, actual evaluation, or progress aggregation yet. The strict contracts and architecture document define the later requirements; runtime interview persistence and deduplication are not claimed as implemented. The only persisted personal entity in this milestone is the profile. Future modules remain visibly unavailable.

Milestone 2 is awaiting user approval.
