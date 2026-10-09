# Milestone 2: Resume and JD Analyzer

Completed 2026-09-27. Milestone 1 was inspected and extended; the existing profile, shell, question content, and provider interface remain. No Milestone 3 work was implemented.

## Delivered workflow

- PDF, DOCX, TXT upload and text paste for resume or JD.
- Local structured extraction using explicit document headings and a conservative vocabulary.
- Source excerpts with immutable document IDs and exact extracted-text offsets.
- Review UI: filter sections, edit, delete, add, mark uncertainty, save, and confirm.
- Provenance remains distinct: extracted, user-supplied, or AI-inferred; confirmation does not erase origin.
- Confirmed analyses are immutable; a new draft revision is required for edits.
- Optimistic revision checking prevents stale browser reviews from overwriting newer data.
- Duplicate uploads reuse identical extracted text within each document kind and retain saved reviews.
- Comparisons require confirmed resume and JD revisions and persist their results in SQLite.
- Strong/partial/missing/needs-revision classifications with supporting resume and JD evidence.
- High/medium/low preparation priorities explained by confirmed JD tiers; versioned suggested review topics.
- Optional AI-analysis service uses the existing interface, validates strict JSON and source support, and requires individual review of AI-inferred items. The default provider stays disabled; local workflow works without a model or API key.

## Verification

| Check | Result |
| --- | --- |
| Backend suite | 36 passed, including the 9 foundation tests |
| Browser suite | 3 passed, including both foundation browser tests |
| Frontend | TypeScript and Vite production build passed |
| Python quality | Ruff lint and format checks passed |
| Migration | Existing local database upgraded 0001 to 0002; existing profile row preserved |
| Migration consistency | Alembic reports no new upgrade operations |
| SQLite integrity | Foreign-key check returned no violations |
| Restart persistence | Documents, confirmed claims/evidence, and comparisons survived app/engine restart |
| Browser workflow | Upload, edit/add/delete, save, confirm, compare, evidence display, refresh, editable revision, and mobile overflow checked |
| Visual review | Desktop and mobile analyzer screenshots inspected |
| Privacy | Database, migration backup, and environment files confirmed ignored by Git |

All 16 requested analyzer testing areas are covered, including valid PDF/DOCX, empty/unsupported/malformed/oversized files, missing sections, comparison, evidence, corrections, persistence, unavailable/invalid LLM output, unsupported claims, and duplicates. Additional tests cover stale revisions, immutable confirmation, ambiguous requirement tiers, Java versus JavaScript, and profile-preserving migration. Fake LLM responses are local test fixtures; tests make no external LLM calls.

The only Python test warning is the existing upstream Starlette/httpx TestClient deprecation. Browser runs emit an environment color warning, without affecting application behavior.

## Files created

Paths are relative to `interview-war-room/`:

```text
backend/app/analyzer.py
backend/app/analyzer_api.py
backend/app/analyzer_schemas.py
backend/app/document_parser.py
backend/migrations/versions/0002_analyzer.py
backend/tests/test_analyzer.py
content/preparation-topics.json
frontend/src/Analyzer.tsx
frontend/src/analyzer.css
frontend/tests/analyzer.spec.ts
docs/MILESTONE-2.md
```

## Files modified

```text
backend/app/contracts.py
backend/app/main.py
backend/app/models.py
backend/requirements.in
backend/requirements.txt
backend/tests/test_foundation.py
frontend/src/api.ts
frontend/src/main.tsx
README.md
docs/ARCHITECTURE.md
```

Changes to foundation tests only update the expected migration head from 0001 to 0002. New dependencies are pypdf, python-docx, python-multipart, and their transitive lxml dependency. No infrastructure services added.

Generated artifacts: ignored `data/before-milestone-2.db` backup, migrated `data/war_room.db`, dependency environment, frontend build, test caches, and browser screenshots/results. Tests use isolated temporary databases. No user resume or JD is bundled or seeded in the personal database.

## Known limitations

- No live LLM adapter is enabled. Local extraction uses a limited vocabulary and recognizable headings, not open-ended semantic reasoning. Unknown technologies, unusual layouts, and complex summaries need correction.
- Work/project/responsibility items are evidence-backed excerpts rather than fully normalized employer/date/project objects. Missing information is not invented.
- Scanned/encrypted PDFs are unsupported. PDF reading order may be imperfect; DOCX body paragraphs/tables are supported, but headers/footers/text boxes are not.
- Skill matches are lexical evidence coverage, not proof of proficiency. Negated/qualified evidence is conservatively flagged; domain, behavioral, and years requirements need contextual review.
- Mixed must/preferred language on a single line is marked uncertain instead of assigning unsupported tiers.
- User additions without source support are self-reported. Exact quotation matching does not prove semantic entailment; AI-inferred interpretations still require individual review.
- Preparation subtopics are curated guidance linked to confirmed JD topics, not extra JD requirements. There is no aggregate hiring/readiness score.
- Save review before leaving the analyzer. Confirmed revisions and saved drafts persist; unsaved edits are not auto-saved.

Milestone 2 stops here. Milestone 3 requires user approval.
