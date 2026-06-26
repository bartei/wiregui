"""add priority to rules

Firewall rules are materialized into per-user nftables chains, which are
evaluated top-to-bottom. Without an explicit order the rules were emitted in
non-deterministic DB order, so a "drop all" rule could be placed before the
"accept" rules it was meant to follow. The priority column makes the order
explicit (lower number = evaluated first).

Revision ID: d8b3a1f06e57
Revises: c5a9f3e21d04
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8b3a1f06e57'
down_revision: Union[str, None] = 'c5a9f3e21d04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rules', sa.Column('priority', sa.Integer(), nullable=False, server_default='100'))
    op.create_index('ix_rules_priority', 'rules', ['priority'])


def downgrade() -> None:
    op.drop_index('ix_rules_priority', table_name='rules')
    op.drop_column('rules', 'priority')
