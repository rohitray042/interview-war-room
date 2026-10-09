# Live AI setup (Milestone 6)

## Gemini primary provider

Gemini is the default provider for local development. OpenAI remains opt-in;
there is no automatic fallback. No configured Gemini model/key means Disabled,
even when an OpenAI key is present. Existing M1-M5 state and schemas are unchanged.

Create a key in [Google AI Studio](https://aistudio.google.com/apikey), then add
these to the project root's ignored `.env`, never `.env.example`:

```dotenv
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=<your server-side key>
```

The model above is a configurable low-cost starting point, not a guarantee of
free account access. Verify your project's tier, current limits and model access
in AI Studio. [Google pricing](https://ai.google.dev/gemini-api/docs/pricing)
lists a free tier for this model and different data-use terms for free versus
paid use. Prefer synthetic/redacted data for testing; do not upload confidential
resumes without reviewing those terms. The application cannot enforce a free
tier or inspect your billing account. No paid tools/grounding are requested.

Adapter: existing httpx dependency, official Gemini REST `generateContent`,
`generationConfig.responseMimeType` and native `responseSchema`.
Local references are inlined and nullable unions translated. Provider-unsupported
string/collection constraints are enforced by the unchanged application Pydantic
models after response parsing. No evidence checks are bypassed. Simple JSON Schema
worked, but the full JSON Schema contract was rejected by the deployed API; the
native schema contract passed live generation, evaluation and follow-ups. Reference:
[Google API documentation](https://ai.google.dev/api/generate-content).
No legacy Python SDK or extra orchestration dependency is installed.

To explicitly choose OpenAI instead:

```dotenv
LLM_PROVIDER=openai
OPENAI_MODEL=<your model>
OPENAI_API_KEY=<your server-side key>
```

Only the selected provider's credentials are required. `LLM_PROVIDER=disabled`
disables live AI. `LLM_PROVIDER` takes precedence over the older
`WAR_ROOM_LLM_PROVIDER`; OpenAI also accepts legacy `WAR_ROOM_LLM_MODEL` and
`WAR_ROOM_LLM_API_KEY` when its dedicated fields are empty. Avoid conflicting
selectors. Do not set `LLM_PROVIDER=mock`; automated tests inject mock providers.

Restart the backend after editing `.env`. The header displays provider/model
and starts Unverified. Connected appears only after an actual successful
structured response, not merely after configuration or page load. This indicates
provider transport/JSON success, not guaranteed semantic assessment quality.

Manual Gemini smoke: select Gemini above, then run from `backend/`:

```sh
../.venv/bin/python manual_live_smoke.py --allow-live
```

It creates synthetic source documents in temporary SQLite, generates exactly
one question, reuses it through the personalized interview source (no duplicate
generation), saves/evaluates an answer, handles applicable bounded follow-ups,
completes and verifies M5 plus restart persistence. At most four logical AI
operations, two transport attempts each. It checks API output/logs for the key.
No original user database is mutated and no live calls are in automated tests.
Live browser network inspection is separate and is not performed by this script.

Gemini errors: 401/403 authentication, 400 request/model configuration, 404 model
unavailable, 429 quota/rate limit, 5xx temporary failure. Only transient errors
get one retry. Timeout budget remains 20 seconds. Safety-blocked, truncated,
non-JSON and invalid evidence results never become successful evaluations.
Answers survive failure. Never repeatedly retry quota errors automatically.

## Original OpenAI setup and shared behavior

Use the existing Python virtual environment and React setup in the README. The
adapter uses httpx 0.28.1 with the official OpenAI Responses REST API; no SDK,
orchestration framework, or new infrastructure is required.

## Configuration

Create `.env` in the project root, not `.env.example`:

```dotenv
WAR_ROOM_LLM_PROVIDER=openai
WAR_ROOM_LLM_MODEL=<your structured-output-capable model>
WAR_ROOM_LLM_API_KEY=<your backend-only key>
WAR_ROOM_DATABASE_PATH=data/war_room.db
```

Do not put secrets in frontend variables, source files, templates, screenshots,
or chat. `.env` and `data/` are Git-ignored. Rotate any exposed key.
Set `WAR_ROOM_LLM_PROVIDER=disabled` to disable AI. A missing model/key also
disables the provider. Mock providers are injected by tests only, never selected
by a production environment switch.

Start from `backend/`:

```sh
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

From `frontend/`, run `npm run dev` and open http://127.0.0.1:5174.
Restart the backend after configuration changes. The header and
`GET /api/v1/ai/status` distinguish Disabled, Mock, Unverified, Connected, and
Unavailable. Configuration alone is NOT a successful connection. Connected
means the last request returned structured JSON, not that every application
evidence check passed. Status resets to Unverified on restart. Polling status
does not call OpenAI or incur usage.

## Operations and evidence

M3 generation sends selected confirmed evidence and vetted candidates; it does
not invent candidate experience or arbitrary new questions. Catalog availability
limits requested counts and filters. M4 sends the saved answer, current question,
rubric and relevant source evidence. Application schemas and exact quotations
are validated before results are stored. AI selects follow-up topics; existing
versioned templates render at most two follow-ups. M5 derives signals from
validated stored evaluations, never from direct AI-written weakness records.

M2 deterministic extraction remains the default. The optional existing API
`POST /api/v1/documents/{id}/ai-analysis?allow_external_processing=true` requires
explicit external-processing consent and returns a new review-required draft;
it never overwrites confirmed analysis. There is no new M2 AI control in the UI.

## Manual live smoke test

This is separate from pytest and Playwright and makes billable requests:

```sh
cd backend
../.venv/bin/python manual_live_smoke.py --allow-live
```

The script uses a fresh temporary SQLite database with explicitly synthetic
resume/JD documents, not your real resume or active interview. It generates one
personalized question, verifies Connected status, submits and evaluates an
answer, handles applicable follow-ups, completes the session, checks M5 signals
and restart persistence. It checks API responses and captured application logs
for the configured key. It prints only safe result/usage metadata. The database
is deleted after the run. This is an API integration smoke, not live browser
network inspection; offline browser tests exercise UI separately.

Maximum four logical AI requests (one generation plus up to three evaluations),
at most two attempts each, 20-second total deadline per operation, 10,000 output
tokens per attempt. Failures abort the procedure without silently retrying the
whole workflow. Failed network requests may still incur provider usage. Review
account usage/budget before rerunning. Usage metadata is logged when returned;
it is not a billing ledger and is not persisted in SQLite.

## Failures and tests

Transient network/timeout, rate limit, and selected 5xx errors get one retry
after 0.5 seconds. Authentication/configuration and malformed output are not
automatically retried. Invalid application evidence is rejected without saving
an evaluation; answers remain saved and can be explicitly retried or continued
unscored. Never enable HTTP debug logging with secrets or private documents.

For Unavailable, check server configuration, model access, billing/quota and
network connectivity. For validation rejection, retry deliberately; the system
must not turn invalid output into success. Connected is a last-response signal,
not continuous health monitoring.

```sh
cd backend
../.venv/bin/pytest
../.venv/bin/ruff check app tests manual_live_smoke.py
cd ../frontend
npm run build
PLAYWRIGHT_CHANNEL=chrome npm test
```

Tests use injected fake providers or mocked HTTP transports. Pytest blocks the
default asynchronous HTTP transport, and the browser test server explicitly
disables the live provider regardless of local `.env` settings.

Official reference: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
