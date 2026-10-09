"""Foundation: local profile. Interview tables belong to their later milestones."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("singleton_key", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("background", sa.String(), nullable=False),
        sa.Column("target_role", sa.String(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("learning_skills", sa.JSON(), nullable=False),
        sa.Column("daily_study_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("singleton_key = 1", name="ck_single_profile"),
        sa.CheckConstraint("daily_study_minutes BETWEEN 5 AND 480", name="ck_study_minutes"),
    )
    op.create_index("ix_profiles_singleton_key", "profiles", ["singleton_key"], unique=True)


def downgrade():
    op.drop_index("ix_profiles_singleton_key", table_name="profiles")
    op.drop_table("profiles")
