# Milestone 3: Question Bank

## Scope and baseline

Inspected the existing API conventions, schema/migrations, content catalog, provider protocol, React shell/analyzer and tests before edits. Baseline: **39 backend tests and 3 browser tests passed**. React + FastAPI + SQLite and all Milestone 1/2 functionality were retained. No new package dependency or infrastructure was introduced. No Milestone 4 work was started.

## Delivered

- 36 representative, versioned curated questions spanning SQL, Python, PySpark, Spark, Snowflake, Databricks, AWS, GCP, BigQuery, Kafka, Data Engineering, modeling, system design, CI/CD, DevOps, GenAI, agent control and behavioral communication.
- Metadata-driven category/skill/difficulty/type/source/status/tag filters, normalized text search and pagination; summary counts and detailed expected topics/evaluation focus.
- SQLite-persisted bookmarks and New/In Progress/Practiced/Needs Review/Mastered states. These are self-reported states, not evaluated scores.
- Personalized sets use existing confirmed resume/JD comparisons, with exact source quotations, offsets, provenance, target IDs and rationale retained in question details.
- Generation revalidates source documents and recomputes comparison, ignoring untrusted/tampered result snapshots. Strong/partial/missing/needs-revision signals and self-reported Needs Review influence deterministic priorities. A JD requirement never establishes candidate experience.
- LLM responses must pass a strict schema and match approved candidate content/metadata/rationale. The entire set is validated before writes. Unknown fields, invented experience, wrong counts, duplicates within a response and invalid priority choices are rejected.
- Normalized text uniqueness, nested transaction conflict handling, and question-target uniqueness reuse existing generated questions rather than duplicating them. Reuse preserves bookmarks/status and reports created/reused counts.
- Optional environment-configured OpenAI adapter behind the existing provider protocol. Disabled by default; explicit consent required for external processing. No model/key hard-coded, no raw prompt storage, and no source text or provider response bodies in failure logs.
- Responsive monochrome Question Bank view, visible loading/error/empty states, detail-panel keyboard focus, and eligible generation counts.

## Database changes

Migration `0003` creates:

- `bank_questions`: stable ID, unique normalized text, validated content JSON, curated/generated source and provenance, version, rationale, status, bookmark, active flag, created/updated timestamps.
- `question_targets`: composite question/target foreign keys and evidence snapshot. One reused question can retain links to multiple targets.

Curated content remains authoritative in `content/question-bank.json`; SQLite contains a cache plus personal state. Generated content is only in SQLite. Same-version curated edits are rejected, version increments update content without resetting state, and removed items are retired.

The real local database was backed up to `data/before-milestone-3.db` and upgraded from `0002` to `0003`. Existing counts remained 1 profile, 2 documents, 2 analyses, and 1 comparison. Startup loaded 36 curated questions. Foreign-key checks returned no violations; `alembic check` found no schema drift. Git ignores both database files and `.env`.

## APIs added

All under `/api/v1/questions`:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/` | Search, filters, pagination |
| GET | `/stats` | Stored counts by source/status and saved count |
| GET | `/metadata` | Available filter values |
| GET | `/{id}` | Question details and source links |
| PATCH | `/{id}` | Validated status/bookmark update |
| POST | `/generation-preview` | Eligible question count/topics without an LLM call |
| POST | `/generate` | Validated personalized set; created/reused counts |

Curated text editing is intentionally version-controlled, not exposed through arbitrary CRUD endpoints. Health reports revision `0003`; capabilities advertise Question Bank and separately report provider availability. Analyzer AI remains independently disabled.

## Verification

- `pytest`: **71 passed**, including the original 39 regression tests (only foundation revision expectations changed).
- `PLAYWRIGHT_CHANNEL=chrome npm test`: **4 passed** against a real isolated API/SQLite database and injected fake LLM.
- `npm run build`: TypeScript and production Vite build passed.
- Ruff lint passed; Ruff format check: **24 files formatted**.
- Prettier checks passed for the changed frontend files.
- Migration upgrade/downgrade/re-upgrade and schema-drift tests passed, preserving analyzer data.
- Restart tests preserved status, bookmarks, generated questions, source links and original profile/analyzer data.
- Browser workflows exercised curated detail, filtering/search, bookmarking, status changes, refresh persistence, personalized Kafka-gap generation and duplicate reuse. Desktop/mobile screenshots were inspected; overflow and browser-error checks passed. Fake generation was used, not a live model.
- Additional coverage: metadata/catalog validation, version bumps, normalized duplicate constraint, missing/empty contexts, stale snapshot revalidation, partial/strong priorities, Java Spark versus PySpark gap, self-reported review boost, fabricated wording/rationale, malformed response, refusal, rate limiting, timeout and consent.

The first new browser test failed to locate an implicitly labelled generation select. Explicit accessible labels fixed the issue; subsequent full runs passed. No test failures remain. Non-failing warnings remain for upstream Starlette TestClient/httpx deprecation and the browser runner's color environment variables.

## Important limitations

1. Generation is **bounded AI-assisted set assembly**, not unrestricted novel question writing. The model selects vetted question wording with neutral framing and deterministic evidence-backed rationale. This is deliberately narrower than open-ended question generation to enforce the no-invented-experience requirement. Free-form authoring is not implemented.
2. Eligible topics/counts are limited by the 36-question catalog and the analyzer's lexical/known-alias matching. Narrow requests such as ten hard Snowflake questions can have fewer eligible candidates; the UI reports the available count. Curated and personalized variants retain separate records; detection covers normalized exact text, not semantic paraphrases.
3. The optional live adapter was tested with fake HTTP responses only. No real API key/model request was made, so live provider availability and output quality are not verified. The running app defaults to disabled generation until configured.
4. Status is shared per question across targets; it is not a per-interview result. Needs Review is self-reported, not a calculated weakness. No new readiness scores exist.
5. Search is designed for a small local bank: SQLite applies structured filters and the resulting rows are searched for normalized text/tag metadata in-process. No large-scale full-text index is included.
6. Existing analyzer limitations remain: lexical grounding does not prove semantic truth or proficiency, and scanned PDFs need prior text conversion. The workspace is local-only and SQLite is not encrypted.

## Exact source files

Created:

```text
backend/app/question_schemas.py
backend/app/questions.py
backend/app/question_api.py
backend/app/providers.py
backend/migrations/versions/0003_question_bank.py
backend/tests/test_questions.py
content/question-bank.json
frontend/src/QuestionBank.tsx
frontend/src/questions.css
frontend/tests/questions.spec.ts
docs/MILESTONE-3.md
```

Modified:

```text
.env.example
README.md
docs/ARCHITECTURE.md
backend/app/config.py
backend/app/main.py
backend/app/models.py
backend/tests/conftest.py
backend/tests/test_foundation.py
backend/tests/serve_browser.py
frontend/src/main.tsx
```

Ignored runtime artifacts include the migrated SQLite database and backup, build output, test caches, and browser screenshots. No personal resume/JD content was added to source control. Milestone 4 remains awaiting approval.
