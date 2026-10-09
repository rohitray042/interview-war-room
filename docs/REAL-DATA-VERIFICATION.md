# Milestone 4 Real-Data Integration Verification

Verified 2026-09-28. No Milestone 5 work, new infrastructure, dependencies, schema changes or major features.

## Finding and Outcome

**M4 works with persisted M2/M3 data after fixing a legacy-target compatibility bug.** The personal database held a confirmed resume/JD comparison using `evidence-comparison-v1`, but GET `/api/v1/targets` filtered out everything except v2. Consequently, the real target was hidden from interview setup. Existing tests created new v2 comparisons and missed this case.

The production interview engine was not a demo-only implementation. Existing automated interview journeys were fixture-based, and injected fake providers lacked a visible test-workspace notice. Those were verification/provenance gaps, not evidence of hard-coded production scores.

## Actual Inputs

- Existing uploaded PDF resume, 4,843 extracted characters; existing pasted JD, 2,756 characters.
- Two confirmed `local-v1` analysis records and one saved comparison. No replacement fixture documents were created in the real-data tests.
- Persisted comparison contains **3 Strong, 3 Partial, 3 Missing and 4 Needs Revision** items, both before and after source revalidation.
- There is no separate `Gap` enum: Missing represents a documentation gap; Partial and Needs Revision retain their separate meanings. Missing evidence is not proof of missing ability.
- Existing M3 SQLite catalog: 36 curated questions; no pre-existing generated personalized questions or question-target links.
- Existing user session: one active interview with one saved answer and no evaluations. Its content was preserved.
- Provider configuration: disabled; no model or API key configured. No external AI request was made.

Personal content and record IDs are deliberately omitted from this report and source-controlled tests.

## Changes

1. GET `/targets` now revalidates known v1 comparisons using confirmed analyses and exact document evidence, stores the current derived v2 result, and preserves target ID, source IDs and creation time. Invalid sources return 409 without replacing the old result. This is a narrow lazy refresh of a derived comparison, not a schema migration or invented replacement target.
2. Capabilities expose workspace provenance. Normal startup reports `user` with no simulated AI; test startup explicitly reports fixtures or a persisted-data copy. The frontend displays a visible test-data/simulated-evaluation notice. No fake provider can be enabled through production settings.
3. Added opt-in tests that open the source database read-only and copy it to an isolated SQLite database. They fail if real sources are unavailable, rather than substituting demo data. Source database fingerprints verify automated tests leave the original unchanged.
4. Added regression tests for legacy comparison refresh, invalid evidence rejection and normal startup without seeded personal records or fake evaluations.

## End-to-End Evidence

| Check | Result |
| --- | --- |
| Actual resume upload | Original PDF re-uploaded through the real multipart API on a database copy; detected as the existing document, not a new fixture |
| Actual JD and M2 analyses | Existing confirmed records loaded; all claim excerpts checked against their source text and offsets |
| Persisted signals | Stored comparison equals a fresh deterministic comparison; counts above retained |
| M3 selection | Three existing curated questions selected using the real target in disabled mode |
| M3 personalization | Existing M3 generation API used with its fake provider only inside automated tests; three source-linked questions stored on the copy and selected through the personalized source |
| M4 planning | Three distinct primary questions with the real target/analysis references and nonempty matching JD evidence in snapshots |
| Answer persistence | Three answers in disabled mode; nine answers in mocked mode; saved text checked against storage/API results |
| Evaluation context | Captured provider request matches the current stored question, submitted answer, rubric and source context; source evidence matches the actual JD/resume documents |
| Follow-ups | Two per primary, six total, persisted parent relationships; existing cap/concurrency regressions also pass |
| Summary | Session ID, primary/turn/follow-up counts and averages checked against that session's stored evaluations |
| Weaknesses | Every occurrence checked against an existing evaluation/turn and matching topic assessment; no new weaknesses in disabled mode |
| Browser refresh | Refresh during active sessions retains the exact turn and submitted answer; completed summaries survive reload |
| Application restart | Fresh app/engine opens the copied SQLite database before evaluation and after completion; answers and summary unchanged |
| Actual backend process restart | Normal backend stopped and restarted; existing personal session response SHA-256 identical before/after, including its saved answer |
| Production UI isolation | Normal server reports user data, simulated AI false and evaluation disabled; no successful fake evaluation was inserted into it |

The mocked browser run completed 3 primary questions plus 6 follow-ups. Its scores demonstrate storage/aggregation, **not the user's performance**. The disabled browser run completed 3 answers explicitly unscored, with null average and no invented practice areas. Verification answers are clearly identified test answers, not answers attributed to the user.

## Audit of Demo Dependencies

Searched production backend/frontend for demo/fixture/fake/sample/fallback references, identifier literals, question planning, source-context assembly, answer handling and summary/statistics calculations.

