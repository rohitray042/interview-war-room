# Interview War Room: locked V1 principles

Current implementation is Milestone 5. Earlier milestone sections below describe their historical scope; see [Milestone 5](MILESTONE-5.md) for the current learning schema, endpoints, rules and verification.

## Milestone 5 additions

Two SQLite tables index normalized topics and references to original evaluations. Learning reads revalidate strict M4 judgments against saved answers and question snapshots before synchronizing this index transactionally. Unsupported or malformed records are excluded; no LLM writes learning records. Status, severity, confidence and recommendations are deterministic views of the persisted evidence and explicit practice intent. Index reads are idempotent; personal documents, answers and interview states are never changed by synchronization.

Topic aliases are version-controlled in `content/learning-topics.json`. No fuzzy matching, embeddings or additional provider is introduced. Independent evidence means distinct interview sessions: follow-ups cannot inflate resolution/confidence. Three subsequent strong independent interviews are required for resolution, and later weak evidence reopens the topic. Exact-topic practice reuses M3's bank and M4's planner via `focus_id`. Existing M4 summary endpoints remain compatible; the richer Weaknesses UI uses `/api/v1/weaknesses`.

React + FastAPI + SQLite. Local personal application, not a generic chatbot. No PostgreSQL, Redis, Kafka infrastructure, vector store, LangChain, LangGraph, MCP, multi-agent orchestration, voice, incidents, RAG, or external integrations in V1. The application may eventually connect to one configured LLM provider for explicit reasoning tasks.

## Milestone 1 baseline

Implemented: app shell, profile persistence, migration, content validation/manifest, environment configuration, disabled provider contract, strict evidence/evaluation contracts, unit/API/browser tests. Only profiles exist in SQLite. Resume/JD analysis, question bank browsing/generation, interviews, answer evaluation, weaknesses, and real progress aggregation are future milestones. Zero/Not assessed are honest empty states, not readiness estimates.

## Required invariants for subsequent milestones

1. Every resume/experience claim must reference an immutable source document and exact excerpt offsets. Validate quotations server-side and retain resume versus JD provenance. A requirement in a JD is not evidence that the candidate has that skill. Source matching is necessary but does not prove the proposed claim follows from its quotation; analysis also needs semantic validation and user review.
2. Never fabricate candidate skills, projects, duties, metrics, technology usage, or achievements. Unsupported claims must be rejected or marked unknown, not filled in.
3. Curated questions and rubrics live in `content/` with stable IDs and versions. Future generated questions belong in SQLite with model/prompt metadata and evidence. Interviews snapshot the question and rubric version.
4. Deterministic services own state transitions, question selection, follow-up budgets, transactions, score arithmetic, and analytics. LLM adapters own provider-specific transport; task services own bounded prompts and validation.
5. Milestone 4 enforces a maximum of 2 follow-ups per primary question in persisted state. This supersedes the earlier foundation contract's allowance of 3.
6. Persist the current question, answer, and session state transactionally. Unique session-question attempts and submission keys prevent duplicate submissions; evaluation retries must not create extra answers. These tables and endpoints are not implemented in Milestone 1.
7. Evaluations must pass the strict JSON schema before storage. Do not accept provider-generated aggregate readiness scores. Validate quoted mistakes against the answer. Evidence validation, provider retries, and production evaluation will be wired in their own milestones.
8. Milestone 4 calculates answer scores from stored, versioned domain-specific rubric dimensions. Summary averages use stored evaluations only, with a separate primary-question average. Earlier proposed generic weights and recency weighting are not applied. Advanced progress analytics remain out of scope.
9. Automated tests use fake providers; no API key or external model availability is required. Fake feedback must never be presented as real evaluation in the application.
10. Environment variables hold secrets. No raw user text or keys in logs. `data/`, `.env`, caches, and build output are excluded from Git. Host on loopback only; no authentication or network deployment in this milestone.

## Foundation endpoints

