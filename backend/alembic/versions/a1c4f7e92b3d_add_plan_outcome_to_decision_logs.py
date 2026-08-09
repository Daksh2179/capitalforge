"""add plan_outcome to decision_logs

Revision ID: a1c4f7e92b3d
Revises: 3a11cbc5313a
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1c4f7e92b3d'
down_revision: Union[str, None] = '3a11cbc5313a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('decision_logs', sa.Column('plan_outcome', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('decision_logs', 'plan_outcome')