- No hard-coded user resume IDs, JD IDs, demo session IDs, fallback answer text or fake evaluation result path found in production.
- Interview planning reads `bank_questions`, `question_targets` and confirmed analyses/documents. Personalization reuses M3; no second generator was added.
- Summary and weakness services read `interview_turns` and `turn_evaluations`; overview counts come from `/interviews/stats`. Readiness remains explicitly unassessed.
- The three historical foundation sample questions remain versioned content for the manifest/startup checks. They do not supply interview turns or personal scores.
- The 36-question versioned curated bank and follow-up templates are intentional product content, not demo candidate data.
- Fixed profile skill suggestions are choices, not assertions about user experience or evaluation inputs.
- Fake providers, synthetic documents and test answers remain under test code. The browser test server always uses an isolated database and explicitly disables real provider configuration.

## Test Results

Baseline before changes: **102 backend tests, 6 browser tests passed**.

Final checks:

- **108 backend tests passed**, including all M1-M4 regressions and enabled real-data tests. Includes original PDF upload, disabled/mocked integration, legacy targets and provenance.
- Full frontend/browser regression: **6 passed, 1 intentionally skipped**. The opt-in real-data test skips when no source database is provided.
- Real-data browser run with mocked provider: **1 passed** (run separately with the persisted database copy).
- Real-data browser run with disabled provider: **1 passed** (same copy-based workflow, no fake success).
- Ruff lint and format checks: passed; 35 Python files formatted.
- Prettier check on changed frontend files: passed.
- TypeScript checking and Vite production build: passed.
- `alembic check`: no new upgrade operations; SQLite integrity `ok`, zero foreign-key violations.
- Database, backup, `.env` and browser artifacts remain ignored by Git.
- Mobile test notice/summary screenshot inspected; overflow checks passed.

This repo's frontend test command is Playwright; there is no separate React unit-test runner. The two real-data browser modes are additional runs, not hidden skips in the regression result.

Failures found and resolved: initial real-data tests failed because the v1 target was filtered out; an invalid-source regression prompted explicit evidence validation on legacy refresh; one frontend regression found the provenance notice competing with the existing profile-save live status, fixed by giving the static notice a `note` role. Final checks above are green. Existing Starlette/httpx deprecation and browser color-environment warnings remain non-failing.

## Data Safety and Startup

Before refreshing the actual target, backed up the database to ignored `data/before-real-data-verification.db`. After verification, every table except `targets` is byte-for-byte equivalent at the row-value level to that backup: profiles, documents, analyses, bank questions, target links, sessions, turns, evaluations and schema revision. Only the derived target result was refreshed to v2; counts and source records are unchanged.

The normal frontend/backend are running at `http://127.0.0.1:5174` and `http://127.0.0.1:8001`. Health through the frontend proxy reports milestone 4, database ready, schema 0004. Your existing active interview was neither completed nor overwritten by verification.

## Reproduce

Stop development servers before browser tests. From `backend/`, with paths to the database and original PDF:

```sh
WAR_ROOM_VERIFY_DATABASE=/absolute/path/to/data/war_room.db \
WAR_ROOM_VERIFY_RESUME=/absolute/path/to/resume.pdf \
../.venv/bin/pytest
```

From `frontend/`:

```sh
PLAYWRIGHT_CHANNEL=chrome npm test
WAR_ROOM_VERIFY_DATABASE=/absolute/path/to/data/war_room.db \
PLAYWRIGHT_CHANNEL=chrome npm test -- tests/persisted.spec.ts
WAR_ROOM_VERIFY_DATABASE=/absolute/path/to/data/war_room.db \
WAR_ROOM_VERIFY_OFFLINE=1 PLAYWRIGHT_CHANNEL=chrome npm test -- tests/persisted.spec.ts
npm run build
```

Never point the normal test server directly at the personal database. `WAR_ROOM_VERIFY_DATABASE` is consumed only by test code and copied first; it does not configure production fake providers. These local copies contain personal data and should be treated as sensitive, including pytest temporary directories and ignored screenshots.

## Files Changed

Created:

```text
backend/tests/persisted_data.py
backend/tests/test_persisted_integration.py
backend/tests/test_legacy_targets.py
frontend/tests/persisted.spec.ts
docs/REAL-DATA-VERIFICATION.md
```

Modified:

```text
backend/app/analyzer_api.py
backend/app/main.py
backend/tests/serve_browser.py
frontend/src/main.tsx
frontend/src/style.css
README.md
```

## Remaining Limits

Live AI quality/availability is unverified because no provider is configured. Mocked evaluations prove the integration contract, not semantic scoring accuracy. Personalized generation was verified on real source data in an isolated copy, not added to the user's bank as a fake production result. Source-evidence checks do not guarantee an LLM's judgment is correct. Broader interviews can include general curated questions where no matching JD topic exists; the three real-data questions tested here all carried matching target context. Existing catalog coverage, untimed text-only interaction and in-memory unsubmitted drafts remain unchanged.

**Stopped after verification. Milestone 5 is not started.**
