"""add firewall policy fields to configurations

Revision ID: b7e2f4a1c903
Revises: a3f1d8e92b01
Create Date: 2026-03-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2f4a1c903'
down_revision: Union[str, None] = 'a3f1d8e92b01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('configurations', sa.Column('allow_peer_to_peer', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('configurations', sa.Column('allow_lan_to_peers', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('configurations', 'allow_lan_to_peers')
    op.drop_column('configurations', 'allow_peer_to_peer')
