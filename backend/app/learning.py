"""Rebuildable evidence index and explainable learning rules. No LLM calls."""

from collections import defaultdict
from datetime import UTC
from hashlib import sha256

from fastapi import HTTPException
from sqlmodel import select

from app.interview_evaluation import validate_evaluation
from app.learning_content import identity, matches, normalized
from app.models import (
    BankQuestion,
    InterviewTurn,
    LearningEvidence,
    LearningTopic,
    TurnEvaluation,
)
from app.question_schemas import GenerateInput
from app.questions import candidates

LEVEL = {"incorrect": 0, "not_demonstrated": 0, "partial": 1, "demonstrated": 2}


def sync(db):
    """Validate original judgments, then index references atomically and idempotently."""
    old = {e.id: e for e in db.exec(select(LearningEvidence)).all()}
    topics = {t.id: t for t in db.exec(select(LearningTopic)).all()}
    seen, rejected = set(), 0
    for evaluation, turn in db.exec(
        select(TurnEvaluation, InterviewTurn).join(
            InterviewTurn, TurnEvaluation.turn_id == InterviewTurn.id
        )
    ).all():
        try:
            if turn.evaluation_state != "succeeded" or not turn.answer_text:
                raise ValueError("Incomplete evaluation")
            score, validated = validate_evaluation(evaluation.result["judgment"], turn)
            if score != evaluation.score or validated != evaluation.result:
                raise ValueError("Stored evaluation does not match its evidence")
            grouped = defaultdict(list)
            for signal in validated["judgment"]["topics"]:
                key, skill, topic = identity(turn.snapshot["content"]["skill"], signal["topic"])
                grouped[(key, skill, topic)].append(signal)
        except ValueError, TypeError, KeyError, AttributeError:
            rejected += 1
            continue
        ratings = validated["judgment"]["dimensions"]
        strong_rubric = all(r["score"] >= 2 for r in ratings) and score >= 7.5
        for (key, skill, topic), signals in grouped.items():
            if key not in topics:
                topics[key] = LearningTopic(
                    id=key,
                    skill=skill,
                    topic=topic,
                    category=turn.snapshot["content"]["category"],
                    created_at=evaluation.created_at,
                    updated_at=evaluation.created_at,
                )
                db.add(topics[key])
                db.flush()
            assessment = min(signals, key=lambda s: (LEVEL[s["status"]], s["status"]))["status"]
            eid = sha256(f"{key}:{evaluation.id}".encode()).hexdigest()[:32]
            value = LearningEvidence(
                id=eid,
                topic_id=key,
                evaluation_id=evaluation.id,
                raw_topics=sorted(s["topic"] for s in signals),
                assessment=assessment,
                strong=assessment == "demonstrated" and strong_rubric,
                observed_at=evaluation.created_at,
            )
            if eid not in old:
                db.add(value)
            else:
                for name in ("raw_topics", "assessment", "strong", "observed_at"):
                    setattr(old[eid], name, getattr(value, name))
                db.add(old[eid])
            seen.add(eid)
    for key, row in old.items():
        if key not in seen:
            db.delete(row)
    db.flush()
    return rejected


def require_topic(db, key):
    topic = db.get(LearningTopic, key)
    if (
        not topic
        or not db.exec(select(LearningEvidence).where(LearningEvidence.topic_id == key)).first()
    ):
        raise HTTPException(404, "No verified learning evidence for this topic.")
    return topic


def records(db, key):
    return db.exec(
        select(LearningEvidence, TurnEvaluation, InterviewTurn)
        .join(TurnEvaluation, LearningEvidence.evaluation_id == TurnEvaluation.id)
        .join(InterviewTurn, TurnEvaluation.turn_id == InterviewTurn.id)
        .where(LearningEvidence.topic_id == key)
        .order_by(LearningEvidence.observed_at, LearningEvidence.id)
    ).all()


