"""Deterministic interview planning and transactional session state machine."""

from collections import Counter
from contextlib import contextmanager
from datetime import UTC

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from app.content import Rubric
from app.interview_schemas import EvaluationView, SessionCard, SessionView, TurnView
from app.learning_content import matches
from app.models import (
    BankQuestion,
    InterviewSession,
    InterviewTurn,
    LearningTopic,
    QuestionTarget,
    TurnEvaluation,
    utc_now,
)
from app.question_schemas import GenerateInput, QuestionContent
from app.questions import candidates, normalized


@contextmanager
def write_session(engine):
    # Short SQLite write locks serialize state transitions, never remote LLM calls.
    with Session(engine) as db:
        db.execute(text("BEGIN IMMEDIATE"))
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise


def get_session(db, identity):
    value = db.get(InterviewSession, identity)
    if not value:
        raise HTTPException(404, "Interview session not found.")
    return value


def current_turn(db, interview):
    turn = db.get(InterviewTurn, interview.current_turn_id) if interview.current_turn_id else None
    if not turn or turn.session_id != interview.id or not turn.asked_at:
        raise HTTPException(409, "Interview state needs repair. Submitted answers remain saved.")
    if not 1 <= turn.primary_number <= interview.total_questions:
        raise HTTPException(409, "Interview question position is invalid. Answers remain saved.")
    if not isinstance(turn.snapshot, dict) or not all(
        k in turn.snapshot for k in ("content", "rubric", "context", "follow_up_templates")
    ):
        raise HTTPException(409, "Question snapshot needs repair. Answers remain saved.")
    try:
        QuestionContent.model_validate(turn.snapshot["content"])
        Rubric.model_validate(turn.snapshot["rubric"])
    except ValueError, TypeError:
        raise HTTPException(409, "Question snapshot needs repair. Answers remain saved.") from None
    return turn


def get_evaluation(db, turn):
    return db.exec(select(TurnEvaluation).where(TurnEvaluation.turn_id == turn.id)).first()


def live_lease(turn):
    return bool(
        turn.evaluation_state == "evaluating"
        and turn.lease_until
        and turn.lease_until.replace(tzinfo=UTC) > utc_now()
    )


def evaluation_view(evaluation):
    return EvaluationView(id=evaluation.id, score=evaluation.score, **evaluation.result["public"])


def turn_view(db, turn):
    evaluation = get_evaluation(db, turn)
    if turn.evaluation_state == "succeeded" and not evaluation:
        raise HTTPException(409, "Evaluation record is missing. The answer remains saved.")
    content = turn.snapshot.get("content", {})
    state = turn.evaluation_state
    error = turn.evaluation_error
    if state == "evaluating" and not live_lease(turn):
        state = "failed"
        error = "Evaluation was interrupted. The answer is saved; retry evaluation."
    return TurnView(
        id=turn.id,
        primary_number=turn.primary_number,
        follow_up_depth=turn.follow_up_depth,
        parent_turn_id=turn.parent_turn_id,
        question_text=content.get("question_text", "Question snapshot unavailable"),
        question_type=content.get("question_type", "unknown"),
        category=content.get("category", "Unknown"),
        difficulty=content.get("difficulty", "unknown"),
        asked_at=turn.asked_at,
        answered_at=turn.answered_at,
        answer_text=turn.answer_text,
        evaluation_state=state,
        evaluation_error=error,
        retryable=state in {"pending", "failed", "deferred"},
        evaluation=evaluation_view(evaluation) if evaluation else None,
    )


def card(interview):
    values = {key: getattr(interview, key) for key in SessionCard.model_fields}
    for key in ("created_at", "started_at", "completed_at"):
        if values[key] is not None:
            values[key] = values[key].replace(tzinfo=UTC)
    return SessionCard(**values)


def session_view(db, interview):
    turn = None
    if interview.status in {"active", "paused"}:
        turn = current_turn(db, interview)
    elif interview.current_turn_id:
        turn = db.get(InterviewTurn, interview.current_turn_id)
    public = turn_view(db, turn) if turn else None
    turns = db.exec(select(InterviewTurn).where(InterviewTurn.session_id == interview.id)).all()
    answered = sum(t.answer_text is not None for t in turns)
    resolved = (
        interview.total_questions
        if interview.status == "completed"
        else (turn.primary_number - 1 if turn else 0)
    )
    action = "none"
    if interview.status == "not_started":
        action = "start"
    elif interview.status == "paused":
        action = "resume"
    elif interview.status == "active":
        if public.answer_text is None:
            action = "answer"
        elif public.evaluation_state == "evaluating":
            action = "wait"
        elif public.evaluation_state not in {"succeeded", "deferred"}:
            action = "evaluate"
        elif public.evaluation and public.evaluation.follow_up_required:
            action = "follow_up"
        else:
            action = "finish" if turn.primary_number == interview.total_questions else "next"
    return SessionView(
        **card(interview).model_dump(),
        current_turn=public,
        answered_turns=answered,
        resolved_primary_questions=resolved,
        next_action=action,
    )


