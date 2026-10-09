# Milestone 5: Adaptive Evaluation & Weakness Intelligence

Verification report, 2026-10-01. React + FastAPI + SQLite retained. No new dependency, production LLM provider, infrastructure or Milestone 6 feature.

## Delivered Loop

Validated M4 evaluation -> normalized learning topic -> explainable priority and evidence timeline -> exact-topic M3 practice -> focused M4 interview -> updated learning signal.

The existing Weaknesses page now supports All, Active, Improving, Resolved, Strengths and JD-relevant views, category/severity filters, search and pagination. Detail includes first/last detection, independent interview and assessment counts, confidence/severity explanations, JD source quotations, chronological weak/partial/strong signals, follow-up recovery, bounded answer excerpts and links to original interview records. Practice intent is editable; improvement and resolution are evidence-derived.

M3 retains its existing question details, bookmarks and self-reported practice statuses. Exact-topic practice cannot silently switch to unrelated or random same-category questions. Retest summaries link back to the learning detail; refresh/deep links preserve the selected topic and JD context.

## Schema

Migration `0005_learning.py` upgrades revision 0004 without altering existing tables:

| Table | Stored fields |
| --- | --- |
| `learning_topics` | Stable normalized ID, skill, topic, category, practicing flag, optimistic revision, created/updated timestamps |
| `learning_evidence` | Stable ID, topic FK, evaluation FK, original topic labels, validated assessment, rubric-qualified positive flag, observation time |

`(topic_id, evaluation_id)` is unique; topic references are indexed. Evidence follows evaluation -> turn -> session/question links rather than duplicating full answers or documents. Aggregates and derived status are computed from stored evidence; practice intent persists independently. A rebuildable index avoids storing an unexplained AI-generated proficiency score.

Learning reads synchronize the index within a short SQLite write transaction. Each original M4 judgment is revalidated with the existing strict schema, exact answer quotation checks, permitted question topics and rubric scoring; stored public feedback and score must agree. Malformed or inconsistent records are excluded and surfaced as an exclusion count. Previously indexed references to invalid records are removed from the derived index, never from the original interview. Topic rows with no verified evidence are not exposed.

## Detection and Normalization

- Only validated `partial`, `incorrect`, or `not_demonstrated` topic assessments create weak signals. A low total score alone never creates a topic weakness.
- `demonstrated` topic evidence is positive. It qualifies for a strong trend only when every rubric dimension is at least 2/4 and the weighted result is at least 7.5/10 (3/4). This is an anchored practice rule, not hiring readiness.
- Unicode normalization, case folding and whitespace normalization establish stable identity within a skill. Explicit versioned aliases cover Spark/Data Skew variants and Kafka rebalancing terms. Unlisted semantic synonyms are not guessed; unrelated skills remain distinct.
- Multiple aliases within one evaluation collapse to one occurrence, retaining the least favorable topic assessment. Retries/repeated reads cannot add occurrences.
- Occurrence count means weak evaluated turns. Confidence and trend rules use distinct interview sessions, so follow-ups are supporting evidence, not independent confirmations.

## Severity and Confidence

Severity:

- Low: weak evidence in one independent interview.
- Medium: weak evidence in at least two independent interviews.
- High: the repeated-evidence rule plus an explicit must-have requirement for that skill in the selected confirmed JD.

Without selected JD context, general severity never becomes High. JD relevance uses M3's source-revalidated candidates; quotations remain inspectable. It is skill-level relevance, not a claim that the JD explicitly named every subtopic. Severity describes recorded weak evidence and remains separate from improvement/resolution.

Confidence:

- Low: one independent weak-signal interview.
- Medium: at least two independent weak-signal interviews.
- High: at least three independent weak-signal interviews, with direct answer excerpts supporting weak assessments in at least two of them.

Absence-only assessments cannot reach High confidence. Labels describe evidence support, not statistical probability or proof that the model is correct. Positive-only topics carry emerging/repeated strength labels rather than fabricated weakness confidence.

## Improvement and Strength Rules

Within each interview, the least favorable topic evidence determines its conservative trend point. A weak primary followed by a strong follow-up is labeled follow-up recovery; it does not become an independent strong interview.