def jd_context(db, target_id):
    if not target_id:
        return {}
    try:
        options = candidates(db, GenerateInput(target_id=target_id))
    except ValueError, TypeError, KeyError:
        raise HTTPException(422, "Selected JD needs valid confirmed source evidence.") from None
    result = {}
    for option in options:
        skill = identity(option["question"]["skill"], "")[1]
        result[normalized(skill)] = option["evidence"]
    return result


def iso(value):
    return value.replace(tzinfo=UTC).isoformat() if value else None


def view(db, topic, context):
    evidence = records(db, topic.id)
    weak = [r for r in evidence if r[0].assessment != "demonstrated"]
    sessions = defaultdict(list)
    for row in evidence:
        sessions[row[2].session_id].append(row)
    timeline = []
    for session_id, rows in sessions.items():
        level = min(
            LEVEL[e.assessment] if not (e.assessment == "demonstrated" and not e.strong) else 1
            for e, _, _ in rows
        )
        timeline.append(
            {
                "session_id": session_id,
                "level": level,
                "assessment": ["weak", "partial", "strong"][level],
                "at": iso(max(e.observed_at for e, _, _ in rows)),
                "evidence_count": len(rows),
                "follow_up_recovery": any(t.follow_up_depth and e.strong for e, _, t in rows)
                and any(e.assessment != "demonstrated" for e, _, _ in rows),
            }
        )
    timeline.sort(key=lambda r: (r["at"], r["session_id"]))
    weak_sessions = len({t.session_id for _, _, t in weak})
    direct_sessions = len(
        {
            t.session_id
            for e, ev, t in weak
            if any(
                s["evidence"] for s in ev.result["judgment"]["topics"] if s["topic"] in e.raw_topics
            )
        }
    )
    positive_tail = 0
    for point in reversed(timeline):
        if point["level"] != 2:
            break
        positive_tail += 1
    improving = bool(
        weak
        and timeline
        and (
            positive_tail > 0
            or (timeline[-1]["level"] == 1 and any(p["level"] == 0 for p in timeline[:-1]))
        )
    )
    status = (
        (
            "resolved"
            if weak and positive_tail >= 3
            else "improving"
            if improving
            else "practicing"
            if topic.practicing
            else "detected"
        )
        if weak
        else None
    )
    strength = "repeated" if positive_tail >= 2 else "emerging" if positive_tail == 1 else None
    jd = context.get(normalized(topic.skill))
    required = bool(jd and any(c["requirement"] == "must_have" for c in jd["jd_claims"]))
    severity = (
        "high" if weak_sessions >= 2 and required else "medium" if weak_sessions >= 2 else "low"
    )
    severity_reason = f"Observed in {weak_sessions} independent interviews. " + (
        "The selected JD explicitly requires this skill."
        if required
        else "No selected must-have JD requirement raises the general priority."
    )
    confidence = (
        "high"
        if weak_sessions >= 3 and direct_sessions >= 2
        else "medium"
        if weak_sessions >= 2
        else "low"
    )
    confidence_reason = (
        f"{weak_sessions} independent weak-signal interviews; "
        f"{direct_sessions} contain direct answer excerpts. "
        "Follow-ups are supporting evidence, not independent confirmation. "
        "Not statistical certainty."
    )
    return {
        "id": topic.id,
        "skill": topic.skill,
        "topic": topic.topic,
        "category": topic.category,
        "description": f"Recorded answer assessments concerning {topic.topic}.",
        "status": status,
        "practicing": topic.practicing,
        "revision": topic.revision,
        "severity": severity if weak else None,
        "severity_reason": severity_reason,
        "confidence": confidence if weak else None,
        "confidence_reason": confidence_reason,
        "occurrence_count": len(weak),
        "independent_interviews": weak_sessions,
        "evidence_count": len(evidence),
        "positive_count": sum(e.strong for e, _, _ in evidence),
        "first_detected_at": iso(weak[0][0].observed_at) if weak else None,
        "last_detected_at": iso(weak[-1][0].observed_at) if weak else None,
        "last_evidence_at": iso(evidence[-1][0].observed_at),
        "created_at": iso(topic.created_at),
        "updated_at": max(iso(topic.updated_at), iso(evidence[-1][0].observed_at)),
        "strength_signal": strength,
        "improvement_signal": (
            "Three later strong interviews; resolved for now, not mastery."
            if status == "resolved"
            else "Improvement detected in later interview evidence."
            if improving
            else "No cross-interview improvement established."
        ),
        "timeline": timeline,
        "jd_relevant": bool(jd),
        "jd_required": required,
        "jd_evidence": jd["jd_claims"] if jd else [],
    }