def plan(db, payload, policy):
    if payload.focus_id and not db.get(LearningTopic, payload.focus_id):
        raise ValueError("Unknown learning topic")
    rules = policy.types[payload.interview_type]
    if rules.category and payload.category and rules.category != payload.category:
        raise ValueError("Category conflicts with the interview type.")
    grounded = {}
    if payload.target_id:
        grounded = {
            o["question"]["candidate_id"]: o
            for o in candidates(db, GenerateInput(target_id=payload.target_id))
        }
    if payload.source in {"personalized", "ai_generated"} and not payload.target_id:
        raise ValueError("Select a saved target comparison for personalized questions.")
    links = (
        {
            link.question_id
            for link in db.exec(
                select(QuestionTarget).where(QuestionTarget.target_id == payload.target_id)
            ).all()
        }
        if payload.target_id
        else set()
    )
    previous = Counter(
        t.question_id
        for t in db.exec(select(InterviewTurn).where(InterviewTurn.asked_at.is_not(None))).all()
    )
    choices = []
    for q in db.exec(select(BankQuestion).where(BankQuestion.active)).all():
        c = q.content
        if payload.focus_id and not matches(c, payload.focus_id):
            continue
        if c["question_type"] in rules.excluded_types or (
            rules.question_type and c["question_type"] != rules.question_type
        ):
            continue
        if payload.question_type and c["question_type"] != payload.question_type:
            continue
        category = payload.category or rules.category
        if (
            category
            and c["category"] != category
            or payload.difficulty
            and c["difficulty"] != payload.difficulty
        ):
            continue
        if payload.source == "curated" and q.source != "curated":
            continue
        if q.source == "generated" and q.id not in links:
            continue
        if payload.source in {"personalized", "ai_generated"} and q.source != "generated":
            continue
        base = q.source_reference.get("base_question_id", q.id)
        context = grounded.get(base, {})
        if q.source == "generated" and not context:
            continue
        rank = context.get("priority", 0) + (2 if q.status == "needs_review" else 0)
        choices.append(
            (
                (-rank, previous[q.id], -(q.source == "generated"), q.id),
                q,
                base,
                context.get("evidence", {}),
            )
        )
    choices.sort(key=lambda item: item[0])
    chosen, seen, texts = [], set(), set()
    for _, q, base, context in choices:
        canonical = normalized(
            q.content["question_text"].removeprefix(
                "Target-role practice (prior experience is not assumed). "
            )
        )
        if base in seen or canonical in texts:
            continue
        seen.add(base)
        texts.add(canonical)
        content = dict(q.content)
        if payload.interview_type == "project_deep_dive":
            content["question_text"] = (
                "Use a real project if available, otherwise a hypothetical example. "
                "Explain the decisions and trade-offs involved. " + content["question_text"]
            )
            content["question_type"] = "project_based"
        chosen.append(
            (
                q.id,
                {
                    "content": content,
                    "question_version": q.version,
                    "source": q.source,
                    "rubric": policy.rubric_for(content),
                    "context": context,
                    "follow_up_templates": list(policy.follow_up_templates),
                    "policy_version": policy.version,
                },
            )
        )
    return chosen


def configuration(payload):
    # Keep pre-M5 creation keys compatible when no topic filter was requested.
    exclude = {"request_id"} if payload.focus_id else {"request_id", "focus_id"}
    if payload.question_type is None:
        exclude.add("question_type")
    return payload.model_dump(exclude=exclude)


def create_interview(db, payload, policy, generated=None):
    config = configuration(payload)
    existing = db.exec(
        select(InterviewSession).where(InterviewSession.request_id == payload.request_id)
    ).first()
    if existing:
        if existing.configuration != config:
            raise HTTPException(
                409, "This creation key was already used for a different configuration."
            )
        return existing
    if payload.source == "ai_generated" and generated is None:
        raise ValueError("Fresh AI questions are required for this session")
    chosen = generated if generated is not None else plan(db, payload, policy)
    if len(chosen) < payload.number_of_questions:
        raise HTTPException(
            422,
            f"Only {len(chosen)} distinct questions match. "
            "Reduce the count or broaden the filters.",
        )
    interview = InterviewSession(
        request_id=payload.request_id,
        target_id=payload.target_id,
        configuration=config,
        total_questions=payload.number_of_questions,
    )
    db.add(interview)
    db.flush()
    for number, (identity, snapshot) in enumerate(chosen[: payload.number_of_questions], 1):
        db.add(
            InterviewTurn(
                session_id=interview.id,
                question_id=identity,
                primary_number=number,
                snapshot=snapshot,
            )
        )
    db.flush()
    return interview


def touch(db, interview):
    interview.revision += 1
    interview.updated_at = utc_now()
    db.add(interview)
    db.flush()


