"""add theme_preference to users

Revision ID: a3f1d8e92b01
Revises: 0741bc76e748
Create Date: 2026-03-30 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a3f1d8e92b01'
down_revision: Union[str, None] = '0741bc76e748'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('theme_preference', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='auto'))


def downgrade() -> None:
    op.drop_column('users', 'theme_preference')