"""institute public site fields (Task F.8 Tier 2)

Revision ID: d4e5f6a7b8c9
Revises: a24386059615
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "a24386059615"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Institute", sa.Column("slug", sa.String(), nullable=True))
    op.create_unique_constraint("uq_institute_slug", "Institute", ["slug"])
    op.create_index("ix_institute_slug", "Institute", ["slug"])
    op.add_column("Institute", sa.Column("address", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("phone_public", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("email_public", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("description", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("course_fee_display", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("color_scheme", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("Institute", "color_scheme")
    op.drop_column("Institute", "course_fee_display")
    op.drop_column("Institute", "description")
    op.drop_column("Institute", "email_public")
    op.drop_column("Institute", "phone_public")
    op.drop_column("Institute", "address")
    op.drop_index("ix_institute_slug", table_name="Institute")
    op.drop_constraint("uq_institute_slug", "Institute", type_="unique")
    op.drop_column("Institute", "slug")
