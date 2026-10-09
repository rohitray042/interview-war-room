"""Immutable document sources, reviewed analyses, and target comparisons."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("kind", "content_hash", name="uq_document_content"),
        sa.CheckConstraint("kind IN ('resume', 'jd')", name="ck_document_kind"),
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'confirmed')", name="ck_analysis_status"),
    )
    op.create_index("ix_analyses_document_id", "analyses", ["document_id"])
    op.create_table(
        "targets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("resume_id", sa.String(), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column("jd_id", sa.String(), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("resume_id", "jd_id", name="uq_target_pair"),
    )


def downgrade():
    op.drop_table("targets")
    op.drop_index("ix_analyses_document_id", table_name="analyses")
    op.drop_table("analyses")
    op.drop_table("documents")
