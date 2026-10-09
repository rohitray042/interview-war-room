import hashlib
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.analyzer import ai_extract, compare, extract_claims, supported
from app.analyzer_schemas import Claim, ReviewInput, RevisionInput, TargetInput, TextDocument
from app.contracts import ProviderUnavailable
from app.document_parser import MAX_BYTES, DocumentError, extract_file, validate_text
from app.models import Analysis, Document, Target, utc_now

router = APIRouter(prefix="/api/v1")


def get_record(session, model, id):
    value = session.get(model, id)
    if value is None:
        raise HTTPException(404, "Record not found.")
    return value


def bundle(session, document, duplicate=False):
    analyses = session.exec(
        select(Analysis)
        .where(Analysis.document_id == document.id)
        .order_by(Analysis.created_at.desc())
    ).all()
    return {"document": document, "analyses": analyses, "duplicate": duplicate}


def create_document(engine, kind, filename, text, warnings):
    digest = hashlib.sha256(text.encode()).hexdigest()
    with Session(engine) as session:
        existing = session.exec(
            select(Document).where(Document.kind == kind, Document.content_hash == digest)
        ).first()
        if existing:
            return bundle(session, existing, True)
        document = Document(
            kind=kind, filename=filename[:200], text=text, content_hash=digest, warnings=warnings
        )
        claims, notes = extract_claims(document)
        analysis = Analysis(
            document_id=document.id, claims=[c.model_dump() for c in claims], warnings=notes
        )
        try:
            session.add(document)
            session.flush()
            session.add(analysis)
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.exec(
                select(Document).where(Document.kind == kind, Document.content_hash == digest)
            ).first()
            if existing:
                return bundle(session, existing, True)
            raise
        session.refresh(document)
        return bundle(session, document)


@router.post("/documents/text")
def paste_document(payload: TextDocument, request: Request):
    try:
        text = validate_text(payload.text)
    except DocumentError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return create_document(request.app.state.engine, payload.kind, payload.filename, text, [])


@router.post("/documents/upload")
async def upload_document(
    request: Request, kind: Literal["resume", "jd"] = Form(...), file: UploadFile = File(...)
):
    try:
        data = await file.read(MAX_BYTES + 1)
        text, warnings = await run_in_threadpool(extract_file, file.filename or "document", data)
    except DocumentError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    finally:
        await file.close()
    return await run_in_threadpool(
        create_document, request.app.state.engine, kind, file.filename or "Document", text, warnings
    )


@router.get("/documents")
def documents(request: Request):
    with Session(request.app.state.engine) as session:
        rows = session.exec(select(Document).order_by(Document.created_at.desc())).all()
        return [
            {"id": d.id, "kind": d.kind, "filename": d.filename, "created_at": d.created_at}
            for d in rows
        ]


@router.get("/documents/{id}")
def document(id: str, request: Request):
    with Session(request.app.state.engine) as session:
        return bundle(session, get_record(session, Document, id))


@router.put("/analyses/{id}")
def review_analysis(id: str, payload: ReviewInput, request: Request):
    with Session(request.app.state.engine) as session:
        analysis = get_record(session, Analysis, id)
        document = get_record(session, Document, analysis.document_id)
        old = {c["id"]: Claim.model_validate(c) for c in analysis.claims}
        if len({c.id for c in payload.claims}) != len(payload.claims):
            raise HTTPException(422, "Claim IDs must be unique.")
        claims = []
        for claim in payload.claims:
            if not all(e.verify(document.id, document.text) for e in claim.evidence):
                raise HTTPException(
                    422, "Evidence quotation or source offsets do not match this document."
                )
            previous = old.get(claim.id)
            unchanged = previous and all(
                getattr(previous, key) == getattr(claim, key)
                for key in ["value", "category", "requirement", "evidence"]
            )
            if unchanged:
                claim.origin = previous.origin
                if previous.origin == "ai_inferred" and not claim.reviewed:
                    claim.uncertain = True
            else:
                claim.origin = "user"
                claim.reviewed = True
                if claim.evidence and not supported(claim.value, claim.evidence):
                    claim.evidence = []
            claims.append(claim.model_dump())
        result = session.exec(
            update(Analysis)
            .where(
                Analysis.id == id, Analysis.revision == payload.revision, Analysis.status == "draft"
            )
            .values(claims=claims, revision=Analysis.revision + 1)
        )
        if result.rowcount != 1:
            session.rollback()
            raise HTTPException(
                409,
                "This review changed or was confirmed. Reload it; "
                "use a new revision to edit confirmed data.",
            )
        session.commit()
        session.refresh(analysis)
        return analysis


