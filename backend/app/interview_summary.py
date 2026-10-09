"""Summaries and weakness evidence derived only from stored evaluations."""

from statistics import mean

from fastapi import HTTPException
from sqlmodel import select

from app.interview_schemas import SummaryView, WeaknessEvidence, WeaknessView
from app.interviews import card, turn_view
from app.models import InterviewTurn, TurnEvaluation
from app.questions import normalized


def weakness_rows(db, session_id=None):
    query = select(TurnEvaluation, InterviewTurn).join(
        InterviewTurn, TurnEvaluation.turn_id == InterviewTurn.id
    )
    if session_id:
        query = query.where(InterviewTurn.session_id == session_id)
    grouped = {}
    for evaluation, turn in db.exec(query).all():
        for topic in evaluation.result["public"]["topics"]:
            if topic["status"] == "demonstrated":
                continue
            skill = turn.snapshot["content"]["skill"]
            key = normalized(skill), normalized(topic["topic"])
            group = grouped.setdefault(
                key, {"skill": skill, "topic": topic["topic"], "occurrences": []}
            )
            group["occurrences"].append(
                WeaknessEvidence(
                    session_id=turn.session_id,
                    turn_id=turn.id,
                    evaluation_id=evaluation.id,
                    primary_number=turn.primary_number,
                    follow_up_depth=turn.follow_up_depth,
                    assessment=topic["status"],
                    evidence=topic["evidence"],
                )
            )
    return sorted(
        [WeaknessView(**g, count=len(g["occurrences"])) for g in grouped.values()],
        key=lambda g: (-g.count, g.skill, g.topic),
    )


def summary(db, interview):
    if interview.status not in {"completed", "abandoned"}:
        raise HTTPException(
            409, "Summary is available after finishing or abandoning the interview."
        )
    turns = db.exec(
        select(InterviewTurn)
        .where(InterviewTurn.session_id == interview.id, InterviewTurn.asked_at.is_not(None))
        .order_by(InterviewTurn.primary_number, InterviewTurn.follow_up_depth)
    ).all()
    evaluations = db.exec(
        select(TurnEvaluation)
        .join(InterviewTurn, TurnEvaluation.turn_id == InterviewTurn.id)
        .where(InterviewTurn.session_id == interview.id)
    ).all()
    by_id = {t.id: t for t in turns}
    primary_scores = [
        e.score for e in evaluations if e.turn_id in by_id and by_id[e.turn_id].follow_up_depth == 0
    ]
    answers = sum(t.answer_text is not None for t in turns)
    weak = weakness_rows(db, interview.id)
    strong = sorted(
        {
            f"{by_id[e.turn_id].snapshot['content']['skill']}: {topic['topic']}"
            for e in evaluations
            if e.turn_id in by_id
            for topic in e.result["public"]["topics"]
            if topic["status"] == "demonstrated"
        }
    )
    review = sorted({occurrence.turn_id for row in weak for occurrence in row.occurrences})
    return SummaryView(
        session=card(interview),
        primary_questions=interview.total_questions,
        primary_answered=sum(t.answer_text is not None and t.follow_up_depth == 0 for t in turns),
        answers_submitted=answers,
        evaluations_completed=len(evaluations),
        unscored_answers=answers - len(evaluations),
        average_score=round(mean(e.score for e in evaluations), 2) if evaluations else None,
        primary_average_score=round(mean(primary_scores), 2) if primary_scores else None,
        follow_ups=sum(t.follow_up_depth > 0 for t in turns),
        strong_areas=strong,
        weak_areas=weak,
        suggested_practice=[f"{r.skill}: {r.topic}" for r in weak[:5]],
        review_turn_ids=review,
        turns=[turn_view(db, t) for t in turns],
    )
