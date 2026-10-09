from fastapi import APIRouter, HTTPException, Query, Request
from sqlmodel import Session, select

from app.contracts import DisabledProvider, ProviderUnavailable
from app.interview_evaluation import evaluate_turn
from app.interview_generation import generate_interview, generation_context, generation_policy
from app.interview_schemas import (
    ActionInput,
    AnswerInput,
    EvaluateInput,
    InterviewInput,
    SessionCard,
    SessionView,
    SummaryView,
    WeaknessView,
)
from app.interview_summary import summary, weakness_rows
from app.interviews import (
    action,
    card,
    configuration,
    create_interview,
    get_session,
    plan,
    session_view,
    submit_answer,
    write_session,
)
from app.models import InterviewSession, InterviewTurn, TurnEvaluation

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])


@router.get("/options")
def options():
    policy = generation_policy()
    return {"category": policy["categories"], "question_type": policy["primary_types"]}


@router.get("", response_model=list[SessionCard])
def sessions(request: Request, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    with Session(request.app.state.engine) as db:
        return [
            card(s)
            for s in db.exec(
                select(InterviewSession)
                .order_by(InterviewSession.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
        ]


@router.get("/stats", response_model=dict[str, int])
def stats(request: Request):
    with Session(request.app.state.engine) as db:
        sessions = db.exec(select(InterviewSession)).all()
        answers = db.exec(select(InterviewTurn).where(InterviewTurn.answer_text.is_not(None))).all()
        evaluations = db.exec(
            select(TurnEvaluation, InterviewTurn).join(
                InterviewTurn, TurnEvaluation.turn_id == InterviewTurn.id
            )
        ).all()
        return {
            "sessions": len(sessions),
            "completed_sessions": sum(s.status == "completed" for s in sessions),
            "answers": len(answers),
            "topics_assessed": len({t.snapshot["content"]["skill"] for _, t in evaluations}),
        }


@router.get("/weaknesses", response_model=list[WeaknessView])
def weaknesses(request: Request):
    with Session(request.app.state.engine) as db:
        return weakness_rows(db)


@router.post("/preview", response_model=dict[str, int])
def preview(payload: InterviewInput, request: Request):
    try:
        with Session(request.app.state.engine) as db:
            if payload.source == "ai_generated":
                generation_context(db, payload, request.app.state.interview_content)
                enabled = not isinstance(request.app.state.question_llm, DisabledProvider)
                return {"available": 20 if enabled else 0, "max_follow_ups": 2}
            planned = plan(db, payload, request.app.state.interview_content)
            return {"available": len(planned), "max_follow_ups": 2}
    except ValueError:
        raise HTTPException(422, "Check interview filters and confirmed target context.") from None


@router.post("", response_model=SessionView)
async def create(payload: InterviewInput, request: Request):
    app = request.app
    with Session(app.state.engine) as db:
        existing = db.exec(
            select(InterviewSession).where(InterviewSession.request_id == payload.request_id)
        ).first()
        if existing:
            if existing.configuration != configuration(payload):
                raise HTTPException(409, "Creation key belongs to a different configuration.")
            return session_view(db, existing)
    try:
        chosen = None
        if payload.source == "ai_generated":
            if app.state.external_llm and not payload.allow_external_processing:
                raise HTTPException(422, "Consent is required for external question generation.")
            with Session(app.state.engine) as db:
                chosen = await generate_interview(
                    app.state.question_llm, db, payload, app.state.interview_content
                )
        with write_session(app.state.engine) as db:
            interview = create_interview(db, payload, app.state.interview_content, generated=chosen)
            return session_view(db, interview)
    except ProviderUnavailable, TimeoutError:
        raise HTTPException(
            503, "Question generation is unavailable. Start a curated interview instead."
        ) from None
    except ValueError, TypeError, KeyError:
        raise HTTPException(
            422,
            "Interview planning failed validation. Check filters and confirmed source evidence.",
        ) from None


@router.get("/{identity}", response_model=SessionView)
def detail(identity: str, request: Request):
    with Session(request.app.state.engine) as db:
        return session_view(db, get_session(db, identity))


@router.post("/{identity}/actions", response_model=SessionView)
def transition(identity: str, payload: ActionInput, request: Request):
    with write_session(request.app.state.engine) as db:
        interview = get_session(db, identity)
        action(db, interview, payload)
        return session_view(db, interview)


@router.post("/{identity}/turns/{turn_id}/answer", response_model=SessionView)
def answer(identity: str, turn_id: str, payload: AnswerInput, request: Request):
    with write_session(request.app.state.engine) as db:
        interview = get_session(db, identity)
        submit_answer(db, interview, turn_id, payload)
        return session_view(db, interview)


@router.post("/{identity}/turns/{turn_id}/evaluate", response_model=SessionView)
async def evaluate(identity: str, turn_id: str, payload: EvaluateInput, request: Request):
    return await evaluate_turn(request.app, identity, turn_id, payload)


@router.get("/{identity}/summary", response_model=SummaryView)
def session_summary(identity: str, request: Request):
    with Session(request.app.state.engine) as db:
        return summary(db, get_session(db, identity))