One later strong interview, or a later partial interview after earlier weak evidence, yields **Improving**. **Resolved** requires the last three independent interview observations to be strong after weak evidence. A later weak assessment reopens the topic. Resolution says "resolved for now", never mastered. An explicit practicing flag applies when evidence does not establish improving/resolved status.

One current strong interview gives an **emerging** positive signal; two or more consecutive strong interviews give a **repeated** positive signal. New weak evidence removes that current strength signal while preserving the evidence timeline. Dates refer to evaluation observation times.

## Recommendations

Active weaknesses are ordered by selected-JD relevance, severity, confidence, independent occurrence count, current improvement status and stable skill/topic ties. Every recommendation includes its evidence IDs, observed counts, confidence, JD explanation and improvement signal. Resolved and positive-only topics receive optional maintenance wording, not active weakness recommendations.

Matching practice questions must have the same canonical skill/topic in their expected topics. Suggestions favor JD relevance, self-reported Needs Review, lower prior question exposure and non-mastered status. The existing M4 planner applies its own source-validated priorities/history within the same exact-topic constraint. No new generator exists. Targeted interviews support 1-5 primary questions, bounded by actual catalog availability; many narrow topics have just one matching question. Zero matches produces an explicit limitation/422, never random substitutions.

## APIs

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/api/v1/weaknesses` | Filtered/paginated topics, counts, categories, recommendations, policy version and exclusion count |
| GET | `/api/v1/weaknesses/{id}` | Topic detail with evidence timeline, JD context and practice recommendations |
| PATCH | `/api/v1/weaknesses/{id}/status` | Revision-checked practice intent: detected/practicing only; improving/resolved cannot be asserted manually |
| POST | `/api/v1/weaknesses/{id}/practice` | Study handoff or idempotent focused M4 session creation; optional target and 1-5 questions |
| GET | `/api/v1/questions?focus_id=...` | Existing M3 list narrowed to the exact canonical topic |
| POST | `/api/v1/interviews` | Existing creation contract additionally accepts optional `focus_id` |

Counts, evidence and recommendations are embedded in list/detail responses instead of separate duplicate endpoints. Existing `/api/v1/interviews/weaknesses` is retained for M4 compatibility. Pre-M5 interview creation keys stay idempotent when `focus_id` is absent/null. M4 snapshot/evaluation provider contracts are unchanged. Capabilities adds `adaptive_learning`; health reports milestone 5/revision 0005.

## Verification

Baseline before M5: 105 backend tests passed with 3 explicit real-data opt-in skips; 6 browser regressions passed with 1 opt-in skip. The earlier fully opted-in baseline was 108 backend tests.

Final suite:

- **133 backend tests passed**, including enabled actual-database/PDF checks and all M1-M4 regressions.
- **7 browser regressions passed**, with 2 explicitly separate-mode tests skipped in the normal run.
- Copied-real-data browser mode: **2 passed**, covering the M5 learning/practice/retest loop and complete M4 interview flow.
- Disabled-provider real-data browser mode: **2 passed, 1 intentional skip**, covering the M5 honest empty state and M4 unscored completion; the successful-evaluation loop intentionally requires the fake test provider.
- Ruff lint and format: passed; TypeScript and Vite production build: passed; Prettier checks on changed frontend files: passed.
- Migration downgrade/re-upgrade on disposable data preserves M4 sessions/evaluations; learning evidence is re-indexed with the provider disabled. `alembic check` finds no pending model changes.
- Restart tests verify persisted practice status, learning evidence, improvement, interview answers and summaries using fresh app/engine instances.
- Desktop/mobile evidence-detail screenshots inspected; mobile overflow checks passed.

Additional coverage includes duplicate alias collapse in persisted evidence, concurrent synchronization, occurrence counts, exact evaluation links, JD severity, confidence quality gates, positive-only topics, partial/strong improvement, three-interview resolution, recurrence, follow-up independence, recommendation explanations, exact-topic M3 filters, targeted M4 idempotency, catalog exhaustion, malformed/missing/unsupported evaluation fields, bounded excerpts, question status/history, stale status updates and legacy creation keys.

During development, a browser test exposed missing same-page hash navigation from an interview summary back to its learning detail. Added hash routing and a return link, then reran successfully. A test-file insertion indentation error and lint issues were corrected before the final run. Existing Starlette/httpx deprecation and browser color-environment warnings remain non-failing. Frontend tests use the existing Playwright suite; there is no separate React unit-test framework.

## Real-Data Result and Limits

The actual uploaded resume, confirmed JD, saved M2 classifications, M3 catalog and existing M4 session were used via read-only-source SQLite copies. Re-upload of the original PDF remains a duplicate. Existing user sessions and answers are compared before/after copied-data tests and remain unchanged; source database fingerprints also remain unchanged.

**The personal database has no completed evaluation records.** It has one active interview and one saved answer. M5 therefore correctly creates no personal weakness/strength history. Positive learning behavior was verified using explicitly mocked evaluations persisted through the real M4 APIs on isolated copies of those actual M2/M3 sources. This is not a claim that the user has demonstrated those strengths or weaknesses, and not validation against genuine live-model assessments. No fake evaluations were inserted into the personal workspace.

No live provider is configured or required for learning from stored evaluations. Future live results enter through the existing M4 abstraction and validation. Semantic model accuracy remains unverified: exact quotes prove provenance, not correctness. Test-only browser responses remain clearly labeled as simulated.

Other limits: alias coverage is intentionally conservative; recommendation coverage is limited by the curated catalog; aggregates revalidate/index existing evaluations on learning reads and are intended for a small local workspace, not large multi-user workloads. Timelines are chronological evidence summaries, not statistical mastery estimates. Weakness status remains global while JD relevance/severity is a selected-target view. No encryption/authentication, voice, RAG, embeddings or new provider was added.

## Exact Source Files

Created:

```text
backend/app/learning.py
backend/app/learning_api.py
backend/app/learning_content.py
backend/migrations/versions/0005_learning.py
backend/tests/test_learning.py
backend/tests/test_learning_persisted.py
content/learning-topics.json
frontend/src/Learning.tsx
frontend/src/learning.css
frontend/tests/learning.spec.ts
docs/MILESTONE-5.md
```

Modified:

```text
backend/app/models.py
backend/app/main.py
backend/app/interviews.py
backend/app/interview_api.py
backend/app/interview_schemas.py
backend/app/question_api.py
backend/tests/test_foundation.py
backend/tests/test_persisted_integration.py
backend/tests/serve_browser.py
frontend/src/main.tsx
frontend/src/QuestionBank.tsx
frontend/src/MockInterview.tsx
frontend/tests/interviews.spec.ts
README.md
docs/ARCHITECTURE.md
```

Runtime database/backup, build and screenshots remain Git-ignored. Local upgrade backup: `data/before-milestone-5.db`. No source resume, JD, answer, API key or token is stored in this report.

The actual local database is now at revision 0005. Row-value comparison with the backup confirms all nine pre-existing user-data tables are unchanged. SQLite integrity is `ok`, with zero foreign-key violations. The normal backend was stopped and restarted; the saved active interview response (including its answer) has the same SHA-256 before and after. The learning API returns zero signals because no evaluation exists, and capabilities correctly reports user data with simulated AI false. Frontend and backend are running on loopback ports 5174 and 8001.

## Commands

From `backend/`:

```sh
WAR_ROOM_VERIFY_DATABASE=/absolute/path/to/data/war_room.db \
WAR_ROOM_VERIFY_RESUME=/absolute/path/to/resume.pdf ../.venv/bin/pytest
../.venv/bin/ruff check app tests migrations
../.venv/bin/ruff format --check app tests migrations
../.venv/bin/alembic upgrade head
../.venv/bin/alembic check
```

From `frontend/`, with development servers stopped before Playwright:

```sh
PLAYWRIGHT_CHANNEL=chrome npm test
WAR_ROOM_VERIFY_DATABASE=/absolute/path/to/data/war_room.db \
PLAYWRIGHT_CHANNEL=chrome npm test -- tests/learning.spec.ts tests/persisted.spec.ts
WAR_ROOM_VERIFY_DATABASE=/absolute/path/to/data/war_room.db \
WAR_ROOM_VERIFY_OFFLINE=1 PLAYWRIGHT_CHANNEL=chrome npm test -- tests/learning.spec.ts tests/persisted.spec.ts
npm run build
```

**Stop after M5. Milestone 6 is not started.**