def action(db, interview, payload):
    if interview.status in {"completed", "abandoned"}:
        raise HTTPException(409, "This interview is closed and cannot be modified.")
    if interview.revision != payload.revision:
        raise HTTPException(409, "Session changed in another request. Reload before continuing.")
    turn = current_turn(db, interview) if interview.current_turn_id else None
    if turn and live_lease(turn):
        raise HTTPException(
            409, "Evaluation is running. Wait for it to finish before changing session state."
        )
    if payload.action == "start" and interview.status == "not_started":
        turn = db.exec(
            select(InterviewTurn).where(
                InterviewTurn.session_id == interview.id,
                InterviewTurn.primary_number == 1,
                InterviewTurn.follow_up_depth == 0,
            )
        ).first()
        if not turn:
            raise HTTPException(409, "The first question is missing. No answers were removed.")
        interview.status, interview.started_at = "active", utc_now()
        interview.current_turn_id, turn.asked_at = turn.id, utc_now()
    elif payload.action == "pause" and interview.status == "active":
        interview.status = "paused"
    elif payload.action == "resume" and interview.status == "paused":
        interview.status = "active"
    elif payload.action == "abandon":
        interview.status, interview.completed_at = "abandoned", utc_now()
    elif (
        payload.action == "defer_evaluation"
        and interview.status == "active"
        and turn
        and turn.answer_text is not None
        and turn.evaluation_state != "succeeded"
    ):
        turn.evaluation_state = "deferred"
        turn.evaluation_error = "Explicitly continued without evaluation; this answer is unscored."
        turn.lease_token, turn.lease_until = None, None
    elif payload.action in {"next", "finish"} and interview.status == "active" and turn:
        if turn.evaluation_state not in {"succeeded", "deferred"}:
            raise HTTPException(409, "Resolve evaluation or explicitly continue unscored first.")
        evaluation = get_evaluation(db, turn)
        if turn.evaluation_state == "succeeded" and not evaluation:
            raise HTTPException(409, "Evaluation record is missing. The answer remains saved.")
        follow_up = evaluation and evaluation.result["public"]["follow_up_required"]
        if follow_up and turn.follow_up_depth >= 2:
            raise HTTPException(
                409, "Stored follow-up state is invalid; the depth cap cannot be exceeded."
            )
        if payload.action == "finish" and (
            follow_up or turn.primary_number != interview.total_questions
        ):
            raise HTTPException(409, "Resolve the remaining questions before finishing.")
        if follow_up:
            topic = evaluation.result["public"]["follow_up_topic"]
            snapshot = dict(turn.snapshot)
            content = dict(snapshot["content"])
            content["question_text"] = snapshot["follow_up_templates"][turn.follow_up_depth].format(
                skill=content["skill"], topic=topic
            )
            content["question_type"], content["expected_topics"] = "follow_up", [topic]
            snapshot["content"] = content
            next_turn = InterviewTurn(
                session_id=interview.id,
                question_id=turn.question_id,
                primary_number=turn.primary_number,
                follow_up_depth=turn.follow_up_depth + 1,
                parent_turn_id=turn.id,
                snapshot=snapshot,
                asked_at=utc_now(),
            )
            db.add(next_turn)
            db.flush()
            interview.current_turn_id = next_turn.id
        elif turn.primary_number == interview.total_questions:
            interview.status, interview.completed_at = "completed", utc_now()
        else:
            next_turn = db.exec(
                select(InterviewTurn).where(
                    InterviewTurn.session_id == interview.id,
                    InterviewTurn.primary_number == turn.primary_number + 1,
                    InterviewTurn.follow_up_depth == 0,
                )
            ).first()
            if not next_turn or next_turn.asked_at:
                raise HTTPException(409, "Next question state is invalid. Answers remain saved.")
            next_turn.asked_at = utc_now()
            db.add(next_turn)
            interview.current_turn_id = next_turn.id
    else:
        raise HTTPException(409, "This action is not allowed in the current interview state.")
    if turn:
        db.add(turn)
    touch(db, interview)


def submit_answer(db, interview, turn_id, payload):
    if interview.status != "active":
        raise HTTPException(409, "Answers can only be submitted to an active session.")
    turn = current_turn(db, interview)
    if turn.id != turn_id:
        raise HTTPException(409, "Only the current question accepts an answer.")
    if turn.answer_text is not None:
        if turn.submission_id == payload.submission_id and turn.answer_text == payload.answer_text:
            return
        raise HTTPException(409, "An answer is already saved for this question.")
    if interview.revision != payload.revision:
        raise HTTPException(409, "Session changed. Reload before submitting.")
    duplicate = db.exec(
        select(InterviewTurn).where(
            InterviewTurn.session_id == interview.id,
            InterviewTurn.submission_id == payload.submission_id,
        )
    ).first()
    if duplicate:
        raise HTTPException(409, "This submission key was already used for another answer.")
    turn.answer_text, turn.submission_id = payload.answer_text, payload.submission_id
    turn.answered_at, turn.evaluation_state = utc_now(), "pending"
    db.add(turn)
    touch(db, interview)
