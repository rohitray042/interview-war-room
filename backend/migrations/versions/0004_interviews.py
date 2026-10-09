"""Persistent interview state, immutable question snapshots and answer evaluations."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("request_id", sa.String(), unique=True, nullable=False),
        sa.Column("target_id", sa.String(), sa.ForeignKey("targets.id"), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("current_turn_id", sa.String(), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('not_started','active','paused','completed','abandoned')"),
        sa.CheckConstraint("total_questions BETWEEN 1 AND 20"),
    )
    op.create_table(
        "interview_turns",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_id", sa.String(), sa.ForeignKey("interview_sessions.id"), nullable=False
        ),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("primary_number", sa.Integer(), nullable=False),
        sa.Column("follow_up_depth", sa.Integer(), nullable=False),
        sa.Column(
            "parent_turn_id", sa.String(), sa.ForeignKey("interview_turns.id"), nullable=True
        ),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("asked_at", sa.DateTime(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.Column("answer_text", sa.String(), nullable=True),
        sa.Column("submission_id", sa.String(), nullable=True),
        sa.Column("evaluation_state", sa.String(), nullable=False),
        sa.Column("evaluation_error", sa.String(), nullable=True),
        sa.Column("lease_token", sa.String(), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "session_id", "primary_number", "follow_up_depth", name="uq_turn_position"
        ),
        sa.UniqueConstraint("session_id", "submission_id", name="uq_answer_submission"),
        sa.CheckConstraint("follow_up_depth BETWEEN 0 AND 2"),
        sa.CheckConstraint("primary_number BETWEEN 1 AND 20"),
        sa.CheckConstraint(
            "evaluation_state IN "
            "('unsubmitted','pending','evaluating','succeeded','failed','deferred')"
        ),
    )
    op.create_index("ix_interview_turns_session_id", "interview_turns", ["session_id"])
    op.create_table(
        "turn_evaluations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "turn_id", sa.String(), sa.ForeignKey("interview_turns.id"), unique=True, nullable=False
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("score BETWEEN 0 AND 10"),
    )


def downgrade():
    op.drop_table("turn_evaluations")
    op.drop_index("ix_interview_turns_session_id", table_name="interview_turns")
    op.drop_table("interview_turns")
    op.drop_table("interview_sessions")
