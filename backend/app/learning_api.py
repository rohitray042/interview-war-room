from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlmodel import select

from app.contracts import StrictModel
from app.interview_schemas import InterviewInput, Token
from app.interviews import create_interview, session_view, write_session
from app.learning import (
    evidence_view,
    jd_context,
    recommendation,
    require_topic,
    sync,
    view,
)
from app.learning_content import normalized
from app.models import LearningTopic, utc_now

router = APIRouter(prefix="/api/v1/weaknesses", tags=["learning"])


class StatusInput(StrictModel):
    status: Literal["detected", "practicing"]
    revision: int = Field(ge=1)


class PracticeInput(StrictModel):
    request_id: Token
    mode: Literal["study", "interview"] = "study"
    target_id: str | None = None
    number_of_questions: int = Field(default=1, ge=1, le=5)


@router.get("")
def listing(
    request: Request,
    target_id: str | None = None,
    status: Literal["all", "active", "improving", "resolved", "strengths", "jd_relevant"] = "all",
    category: str = "",
    severity: Literal["", "low", "medium", "high"] = "",
    search: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    with write_session(request.app.state.engine) as db:
        rejected = sync(db)
        context = jd_context(db, target_id)
        items = []
        for topic in db.exec(select(LearningTopic)).all():
            try:
                require_topic(db, topic.id)
            except HTTPException:
                continue
            items.append(view(db, topic, context))
        stats = {
            "active": sum(bool(v["status"] and v["status"] != "resolved") for v in items),
            "improving": sum(v["status"] == "improving" for v in items),
            "resolved": sum(v["status"] == "resolved" for v in items),
            "strengths": sum(bool(v["strength_signal"]) for v in items),
            "jd_relevant": sum(bool(v["status"] and v["jd_relevant"]) for v in items),
        }
        categories = sorted({v["category"] for v in items})
        filtered = [
            v
            for v in items
            if (
                status == "all"
                or status == "active"
                and v["status"] in {"detected", "practicing", "improving"}
                or status in {"improving", "resolved"}
                and v["status"] == status
                or status == "strengths"
                and v["strength_signal"]
                or status == "jd_relevant"
                and v["jd_relevant"]
                and v["status"]
            )
            and (not category or category == v["category"])
            and (not severity or severity == v["severity"])
            and all(
                word in normalized(f"{v['skill']} {v['topic']} {v['description']}")
                for word in normalized(search).split()
            )
        ]
        filtered.sort(
            key=lambda v: (
                v["status"] in {None, "resolved"},
                not v["jd_relevant"],
                {"high": 0, "medium": 1, "low": 2, None: 3}[v["severity"]],
                {"high": 0, "medium": 1, "low": 2, None: 3}[v["confidence"]],
                -v["independent_interviews"],
                v["status"] == "improving",
                v["skill"],
                v["topic"],
            )
        )
        for value in filtered[offset : offset + limit]:
            value["recommendation"] = recommendation(
                db, db.get(LearningTopic, value["id"]), value, target_id
            )
        return {
            "items": filtered[offset : offset + limit],
            "total": len(filtered),
            "stats": stats,
            "categories": categories,
            "excluded_evaluations": rejected,
            "policy_version": 1,
        }


@router.get("/{identity}")
def detail(identity: str, request: Request, target_id: str | None = None):
    with write_session(request.app.state.engine) as db:
        rejected = sync(db)
        topic = require_topic(db, identity)
        value = view(db, topic, jd_context(db, target_id))
        return {
            **value,
            "evidence": evidence_view(db, identity),
            "recommendation": recommendation(db, topic, value, target_id),
            "excluded_evaluations": rejected,
        }


@router.patch("/{identity}/status")
def status(identity: str, payload: StatusInput, request: Request):
    with write_session(request.app.state.engine) as db:
        sync(db)
        topic = require_topic(db, identity)
        value = view(db, topic, {})
        if not value["status"] or value["status"] == "resolved":
            raise HTTPException(
                409, "This topic has no active weakness. Resolution is evidence-derived."
            )
        if topic.revision != payload.revision:
            raise HTTPException(409, "Practice status changed. Reload before updating.")
        topic.practicing = payload.status == "practicing"
        topic.revision += 1
        topic.updated_at = utc_now()
        db.add(topic)
        db.flush()
        return view(db, topic, {})


@router.post("/{identity}/practice")
def practice(identity: str, payload: PracticeInput, request: Request):
    with write_session(request.app.state.engine) as db:
        sync(db)
        topic = require_topic(db, identity)
        value = view(db, topic, jd_context(db, payload.target_id))
        rec = recommendation(db, topic, value, payload.target_id)
        if not rec["available"]:
            raise HTTPException(422, rec["limitation"])
        result = {
            "focus_id": topic.id,
            "target_id": payload.target_id,
            "available": rec["available"],
        }
        if payload.mode == "interview":
            interview = create_interview(
                db,
                InterviewInput(
                    request_id=payload.request_id,
                    target_id=payload.target_id,
                    interview_type="mixed",
                    number_of_questions=payload.number_of_questions,
                    source="curated",
                    focus_id=topic.id,
                ),
                request.app.state.interview_content,
            )
            result["interview"] = session_view(db, interview)
        if value["status"] and value["status"] != "resolved" and not topic.practicing:
            topic.practicing = True
            topic.revision += 1
            topic.updated_at = utc_now()
            db.add(topic)
        return result
