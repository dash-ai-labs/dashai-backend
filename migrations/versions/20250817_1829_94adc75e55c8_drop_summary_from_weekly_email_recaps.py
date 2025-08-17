"""drop summary from weekly_email_recaps

Revision ID: 94adc75e55c8
Revises: ca30632bb435
Create Date: 2025-08-17 18:29:41.675737

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "94adc75e55c8"
down_revision: Union[str, None] = "ca30632bb435"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.drop_column('weekly_email_recaps', 'summary')

def downgrade():
    op.add_column('weekly_email_recaps',
        sa.Column('summary', sa.UnicodeText(), nullable=True)
    )