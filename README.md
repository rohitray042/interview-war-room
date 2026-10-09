# Interview War Room

Phone/public HTTPS access: [Render deployment instructions](docs/DEPLOYMENT.md).

Milestone 6 provider setup and isolated live verification: [LLM setup](docs/LLM-SETUP.md).
Gemini is the primary local AI provider; OpenAI is optional. Configure backend-only
`LLM_PROVIDER`, `GEMINI_API_KEY` and `GEMINI_MODEL`; missing credentials disable AI.

A personal Data Engineering interview preparation workspace. React + TypeScript, FastAPI, SQLModel, Alembic, and SQLite application logic. Personal data is now saved in the user's browser (IndexedDB) by default. Each backend operation uses a disposable, isolated in-memory SQLite database. See [device storage](docs/DEVICE-STORAGE.md) for the privacy boundary and verification.

## What works

- Responsive dashboard shell with light/dark themes and honest empty states.
- Browser-owned profiles, resumes, JD comparisons and interview history, with backup/restore and device-data deletion.
- Three versioned sample questions (SQL, Spark, Snowflake) and one anchored technical rubric, validated at startup.
- Health/capabilities/content-manifest APIs, strict input validation, and privacy-conscious logging.
- Disabled LLM provider interface and strict evaluation/evidence contracts; automated fake-provider tests.
- Resume and JD uploads (PDF/DOCX/TXT) or pasted text, with structured, evidence-linked local extraction.
- Editable reviews, source quotations and character offsets, uncertainty flags, and immutable confirmed revisions.
- Confirmed resume/JD comparison: strong, partial, missing, and needs-revision items, plus explained priorities and suggested preparation topics.
- Duplicate content detection, saved comparisons, optimistic review concurrency, and restart persistence.
- 36 versioned Question Bank prompts with metadata, search/filtering, saved questions, and five persistent practice statuses.
- Evidence-linked personalized sets with fresh AI-drafted hypothetical questions, strict output validation, deterministic metadata and duplicate checks.

Mock interviews now include persistent sessions, answer evaluation, bounded follow-ups, summaries, and evidence-linked weakness aggregation. No hiring score or AI readiness score is exposed. See [architecture and invariants](docs/ARCHITECTURE.md), [Milestone 2 report](docs/MILESTONE-2.md), [Milestone 3 report](docs/MILESTONE-3.md), and [Milestone 4 report](docs/MILESTONE-4.md).

## Mock interview workflow

1. Open **Mock interview**, choose a type, optional confirmed resume/JD comparison, category, difficulty, question count and source.
2. Create and start the session. The interview screen shows the current question. The browser-owned backup contains the full session and rubrics; this is a practice tool, not a secure exam.
3. Submit a text answer. Browser storage commits it before evaluation starts. Retrying submission cannot create a second answer.
4. Review the answer-specific feedback and evidence. Continue through at most two follow-ups per primary question, then the next primary question.
5. Pause/resume or refresh using the session link. Complete the interview to see stored scores, review questions and suggested practice; **Weaknesses** links assessments to their answers.

Without an LLM, curated interviews and answer persistence still work. Retry evaluation after configuring a provider, or explicitly continue unscored. Unscored answers never become fabricated scores or weaknesses. Completed sessions are immutable, including deferred evaluations. Unsubmitted drafts are only held in browser memory; submit before leaving. There is no duration timer.

Interview evaluation uses the same optional provider configuration as Question Bank generation. External evaluation requires consent and sends the current question, rubric, answer and selected source context, not the entire database. Exact answer quotations are validated, but do not prove the model's judgment is correct. These scores assess individual answers, not interview readiness.

## Question Bank workflow

1. Open **Question bank**, filter/search by metadata, and select a question for its expected topics and evaluation focus.
2. Bookmark questions and change their status: New, In Progress, Practiced, Needs Review, or Mastered. These are self-reported practice states, not evaluated proficiency.
3. Confirm and compare a resume/JD in the analyzer. Then select **Generate personalized questions**, choose that comparison and any category/difficulty/type filters. The form shows whether matching JD skills are available.
4. With a configured provider, consent to external processing and generate a set. Gemini writes fresh hypothetical question text while the app supplies approved skill anchors, selected metadata and source links. The detail view shows relevant JD/resume evidence.

The form drafts up to 20 questions per explicit request. It checks count, anchor IDs, duplicate wording and personal-claim language before saving. Category, difficulty, type, expected topics and provenance are controlled by the app; output text is reviewed by the same strict contract. The older bounded-selection API mode remains available. Model wording is not a guarantee of technical correctness, so review generated questions before using them.

## Analyzer workflow

1. Open **Resume & JD** and upload a sanitized resume, or paste its text.
2. Inspect extracted values and source quotations. Filter by section to review missing fields. Add, edit, delete, or flag uncertain items; save your review.
3. Confirm the reviewed resume. Switch to **Job description**, upload/paste it, and review its requirement tiers before confirming.
4. Select **Compare resume & JD** to save an evidence-linked preparation map. Suggested focus areas come from versioned content, not claims about your experience.
5. To revise confirmed information, create an editable revision, save/confirm it, then compare again. Previous confirmed data and comparisons remain unchanged.

