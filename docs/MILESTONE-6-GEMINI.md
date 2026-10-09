# M6 Gemini adjustment - 2026-10-04

Gemini is now the default local provider. This supersedes the OpenAI-default
configuration in the earlier M6 report; no M7 work was done.

## Current live verification: PASSED

2026-10-04: isolated synthetic Gemini smoke now passes using gemini-3.5-flash-lite.
The incompatible full responseJsonSchema was replaced with native responseSchema:
inline local references, translate nullable unions, omit provider-unsupported
constraints while retaining full original Pydantic/evidence checks on output.
Simple text and simple structured probes proved credentials/model access were
working; the full native question-schema probe succeeded before the final smoke.

Verified: Connected status; one generated/persisted question; primary answer plus
two follow-ups evaluated; completed summary; four M5 learning topics; restart
persistence; no configured key in API responses or captured logs. The smoke used
temporary synthetic SQLite, not original user documents/interviews.

Successful smoke: four first-attempt calls, 5,030 input + 1,278 output = 6,308
reported tokens. Four successful minimal diagnostics reported another 234 tokens.
One full-schema attempt returned 400 with no usage reported. One model metadata
GET checked limits. No OpenAI calls. No billing changes. Actual charges/tier were
not queried and cannot be inferred from returned token metadata.

This supersedes the historical blocked attempts below. No live M2 AI extraction
or browser network capture was performed; Gemini API M3-M5 path including the
two-follow-up cap is live verified. No claim of universal evaluation accuracy.

Fix files: backend/app/gemini_provider.py, backend/tests/test_gemini_provider.py,
docs/LLM-SETUP.md, docs/MILESTONE-6-GEMINI.md.

Final regression: 170 backend tests passed (including persisted-copy checks),
8 browser tests passed with 2 opt-in cases skipped. Vite/TypeScript build, Ruff
lint and changed-Python format checks passed. All automated tests remained offline.

## Historical blocked configuration follow-up

After the user supplied credentials, attempted Gemini smoke with synthetic data.
The initial responseFormat request returned 400. A compatibility probe using
responseMimeType/responseJsonSchema reached model resolution and returned 404:
gemini-2.5-flash-lite is unavailable to new users; the API recommended
gemini-3.5-flash-lite. Local GEMINI_MODEL and setup documentation were updated
to that model (Google lists a free tier; account eligibility is not verified).

The adapter and mocked request tests now use responseMimeType/responseJsonSchema.
The repeated full smoke still returned 400; a reduced question-schema probe
returned only "Request contains an invalid argument." No successful generation,
evaluation or learning signal was produced. Exact remaining incompatibility is
unresolved. Five total HTTP requests in this follow-up all failed (400/404),
with no automatic retry of those statuses. No token usage was reported; no claim
of zero billing is made. No OpenAI calls or changes to original interviews.
Gemini remains NOT live-verified; stop further live calls pending diagnosis.

## Implementation

The existing LLMProvider contract, LLMRequest/LLMResult and application validation
are unchanged. A Gemini adapter uses official REST generateContent with current
responseFormat JSON schema, using already-installed httpx 0.28.1. A small shared
HTTPProvider base contains the existing timeout/retry/metadata behavior. OpenAI
Responses support is retained, optional, and isolated. No added dependencies.

Gemini forwards existing schema and minimal task context. It rejects blocked,
truncated, missing, multiple-candidate and malformed responses. Both providers
have at most two attempts and a 20-second operation deadline; auth/config errors
are not retried. The Gemini key is in an HTTP header, never a URL. Safe metadata
contains provider/model/operation/status/latency/usage, not prompts or answers.

The UI shows safe provider/model with status. Connected means a successful
structured provider response, not merely valid-looking configuration. Health
polling never calls an LLM. Missing selected-provider credentials disable AI;
there is no cross-provider fallback. Mock providers remain test-only injections.

M2 optional extraction, M3 bounded generation, M4 evaluation/follow-up selection,
and deterministic M5 learning reuse their existing paths. No interview-state,
database-schema or permanent weakness-writing changes.

## Configuration

- `LLM_PROVIDER=gemini` (default), `openai`, or `disabled`.
- Gemini: `GEMINI_API_KEY`, `GEMINI_MODEL`.
- OpenAI: `OPENAI_API_KEY`, `OPENAI_MODEL`.
- Legacy WAR_ROOM_LLM_* configuration remains supported for OpenAI.
- `LLM_PROVIDER` takes priority over `WAR_ROOM_LLM_PROVIDER`.

The local ignored `.env` selector was changed to Gemini. Existing OpenAI secrets
were neither displayed nor removed. Gemini key/model were absent at verification.

## Verification

168 backend tests passed, including opt-in persisted-copy regressions. Added
mocked Gemini HTTP tests cover schema request shape, usage/redaction, auth,
rate-limit, timeout/network, malformed/blocked output, switching, disabled mode,
status metadata, and full M3/M4/M5 integration with two bounded follow-ups.
TypeScript/Vite build, Ruff lint and 41-file format check, and changed frontend
Prettier check passed. Browser suite: 8 passed, 2 opt-in cases skipped. No failures.

No Gemini or OpenAI live calls were made during this adjustment. Gemini live
smoke is PENDING configuration, not passed. Prior OpenAI smoke does not verify
Gemini. Definition of done remains incomplete until live validation succeeds.

Manual smoke: from backend, `../.venv/bin/python manual_live_smoke.py --allow-live`
after configuring Gemini. Synthetic temporary SQLite, exactly one generated
question reused by personalized interview, up to three evaluations, completion,
M5 and restart checks. At most four logical operations; no original data edits.

## Security and limits

`.env` and data/ remain Git-ignored. Source/template/docs key-pattern scan found
no secrets. Nothing committed or pushed; the whole project remains untracked
in its parent repo. Automated tests block default async HTTP and browser tests
force disabled/fake providers. No keys stored in SQLite or frontend state.

Free tier is not guaranteed by the application: verify account tier, model
availability, quotas and Google's data-use terms. Synthetic test data is advised.
M3 still selects vetted questions; five hard Kafka scenario questions require
five actual matching candidates. Follow-ups remain versioned templates selected
from AI judgments, not arbitrary newly written text. Existing generic public
provider errors and evidence validation remain in place. No live browser secret
inspection or live Gemini semantic-quality assessment has yet been performed.

## Exact files changed in this adjustment

Created: `backend/app/gemini_provider.py`, `backend/tests/test_gemini_provider.py`,
`docs/MILESTONE-6-GEMINI.md`.

Modified: `backend/app/config.py`, `backend/app/providers.py`,
`backend/app/main.py`, `backend/manual_live_smoke.py`, `frontend/src/AIStatus.tsx`,
`.env.example`, `README.md`, `docs/LLM-SETUP.md`.

Local configuration only: ignored `.env` provider selector.

See [LLM setup](LLM-SETUP.md) for setup, official API references and troubleshooting.