@router.post("/analyses/{id}/confirm")
def confirm_analysis(id: str, payload: RevisionInput, request: Request):
    with Session(request.app.state.engine) as session:
        analysis = get_record(session, Analysis, id)
        if analysis.status == "confirmed":
            return analysis
        if not analysis.claims:
            raise HTTPException(422, "Add and review at least one item before confirming.")
        if any(c["origin"] == "ai_inferred" and not c["reviewed"] for c in analysis.claims):
            raise HTTPException(422, "Individually review or delete every AI-inferred item first.")
        claims = [{**c, "reviewed": True} for c in analysis.claims]
        result = session.exec(
            update(Analysis)
            .where(
                Analysis.id == id, Analysis.revision == payload.revision, Analysis.status == "draft"
            )
            .values(
                status="confirmed",
                claims=claims,
                confirmed_at=utc_now(),
                revision=Analysis.revision + 1,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            raise HTTPException(409, "Review changed. Reload before confirming.")
        session.commit()
        session.refresh(analysis)
        return analysis


@router.post("/analyses/{id}/revision")
def new_revision(id: str, request: Request):
    with Session(request.app.state.engine) as session:
        previous = get_record(session, Analysis, id)
        if previous.status != "confirmed":
            raise HTTPException(409, "Edit the existing draft before creating another revision.")
        draft = session.exec(
            select(Analysis).where(
                Analysis.document_id == previous.document_id, Analysis.status == "draft"
            )
        ).first()
        if draft:
            return draft
        draft = Analysis(
            document_id=previous.document_id,
            claims=[{**c, "reviewed": False} for c in previous.claims],
            warnings=previous.warnings,
            method=previous.method,
        )
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft


@router.post("/documents/{id}/ai-analysis")
async def analyze_with_ai(id: str, request: Request, allow_external_processing: bool = False):
    if request.app.state.external_llm and not allow_external_processing:
        raise HTTPException(409, "Confirm external processing before sending this document to AI.")
    with Session(request.app.state.engine) as session:
        document = get_record(session, Document, id)
        try:
            claims, method = await ai_extract(document, request.app.state.llm)
        except (ProviderUnavailable, TimeoutError) as exc:
            raise HTTPException(
                503, "LLM unavailable. Local extraction and manual review remain available."
            ) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(
                422,
                "AI output rejected: invalid schema or unsupported source evidence. "
                "Local review is unchanged.",
            ) from exc
        draft = Analysis(
            document_id=id,
            claims=[c.model_dump() for c in claims],
            method=method,
            warnings=[
                "AI-inferred items require individual review. "
                "Matching quotes alone do not prove an interpretation."
            ],
        )
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft


@router.post("/targets")
def create_target(payload: TargetInput, request: Request):
    with Session(request.app.state.engine) as session:
        resume = get_record(session, Analysis, payload.resume_id)
        jd = get_record(session, Analysis, payload.jd_id)
        if resume.status != "confirmed" or jd.status != "confirmed":
            raise HTTPException(409, "Confirm both resume and JD before comparing.")
        if (
            get_record(session, Document, resume.document_id).kind != "resume"
            or get_record(session, Document, jd.document_id).kind != "jd"
        ):
            raise HTTPException(422, "Select one resume and one JD analysis.")
        existing = session.exec(
            select(Target).where(Target.resume_id == resume.id, Target.jd_id == jd.id)
        ).first()
        try:
            comparison = compare(
                [Claim.model_validate(c) for c in resume.claims],
                [Claim.model_validate(c) for c in jd.claims],
                get_record(session, Document, resume.document_id),
                get_record(session, Document, jd.document_id),
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        target = existing or Target(
            resume_id=resume.id,
            jd_id=jd.id,
            result=comparison,
        )
        target.result = comparison
        session.add(target)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return session.exec(
                select(Target).where(Target.resume_id == resume.id, Target.jd_id == jd.id)
            ).one()
        session.refresh(target)
        return target


@router.get("/targets")
def targets(request: Request):
    with Session(request.app.state.engine) as session:
        rows = session.exec(select(Target).order_by(Target.created_at.desc())).all()
        # Legacy comparisons predate source-mention validation. Refresh their derived
        # results from confirmed sources, preserving IDs used by questions/interviews.
        for target in rows:
            if target.result.get("method") != "evidence-comparison-v1":
                continue
            resume, jd = (
                session.get(Analysis, target.resume_id),
                session.get(Analysis, target.jd_id),
            )
            if not resume or not jd or resume.status != "confirmed" or jd.status != "confirmed":
                raise HTTPException(409, "Saved target needs confirmed source reviews.")
            rd, jdd = (
                session.get(Document, resume.document_id),
                session.get(Document, jd.document_id),
            )
            if not rd or not jdd or rd.kind != "resume" or jdd.kind != "jd":
                raise HTTPException(409, "Saved target source documents are unavailable.")
            try:
                for analysis, document in ((resume, rd), (jd, jdd)):
                    for raw in analysis.claims:
                        claim = Claim.model_validate(raw)
                        if not all(e.verify(document.id, document.text) for e in claim.evidence):
                            raise ValueError("Legacy source evidence does not match")
                target.result = compare(
                    [Claim.model_validate(c) for c in resume.claims],
                    [Claim.model_validate(c) for c in jd.claims],
                    rd,
                    jdd,
                )
            except ValueError:
                raise HTTPException(409, "Saved target evidence needs review before use.") from None
            session.add(target)
        session.commit()
        return [
            target for target in rows if target.result.get("method") == "evidence-comparison-v2"
        ]