def evidence_view(db, key):
    output = []
    for signal, evaluation, turn in records(db, key):
        quotes = []
        for topic in evaluation.result["judgment"]["topics"]:
            if topic["topic"] in signal.raw_topics:
                for e in topic["evidence"]:
                    end = min(e["end"], e["start"] + 240)
                    quotes.append(
                        {
                            "start": e["start"],
                            "end": end,
                            "quote": turn.answer_text[e["start"] : end],
                        }
                    )
        output.append(
            {
                "id": signal.id,
                "session_id": turn.session_id,
                "turn_id": turn.id,
                "question_id": turn.question_id,
                "evaluation_id": evaluation.id,
                "question": turn.snapshot["content"]["question_text"],
                "primary_number": turn.primary_number,
                "follow_up_depth": turn.follow_up_depth,
                "assessment": signal.assessment,
                "strong": signal.strong,
                "observed_at": iso(signal.observed_at),
                "evidence": quotes[:3],
                "absence_note": (
                    "No supporting excerpt was identified by the evaluator. "
                    "Inspect the saved answer."
                )
                if not quotes
                else None,
            }
        )
    return output


def practice_questions(db, topic, target_id=None):
    links = {}
    if target_id:
        # Reuse M3's evidence validation and eligibility, not a second generator.
        try:
            links = {
                o["question"]["candidate_id"]: o
                for o in candidates(db, GenerateInput(target_id=target_id))
            }
        except ValueError, TypeError, KeyError:
            raise HTTPException(422, "Selected JD needs valid confirmed source evidence.") from None
    history = defaultdict(int)
    for turn in db.exec(select(InterviewTurn).where(InterviewTurn.asked_at.is_not(None))).all():
        history[turn.question_id] += 1
    questions = []
    for q in db.exec(
        select(BankQuestion).where(BankQuestion.active, BankQuestion.source == "curated")
    ).all():
        if matches(q.content, topic.id):
            questions.append(
                {
                    "id": q.id,
                    "question_text": q.content["question_text"],
                    "difficulty": q.content["difficulty"],
                    "status": q.status,
                    "times_asked": history[q.id],
                    "jd_relevant": q.id in links,
                }
            )
    return sorted(
        questions,
        key=lambda q: (
            not q["jd_relevant"],
            q["status"] != "needs_review",
            q["times_asked"],
            q["status"] == "mastered",
            q["id"],
        ),
    )


def recommendation(db, topic, value, target_id=None):
    questions = practice_questions(db, topic, target_id)
    active = bool(value["status"] and value["status"] != "resolved")
    reason = (
        (
            f"{value['occurrence_count']} weak assessments across "
            f"{value['independent_interviews']} interviews; "
            f"{value['confidence']} confidence. "
            + (
                "The selected JD requires this skill. "
                if value["jd_required"]
                else "Related to the selected JD. "
                if value["jd_relevant"]
                else "General practice, not a selected JD priority. "
            )
            + value["improvement_signal"]
        )
        if active
        else "No active weakness recommendation. Optional maintenance practice."
    )
    return {
        "topic_id": topic.id,
        "recommended": active,
        "reason": reason,
        "evidence_ids": [
            e.id for e, _, _ in records(db, topic.id) if e.assessment != "demonstrated"
        ],
        "questions": questions,
        "available": len(questions),
        "limitation": None
        if questions
        else (
            "No exact-topic question is available in the curated bank. "
            "No unrelated question substituted."
        ),
    }