Uploads are limited to 5 MB, PDF files to 30 pages, extracted text to 100,000 characters, and expanded DOCX content to 20 MB. Supported TXT encoding is UTF-8. Raw files are not retained; extracted text and analysis data are saved in the browser. Uploads and workspace data are processed temporarily in backend memory. An exact normalized-text hash plus document kind deduplicates uploads within that browser workspace, preserving prior reviews. Layout/text changes may create a new document.

## Extraction and evidence limitations

The default analyzer is explicitly **deterministic/local**, using section headings and a limited technology vocabulary. It does not pretend to be semantic AI. Unrecognized headings/skills may need manual review; years of experience are captured only when explicitly stated, never calculated from overlapping dates. PDF reading order can be imperfect. Scanned/password-protected PDFs are unsupported. DOCX extraction includes body paragraphs/tables but not headers, footers, or text boxes. Mixed required/preferred wording on the same line is marked uncertain rather than guessed.

Extracted items retain exact evidence from the stored extracted text. Edited/added values that lack matching evidence are labeled user-supplied, not resume-verified. Confirmation records your review; it does not independently verify a claim. The local parser cannot prove semantic truth from text. Missing resume evidence does not mean you lack a skill.

Comparison only uses confirmed revisions. Strong matches require an explicit action mentioning the topic in a project/work section; skill-list mentions are partial. Uncertain claims and contextual requirements (years, responsibilities, domain/behavior) need revision. Priority follows the confirmed JD tier: must-have = high, preferred/unspecified = medium, nice-to-have = low. Each row includes matching sources and reasons. Suggested subtopics are preparation guidance, not extra JD requirements.

The LLM boundary accepts strict structured output and rejects invalid quotations or unsupported values. Accepted AI items remain labeled **AI inferred** and require individual review before confirmation. A disabled provider returns 503 without replacing deterministic extraction. Live Gemini and optional OpenAI adapters are available; fake adapters are used only in tests. User correction must still resolve semantic ambiguity even when an excerpt matches exactly.

## Local setup

Tested with Python 3.14.6 and Node 26.4.0. Commands below start in `interview-war-room/`. Use two terminals. Dependencies are locked in `backend/requirements.txt` and `frontend/package-lock.json`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In the second terminal, starting from `interview-war-room/`:

