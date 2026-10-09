# Milestone 2 evidence verification

## Changes

- Strong and Partial classifications require source-backed reviewed claims. Comparison revalidates exact document IDs, character offsets, quotes, and lexical support against immutable source text.
- Unsupported user-added or corrected items block comparison with HTTP 422. Candidate names are excluded from matching and this guard; name corrections cannot influence coverage.
- Every row displays resume/JD evidence by default, including document identifiers and character offsets.
- Missing means no literal/known-alias excerpt found in the complete uploaded resume, not a proven skill gap. The UI shows the exact JD excerpt and explicitly states the absence-check scope instead of inventing resume evidence.
- A source mention omitted from reviewed items produces Needs Revision, not Missing.
- Legacy v1 comparison snapshots are retained in SQLite but excluded from results. Re-running comparison validates the sources and replaces the snapshot with v2.

## Verification

- Backend: 39 passed. Covers malformed PDF/DOCX, empty text and blank PDF, unsupported formats, size limits, missing sections, duplicate uploads, source offsets, LLM unavailable/invalid schema/fabricated values/fabricated quotes/wrong document, Java versus JavaScript, user corrections, review conflicts, confirmation, restart persistence, migrations, and foundation behavior.
- Added regressions: unsupported resume/JD additions rejected at comparison; deleted reviewed mentions cannot create false Missing classifications; row excerpts match the original source slices.
- Browser: 3 passed. Upload/edit/add/delete/confirm/compare, visible evidence and absence explanation, refresh persistence, revisions, responsive layout, profile persistence, API failure recovery.
- Frontend production build passed; Ruff passed; Alembic reports no pending schema changes.
- Initial browser run failed because the guard also blocked name corrections. Fixed by excluding names from comparison; complete rerun passed.
- Non-failing warnings: existing Starlette TestClient/httpx deprecation and browser runner color-environment warning.

## Limitations

- Exact lexical evidence is not semantic proof of proficiency or factual verification of a resume. Human review remains necessary; local extraction has a limited vocabulary and does not handle all paraphrases or nuanced negation.
- Missing is a document-coverage finding, not evidence of lacking experience. There is no separate candidate-skill Gap verdict.
- Newly added experience must appear in an updated uploaded source before it can support comparison. Unsupported edits remain saveable for review but cannot support results.
- Scanned PDFs are unsupported; live LLM calls remain disabled. Automated tests use fake providers.
- No Milestone 3 work performed.

## Files changed in this follow-up

- `backend/app/analyzer.py`
- `backend/app/analyzer_api.py`
- `backend/tests/test_analyzer.py`
- `frontend/src/Analyzer.tsx`
- `frontend/tests/analyzer.spec.ts`
- `docs/MILESTONE-2-EVIDENCE-VERIFICATION.md`
