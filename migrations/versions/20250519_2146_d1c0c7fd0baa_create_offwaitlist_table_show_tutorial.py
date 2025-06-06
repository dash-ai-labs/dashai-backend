"""create OffWaitlist table. Show tutorial

Revision ID: d1c0c7fd0baa
Revises: 0ca4a8975649
Create Date: 2025-05-19 21:46:54.918625

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1c0c7fd0baa"
down_revision: Union[str, None] = "0ca4a8975649"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "off_waitlist",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_off_waitlist_email"), "off_waitlist", ["email"], unique=True
    )
    op.create_index(op.f("ix_off_waitlist_id"), "off_waitlist", ["id"], unique=False)
    op.add_column("users", sa.Column("show_tutorial", sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "show_tutorial")
    op.drop_index(op.f("ix_off_waitlist_id"), table_name="off_waitlist")
    op.drop_index(op.f("ix_off_waitlist_email"), table_name="off_waitlist")
    op.drop_table("off_waitlist")
    # ### end Alembic commands ###
