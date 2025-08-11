"""Add email_id to weekly_email_recaps

Revision ID: 8ce6bddcd6fe
Revises: 96c1eddfddac
Create Date: 2025-08-11 20:10:34.083222

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ce6bddcd6fe"
down_revision: Union[str, None] = "96c1eddfddac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Drop the old 'email_ids' column (array UUID)
    op.drop_column("weekly_email_recaps", "email_ids")

    # Add the new 'email_id' column
    op.add_column("weekly_email_recaps", sa.Column("email_id", sa.UUID(), nullable=False))

    # Add foreign key constraint from email_id -> emails.id
    op.create_foreign_key(
        "fk_weekly_email_recaps_email_id_emails",
        "weekly_email_recaps",
        "emails",
        ["email_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_weekly_email_recaps_email_id_emails", "weekly_email_recaps", type_="foreignkey")
    op.drop_column("weekly_email_recaps", "email_id")

    # Recreate the old 'email_ids' column as ARRAY(UUID)
    op.add_column("weekly_email_recaps", sa.Column("email_ids", sa.ARRAY(sa.UUID()), nullable=True))
