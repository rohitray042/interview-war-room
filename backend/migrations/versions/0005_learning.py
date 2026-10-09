"""Evidence-derived learning topics and references; no duplicated answers."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_topics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("skill", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("practicing", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "learning_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("topic_id", sa.String(), sa.ForeignKey("learning_topics.id"), nullable=False),
        sa.Column(
            "evaluation_id", sa.String(), sa.ForeignKey("turn_evaluations.id"), nullable=False
        ),
        sa.Column("raw_topics", sa.JSON(), nullable=False),
        sa.Column("assessment", sa.String(), nullable=False),
        sa.Column("strong", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("topic_id", "evaluation_id", name="uq_learning_evidence"),
    )
    op.create_index("ix_learning_evidence_topic_id", "learning_evidence", ["topic_id"])


def downgrade():
    op.drop_index("ix_learning_evidence_topic_id", table_name="learning_evidence")
    op.drop_table("learning_evidence")
    op.drop_table("learning_topics")
