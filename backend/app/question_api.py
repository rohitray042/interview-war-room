import logging

from fastapi import APIRouter, HTTPException, Query, Request
from sqlmodel import Session, select

from app.contracts import ProviderUnavailable
from app.learning_content import matches
from app.models import BankQuestion, utc_now
from app.question_drafting import draft_options, draft_questions, question_history
from app.question_schemas import (
    GenerateInput,
    GenerationPreview,
    GenerationResult,
    QuestionList,
    QuestionView,
    StateInput,
    Stats,
)
from app.questions import candidates, generate, normalized, store_generated, view

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])
logger = logging.getLogger("war_room")


def get_question(session, identity):
    question = session.get(BankQuestion, identity)
    if not question or not question.active:
        raise HTTPException(404, "Question not found.")
    return question


@router.get("/stats", response_model=Stats)
def stats(request: Request):
    with Session(request.app.state.engine) as session:
        rows = session.exec(select(BankQuestion).where(BankQuestion.active)).all()
        return {
            "total": len(rows),
            "curated": sum(q.source == "curated" for q in rows),
            "generated": sum(q.source == "generated" for q in rows),
            "saved": sum(q.bookmarked for q in rows),
            "statuses": {
                status: sum(q.status == status for q in rows)
                for status in StateInput.model_fields["status"].annotation.__args__
            },
        }


@router.get("/metadata", response_model=dict[str, list[str]])
def metadata(request: Request):
    with Session(request.app.state.engine) as session:
        rows = session.exec(select(BankQuestion).where(BankQuestion.active)).all()
        values = {
            key: sorted({q.content[key] for q in rows})
            for key in ("category", "skill", "difficulty", "question_type")
        }
        values["tags"] = sorted({tag for q in rows for tag in q.content["tags"]})
        return values


@router.get("", response_model=QuestionList)
def listing(
    request: Request,
    search: str = Query("", max_length=200),
    category: str = "",
    skill: str = "",
    difficulty: str = "",
    question_type: str = "",
    source: str = "",
    status: str = "",
    tag: str = "",
    saved: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    focus_id: str = "",
):
    statement = select(BankQuestion).where(BankQuestion.active)
    for key, value in (
        ("category", category),
        ("skill", skill),
        ("difficulty", difficulty),
        ("question_type", question_type),
    ):
        if value:
            statement = statement.where(BankQuestion.content[key].as_string() == value)
    if source:
        statement = statement.where(BankQuestion.source == source)
    if status:
        statement = statement.where(BankQuestion.status == status)
    if saved:
        statement = statement.where(BankQuestion.bookmarked)
    with Session(request.app.state.engine) as session:
        rows = session.exec(
            statement.order_by(BankQuestion.created_at.desc(), BankQuestion.id)
        ).all()
        rows = [
            q
            for q in rows
            if (not tag or tag in q.content["tags"])
            and (not focus_id or matches(q.content, focus_id))
            and all(
                word in normalized(" ".join(str(v) for v in q.content.values()))
                for word in normalized(search).split()
            )
        ]
        return {
            "total": len(rows),
            "items": [view(q, session) for q in rows[offset : offset + limit]],
        }


@router.post("/generation-preview", response_model=GenerationPreview)
def generation_preview(payload: GenerateInput, request: Request):
    try:
        with Session(request.app.state.engine) as session:
            options = (
                draft_options(session, payload)
                if payload.generation_mode == "draft"
                else candidates(session, payload)
            )
        return {
            "available": (20 if options else 0)
            if payload.generation_mode == "draft"
            else len(options),
            "topics": sorted({o["question"]["skill"] for o in options}),
        }
    except ValueError:
        raise HTTPException(
            422, "Confirm source-backed resume and JD reviews before generating."
        ) from None


@router.post("/generate", response_model=GenerationResult)
async def generate_questions(payload: GenerateInput, request: Request):
    if request.app.state.external_llm and not payload.allow_external_processing:
        raise HTTPException(
            422, "Consent is required to send selected evidence to the configured LLM provider."
        )
    try:
        with Session(request.app.state.engine) as session:
            options = (
                draft_options(session, payload)
                if payload.generation_mode == "draft"
                else candidates(session, payload)
            )
            history = question_history(session) if payload.generation_mode == "draft" else []
        if payload.generation_mode != "draft" and len(options) < payload.number_of_questions:
            raise HTTPException(
                422,
                f"Only {len(options)} grounded questions match. "
                "Reduce the count or broaden the filters.",
            )
        if payload.generation_mode == "draft":
            selected, result = await draft_questions(
                request.app.state.question_llm, options, payload, history
            )
        else:
            selected, result = await generate(
                request.app.state.question_llm, options, payload.number_of_questions
            )
        with Session(request.app.state.engine) as session:
            return store_generated(session, selected, result)
    except ProviderUnavailable, TimeoutError:
        logger.warning("Question provider unavailable")
        raise HTTPException(
            503,
            "Question provider unavailable. Curated questions remain available; "
            "no questions were stored.",
        ) from None
    except ValueError, TypeError, KeyError:
        logger.warning("Question generation validation rejected")
        raise HTTPException(
            422,
            "Generation rejected: check confirmed source evidence and matching question count. "
            "The provider must return valid, grounded questions. Nothing was stored.",
        ) from None


@router.get("/{identity}", response_model=QuestionView)
def detail(identity: str, request: Request):
    with Session(request.app.state.engine) as session:
        return view(get_question(session, identity), session)


@router.patch("/{identity}", response_model=QuestionView)
def state(identity: str, payload: StateInput, request: Request):
    with Session(request.app.state.engine) as session:
        question = get_question(session, identity)
        question.status, question.bookmarked = payload.status, payload.bookmarked
        question.updated_at = utc_now()
        session.add(question)
        session.commit()
        session.refresh(question)
        return view(question, session)
