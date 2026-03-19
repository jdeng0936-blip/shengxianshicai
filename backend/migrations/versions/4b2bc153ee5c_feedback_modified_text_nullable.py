"""feedback_log modified_text nullable

Revision ID: 4b2bc153ee5c
Revises: 0689c114187d
"""
from alembic import op
import sqlalchemy as sa

revision = "4b2bc153ee5c"
down_revision = "0689c114187d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("feedback_log", "modified_text",
                    existing_type=sa.Text(),
                    nullable=True)


def downgrade() -> None:
    op.alter_column("feedback_log", "modified_text",
                    existing_type=sa.Text(),
                    nullable=False,
                    server_default="")