- `GET /api/v1/health`: database connectivity and migration revision.
- `GET /api/v1/capabilities`: implemented features; AI explicitly disabled.
- `GET /api/v1/content/manifest`: content IDs, versions, and topic metadata; no prompts, reference concepts, or private rubrics.
- `GET /api/v1/profile`: local personal profile.
- `PUT /api/v1/profile`: validated complete editable profile replacement. Immutable IDs/timestamps are not accepted. A full PUT avoids ambiguous partial-update semantics for the first form.

The database starts empty of personal information. Suggested topics in the UI are labeled as suggestions. The profile stores only what the user saves. Profile data is served from SQLite, not browser localStorage; localStorage is used only for theme preference.

## Milestone 2 additions

The existing shell, profile, curated question catalog, and provider contract remain in place. Separate parser, analyzer, API, schema, and React page modules add the review workflow. Migration `0002` adds `documents`, `analyses`, and `targets`. Documents contain immutable extracted text and per-kind content hashes. Reviews have optimistic revision counters; confirmed analyses cannot be edited. Target results reference immutable confirmed analysis IDs. Duplicate uploads reuse the stored document and its analyses. Personal extraction never modifies curated content.

New routes: POST `/documents/upload`, POST `/documents/text`, GET `/documents`, GET `/documents/{id}`, PUT `/analyses/{id}`, POST `/analyses/{id}/confirm`, POST `/analyses/{id}/revision`, POST `/documents/{id}/ai-analysis`, POST/GET `/targets` (all under `/api/v1`). The optional AI-analysis route uses the existing provider interface; the default disabled provider returns 503. Local extraction, user review, and comparison need no API key. No remote adapter, agents, RAG, incidents, or question generation was added.

Source quotes are verified against immutable extracted text. AI claims require support in those excerpts and remain uncertain/unconfirmed until reviewed individually. This is lexical validation, not proof of semantic entailment. User-provided additions retain distinct provenance. Missing data remains missing; suggestions in `content/preparation-topics.json` are labeled preparation guidance, not inferred candidate experience or unmentioned JD requirements.

## Milestone 3 additions

Question Bank services reuse the existing provider protocol and confirmed analyzer revisions. No interview, answer, or evaluation tables are introduced. Migration `0003` adds `bank_questions` (curated cache or generated record, unique normalized text, version, metadata, timestamps, status and bookmark) and `question_targets` (composite question/target foreign keys with immutable evidence snapshots). Curated content is authoritative in `content/question-bank.json`, distinct from the three historical foundation samples. Catalog synchronization preserves personal state, rejects changed content without a version bump, and retires removed entries.

Personalization re-runs deterministic comparison against original source documents, rather than trusting a stored result or model assertion. JD tier contributes 30/20/10 priority points; missing/partial/needs-revision/strong coverage adds 6/4/3/1; a self-reported Needs Review question adds 2. These are preparation ordering weights, not skill scores. Literal/known-alias topic matching limits the eligible catalog. Contextual requirements remain Needs Revision; no skill gap is asserted as candidate fact.

The optional LLM selects from bounded vetted question candidates and returns strict JSON. Every returned field, count, identity, rationale and priority eligibility is verified before a transaction stores anything. This is personalized set assembly, not unconstrained new question authorship. Neutral framing never attributes work to the candidate. Normalized duplicates reuse the existing record and add a target evidence association, preserving status/bookmark state. Evidence and provenance remain inspectable after restart; raw prompts are not stored.

`providers.py` implements optional OpenAI Responses transport behind `LLMProvider`, using environment-only model/key settings, explicit per-request consent, a timeout, and `store=false`. It is disabled by default. The analyzer retains its disabled provider to preserve Milestone 2 behavior. Unit tests and the isolated browser server inject fake question providers; they force provider configuration to disabled irrespective of environment variables.

All Question Bank routes use `/api/v1/questions`: GET list, GET `/stats`, GET `/metadata`, GET `/{id}`, PATCH `/{id}` for status/bookmark, POST `/generation-preview`, POST `/generate`. Curated question edits belong in versioned content, not an arbitrary CRUD endpoint. SQLite handles structured filters; the small filtered catalog is searched locally for normalized text and array metadata. There is no search service or vector index.
