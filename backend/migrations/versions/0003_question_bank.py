"""Question catalog cache, generated questions, personal state and target evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bank_questions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("normalized_text", sa.String(), nullable=False, unique=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_reference", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("bookmarked", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("source IN ('curated', 'generated')"),
        sa.CheckConstraint(
            "status IN ('new', 'in_progress', 'practiced', 'needs_review', 'mastered')"
        ),
    )
    op.create_table(
        "question_targets",
        sa.Column("question_id", sa.String(), sa.ForeignKey("bank_questions.id"), primary_key=True),
        sa.Column("target_id", sa.String(), sa.ForeignKey("targets.id"), primary_key=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("question_targets")
    op.drop_table("bank_questions")
