# Milestone 6 verification - 2026-10-04

Status: live smoke passed after credits were added. See the rerun below for
verified scope and remaining limitations. Milestone 7 has not started.

## Live rerun after funding

2026-10-04: explicit user-authorized rerun passed with the newly configured
`gpt-4.1-nano` model, synthetic documents and a temporary SQLite database.
Connected status, one persisted generated question, saved answer, validated
evaluation, completed summary, four M5 learning topics and session persistence
after app restart were verified. API-response and captured-log key checks passed.
Existing user documents/interviews were untouched.

Three actual API calls, all successful first attempts: two question-generation
calls (the ai_generated interview creation path generates again) and one
evaluation. Total reported usage: 4,977 input tokens and 510 output tokens,
5,487 total. Latencies: 3,193 ms, 3,238 ms and 1,778 ms. Exact dollar cost was not
queried. No additional paid calls were made.

No follow-up was requested by the model, so the live follow-up branch remains
unexercised in this run; bounded follow-ups are covered by prior offline tests.
Live M2 optional AI extraction and live browser network inspection were not
part of this minimal API smoke. The earlier 429 outcome below is historical.

## Changes

Reused LLMProvider and the existing official OpenAI Responses REST adapter with
httpx 0.28.1. No SDK or infrastructure dependency added. One shared live adapter
serves M2 optional analysis, M3 question generation and M4 evaluation. Missing
configuration selects DisabledProvider; injected providers label tests as Mock.
Provider/model/key remain backend-only WAR_ROOM_LLM_* environment variables.

Added nested strict-schema normalization, explicit refusal rejection, 20-second
operation deadline, at most two HTTP attempts, 0.5-second transient backoff,
safe operation/model/timestamp/status/latency/attempt/token metadata logging.
Authentication/configuration and malformed output do not trigger automatic
retry. Existing evidence validation, answer persistence, evaluation leases,
follow-up cap and deterministic M5 derivation remain unchanged.

Added safe status endpoint/header indicator. Configured starts Unverified;
successful structured response becomes Connected; provider failure becomes
Unavailable. No paid status probes. M2 optional analysis now requires explicit
external-processing consent. No AI-key entry in frontend.

## Verification

- Backend: 145 passed, including copied persisted-data regression checks.
- Browser: 8 passed, 2 intentionally skipped opt-in real-data/offline cases.
- Ruff lint and format: passed (37 Python files checked for format).
- TypeScript check and Vite production build: passed.
- Prettier check for changed TypeScript: passed.
- SQLite schema remains 0005; no migration required. Existing migration tests
  and persisted-copy tests passed; live smoke used a new temporary database.
- `.env` and `data/war_room.db` confirmed Git-ignored.
- Source/template/docs scan found no remaining API-key-shaped strings.
- Automated tests block default async HTTP transport; browser test server uses
  explicit disabled/fake configuration even with local live keys configured.
- Known non-failing warning: Starlette testclient/httpx deprecation.

## Earlier live smoke (before funding)

Explicitly authorized manual run, using synthetic documents in temporary SQLite.
Configured model: gpt-4.1-mini. Resume/JD extraction, confirmation, target
creation succeeded. Question generation reached OpenAI twice and received HTTP
429 both times. One logical operation failed after 15,185 ms, returned controlled
503, and stopped without creating an evaluation or fake success.

No token usage was returned. Do not infer zero billed usage. The response code
alone does not establish whether the cause is rate limit, quota or account
billing. Review the provider account before explicitly rerunning.

At that point, live question persistence, evaluation, follow-ups, completion and M5
learning remained UNVERIFIED. The funded rerun above supersedes that result. Live browser
network inspection was not performed. The configured key is absent from normal
API metadata; synthetic secret redaction tests pass.

A key-like value was found in the shareable `.env.example` and removed. That key
must be revoked/rotated. Rotation cannot be verified locally. `.env` was not
printed or edited by the agent. Nothing was committed or pushed. The project is
untracked in its parent repository, so Git cannot supply a preexisting baseline
diff; the exact agent-touched file list is below.

## Exact files

Modified:
- `.env.example`
- `README.md`
- `backend/app/providers.py`
- `backend/app/main.py`
- `backend/app/analyzer_api.py`
- `backend/tests/conftest.py`
- `frontend/src/main.tsx`

Created:
- `backend/tests/test_live_provider.py`
- `backend/manual_live_smoke.py`
- `frontend/src/AIStatus.tsx`
- `frontend/tests/ai-status.spec.ts`
- `docs/LLM-SETUP.md`
- `docs/MILESTONE-6.md`

## Limits

M3 remains bounded vetted-catalog assembly, not unrestricted question writing.
Five hard Kafka questions may not exist in the current catalog. Follow-ups
remain versioned templates selected from validated evaluation topics. M2 AI
assistance is API-only; deterministic UI extraction is unchanged. Usage metadata
is logs, not a persistent billing ledger. Connected describes last structured
provider response, not proof of semantic/evidence validity or continuous health.
The 20-second budget can reject slow models; users must deliberately retry.
UI service errors remain conservative/general; authentication detail is not
shown separately on every workflow screen. No fabricated fallback evaluations.

Setup and manual procedure: [LLM-SETUP.md](LLM-SETUP.md).
