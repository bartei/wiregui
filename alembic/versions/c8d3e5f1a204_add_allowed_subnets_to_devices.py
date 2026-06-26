"""add allowed_subnets to devices

Revision ID: c8d3e5f1a204
Revises: d8b3a1f06e57
Create Date: 2026-06-05 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c8d3e5f1a204'
down_revision: Union[str, None] = 'd8b3a1f06e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('devices', sa.Column('allowed_subnets', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('devices', 'allowed_subnets')
