# Milestone 4: Mock Interview Engine

Verified 2026-09-28. Milestone 5 has not been started.

## Delivered

Seven interview types; target, category, difficulty, count and source filters; reuse of the Milestone 3 planner/generator; immutable question snapshots; focused single-question presentation; persistent history and deep links; pause/resume; answer-first storage; strict evidence-based evaluation; at most two follow-ups per primary question; completion summaries; read-only weakness aggregation linked to stored answers. Existing profile, analyzer and Question Bank behavior is preserved.

## Database and state

Migration `0004` adds three tables:

- `interview_sessions`: unique creation request key, target FK, configuration JSON, status, optimistic revision, current turn, primary count and timestamps.
- `interview_turns`: session FK, original question identity, primary number, follow-up depth and parent FK, frozen question/rubric/context snapshot, answer, submission key, evaluation state and renewable lease token/deadline. Unique session/primary/depth and session/submission constraints prevent duplicate turns and answers.
- `turn_evaluations`: unique turn FK, deterministic score, validated result JSON, provider/model and timestamp.

Primary question counts exclude follow-ups; answered/evaluated turn counts include them. Deleted catalog records cannot delete interview snapshots. Current-turn ownership and snapshot structure are validated before state changes. Completed/abandoned sessions are immutable. Corrupt state returns a conflict without deleting answers.

Short `BEGIN IMMEDIATE` transactions serialize writes. Answers commit before a separate evaluation request. A 30-second lease prevents duplicate provider work; the provider has a 22-second deadline. Expired leases can be retried after restart, and old lease results cannot overwrite newer results. Replaying the same answer key and content is idempotent; conflicting submissions return 409.

## Evaluation boundary

The existing LLMProvider abstraction is reused. Strict JSON contains rubric dimension scores (0-4), topic assessments, exact answer excerpts/offsets, and an optional follow-up topic. Unknown fields, invented topics, invalid quotations and unsupported positive judgments are rejected. No free-form candidate experience claims are accepted. Server code renders feedback from validated topic labels and fixed wording, and computes the weighted score out of 10. The versioned technical, SQL, system-design and behavioral rubrics each sum to 100.

Follow-ups use two versioned templates, selected from an assessed missing/partial/incorrect topic and bounded in the persisted state machine. Summary averages, review topics and practice suggestions derive only from stored evaluations; no AI-generated aggregate scores. Weakness occurrences retain session/turn/evaluation IDs and answer excerpts. Missing-answer evidence is an assessment of the answer, not proof the candidate lacks a skill.

## APIs Added

All paths start with `/api/v1/interviews`:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | (base) | Paginated session history |
| GET | `/stats` | Stored session/answer/topic counts |
| GET | `/weaknesses` | Evidence-linked assessment aggregation |
| POST | `/preview` | Eligible count and follow-up cap |
| POST | (base) | Idempotent session creation |
| GET | `/{id}` | Current redacted session state |
| POST | `/{id}/actions` | Start, pause, resume, next, finish, abandon, defer evaluation |
| POST | `/{id}/turns/{turn_id}/answer` | Durable idempotent answer submission |
| POST | `/{id}/turns/{turn_id}/evaluate` | Evaluate/retry through configured provider |
| GET | `/{id}/summary` | Completed/abandoned session summary |

Future questions, expected topics and rubric anchors are not exposed in the current interview response. The separate Question Bank remains available for study; this is not a secure examination platform.

## Verification Results

- Before changes: 71 backend tests and 4 browser tests passed.
- Final backend suite: **102 passed**. Includes all prior regressions plus seven interview types, selection/deduplication, consent, answer concurrency, transition concurrency, evaluation leases, stale results, unavailable/timeout/invalid providers, evidence validation, two-follow-up cap, parent relationships, deletion snapshots, corrupted pointers, restart recovery, completion, summaries and weaknesses.
- Final browser suite: **6 passed**. Existing profile/theme/analyzer/Question Bank journeys plus full JD-based interview, two follow-ups, evaluation, summary, refresh persistence, weaknesses and interrupted-network answer recovery.
- TypeScript check and Vite production build: passed.
- Ruff lint and format check: passed (32 Python files).
- Initial browser regression: one old test expected Mock interview navigation to be disabled. Updated that assertion for the delivered feature; the complete rerun passed.
- SQLite migration downgrade/re-upgrade and restart recovery pass on disposable test databases, including persisted follow-up relationships.
- Actual local database backed up to ignored `data/before-milestone-4.db`, upgraded from 0003 to 0004. Counts unchanged: 1 profile, 2 documents, 2 analyses, 1 target and 36 bank questions.
- `alembic check`: no new upgrade operations. SQLite integrity check: `ok`; foreign-key check: no violations.
- Git ignore verified for the database, backup, `.env`, and browser screenshots.
- Desktop question and mobile summary screenshots visually inspected; browser overflow checks passed.
- Actual frontend/backend restarted on 5174/8001. Health through the frontend proxy returned milestone 4, database ready, revision 0004; interview stats returned valid empty counts.

All automated AI responses are fake. The complete interactive flow was exercised by Playwright, not separately repeated as an unautomated manual run. No live model/API-key verification was performed. One dependency warning remains: Starlette deprecates its current httpx TestClient integration; it does not fail tests. Browser tooling also reports a harmless color-environment warning.

## Exact Files Created

```text
backend/app/interview_api.py
backend/app/interview_content.py
backend/app/interview_evaluation.py
backend/app/interview_schemas.py
backend/app/interview_summary.py
backend/app/interviews.py
backend/migrations/versions/0004_interviews.py
backend/tests/test_interviews.py
content/interview-policy.json
frontend/src/MockInterview.tsx
frontend/src/interview.css
frontend/tests/interviews.spec.ts
docs/MILESTONE-4.md
```

## Exact Files Modified

```text
.env.example
README.md
backend/app/main.py
backend/app/models.py
backend/tests/serve_browser.py
backend/tests/test_foundation.py
docs/ARCHITECTURE.md
frontend/src/main.tsx
frontend/tests/foundation.spec.ts
```

Runtime SQLite/backup, build output and test artifacts are ignored, not source changes. No dependencies or infrastructure were added.

## Limits and Scope

- Exact quotations validate provenance, not semantic truth. Model judgments can still be wrong; scores are answer-specific, not hiring predictions.
- No provider is required for curated interviews or answer storage. Failed evaluation can be retried, or explicitly deferred to continue unscored. Deferred answers are excluded from averages and weaknesses; closed sessions cannot be retroactively evaluated.
- Unsubmitted drafts are in memory only, with a page-unload warning. Submitted answers are durable. Navigating away can discard a draft.
- Follow-up wording is deliberately template-bounded, not unrestricted generated prose. AI-generated questions reuse Milestone 3 bounded set assembly; catalog coverage is limited.
- Project deep dives use neutral real-project-or-hypothetical framing, not invented employer-specific stories.
- No timer, voice, video, incidents, RAG, advanced progress analytics, authentication or encryption. Local loopback use only; sanitize inputs and protect backups.
- Corrupted state is reported safely, not automatically repaired. A crashed evaluation becomes retryable after its lease expires.
- History initially displays the most recent 30 sessions; the API supports pagination. Existing session deep links remain usable.

Stop here. Milestone 5 requires approval.