```sh
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5174. Ports 5174 and 8001 must be free. Use the same hostname and port to access your saved browser data: `localhost` and `127.0.0.1` are different storage origins. Both servers bind to loopback; public hosting is not configured. Browser mode blocks direct access to personal REST endpoints and `/docs`; the frontend uses the stateless device gateway. Stop a server with Ctrl+C.

## Configuration and data

Defaults work without a `.env` file or API key; live AI then stays disabled. `.env.example` lists backend configuration. Set `WAR_ROOM_DATABASE_PATH` to change the database location (relative paths resolve from the project root). Select `LLM_PROVIDER=gemini` with `GEMINI_MODEL` and `GEMINI_API_KEY`, or explicitly select OpenAI. Restart the backend after configuration. See [LLM setup](docs/LLM-SETUP.md). Rate limits, timeouts and invalid output return controlled errors without saving questions; optional analyzer AI requires separate consent.

The optional adapter uses the [Responses structured-output API](https://developers.openai.com/api/docs/guides/structured-outputs), with `store=false` and no prompt logging. This does not override the provider's own data-retention policies. No live provider request is part of the test suite.

`WAR_ROOM_STORAGE_MODE=browser` is the default. IndexedDB stores the workspace; localStorage stores only the theme. Different devices/browser profiles have separate data. People sharing the same browser profile share its workspace. Clearing site data, private browsing or browser eviction can remove saved data; use **Profile & settings > Export backup**. Backups are readable JSON, not encrypted. **Restore backup** replaces the current browser workspace after validation; **Delete device data** clears it and refreshes other open tabs.

For application operations, the browser sends its workspace to FastAPI. FastAPI processes it in an isolated in-memory database, returns the result plus updated workspace, and disposes the database. It does not persist personal records or raw uploads on the server in browser mode. This is device-only **persistence**, not offline execution or a promise that data never leaves the device. AI receives selected context only with consent; provider retention policies still apply. No keys are sent to the browser. The current snapshot transport is limited to 12 MB / 20,000 records per workspace.

Existing `data/war_room.db` files are left untouched and are never loaded into browser mode automatically. To use the older single-user local installation explicitly, set `WAR_ROOM_STORAGE_MODE=local_sqlite` and run `alembic upgrade head` before startup. That mode shares a server-side workspace and must not be used for a public multi-user site. `data/` remains Git-ignored. Browser mode runs existing migrations on its empty in-memory template at startup; no disk migration is needed. Tests exercise upgrade/downgrade/re-upgrade on disposable databases.

## Tests and quality checks

From `backend/`:

```sh
../.venv/bin/pytest
../.venv/bin/ruff check app tests migrations
../.venv/bin/ruff format --check app tests migrations
```

From `frontend/`:

```sh
npm run build
npx playwright install chromium
npm test
# Browser-owned storage, isolation, backup/restore and quota-failure checks:
npm test -- --config=playwright.device.config.ts
```

Browser tests start and stop their own frontend and backend on 5174/8001: stop development servers before running them. They use a temporary SQLite database, never your personal database. If Chrome is already installed, `PLAYWRIGHT_CHANNEL=chrome npm test` avoids downloading Chromium. Screenshots are stored under ignored `frontend/test-results/`.

Tests cover persisted profiles across application instances, migration round-trips, database foreign keys, validation, origin restrictions, sample content loading, evidence contracts, follow-up caps, strict fake-provider output, error recovery, themes, and mobile overflow. No external LLM calls.

Analyzer tests additionally cover valid PDF/DOCX, empty/unsupported/malformed/oversized files, missing sections, explicit/ambiguous tiers, comparisons, evidence offsets, corrections, confirmation, stale revisions, restart persistence, unavailable/invalid/fabricated LLM output, duplicate uploads, and profile preservation during the 0001-to-0002 migration. Browser tests exercise the entire upload/review/confirm/compare workflow with a temporary database.

## Layout

```text
backend/app/        API, settings, models, content, provider/schema contracts
backend/migrations/  Versioned database changes
backend/tests/      Unit/API tests and isolated browser-test server
frontend/src/       App shell, API client, theme and styles
frontend/tests/     End-to-end browser checks
content/questions/ Version-controlled curated sample questions
content/question-bank.json  Versioned Question Bank catalog (36 prompts)
content/rubrics/   Version-controlled evaluation criteria
data/             Ignored personal SQLite database
docs/             Architecture and milestone verification
```

Existing installations must run `alembic upgrade head` before restarting the backend. Revision `0003` adds `bank_questions` and `question_targets`, preserving profiles, documents, analyses, and comparisons. The versioned JSON catalog is authoritative; SQLite holds its searchable cache and user state separately from generated records. Curated text/metadata changes require a version increment; removed catalog entries are retired without deleting progress. Back up `data/war_room.db` while the server is stopped before migrating an installation with important data.

Question Bank tests cover catalog validation, metadata/search/filters, status/bookmark persistence, source revalidation, strong/partial/missing priorities, bounded schema validation, fabricated experience rejection, duplicate reuse, migrations, restart persistence, consent, and fake HTTP provider failures. Browser tests use an injected fake provider, never a live API key.

Migration `0004` adds `interview_sessions`, `interview_turns`, and `turn_evaluations`, preserving earlier data. Versioned interview rubrics, type policies and follow-up templates live in `content/interview-policy.json`. Run `alembic upgrade head` before starting this version.

Milestone 4 tests cover idempotent submissions, concurrent state changes, evaluation leases and stale results, offline/invalid providers, evidence validation, follow-up caps, snapshots after question deletion, restart recovery, summaries and weaknesses. Browser tests cover a JD-based interview, all follow-ups, refresh persistence and a network failure after answer storage. All AI responses in tests are fake.

## Evidence-led practice

Open **Weaknesses** to inspect active, improving and resolved topics, positive signals and JD relevance. Each topic links to validated interview evaluations, exact answer excerpts (or explicit absence assessments), questions and a chronological performance timeline. Severity and confidence have separate explanations. A single good answer never resolves a weakness.

**Practice This** opens the existing Question Bank filtered to the exact normalized topic. **Start targeted interview** reuses M4; its summary links back to the learning signal. The catalog may have fewer than five exact-topic questions. No random same-category questions are substituted, and practice availability does not depend on a live provider. New answer evaluation still requires the existing configured provider; unscored answers create no learning signals.

Migration `0005` adds `learning_topics` and `learning_evidence`. Run `alembic upgrade head` before startup. Learning records are a rebuildable index of validated M4 evaluations; no full answers or source documents are copied into the new tables. M1-M4 data and active interviews are preserved. Back up the stopped database before upgrading.

See [Milestone 5 report](docs/MILESTONE-5.md) for exact rules, API contracts, changed files, tests and limitations. Existing real-data test commands remain valid; add `tests/learning.spec.ts` to the opt-in browser commands to exercise M5 with the copied data. Standard tests skip opt-in personal-data scenarios; set the verification environment variables described below to include them.

Live provider configuration is documented in [LLM setup](docs/LLM-SETUP.md).

## Real-data integration verification

See [the real-data verification report](docs/REAL-DATA-VERIFICATION.md) for the persisted M2-to-M4 checks, results and repeatable commands. Legacy v1 target comparisons are now revalidated against their confirmed source documents when listed, preserving their IDs instead of silently hiding them. Invalid source evidence is rejected rather than replaced with demo context.

Opt-in integration tests copy the selected database before use and never send personal data to a live LLM. Test workspaces visibly identify fixture/copied data and simulated evaluations; normal startup uses your persisted data and the configured provider only. No verification answers or fake scores are inserted into your personal workspace.
