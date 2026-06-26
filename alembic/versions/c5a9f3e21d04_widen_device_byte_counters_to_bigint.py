"""widen device byte counters to bigint

WireGuard rx/tx byte counters routinely exceed the int32 range (~2 GB). The
original INTEGER columns overflow once a peer transfers more than ~2 GB, which
makes the metrics collector's batched UPDATE fail with asyncpg DataError
("value out of int32 range") and abort the whole transaction — so latest_handshake
is never persisted and every device shows as "offline".

Revision ID: c5a9f3e21d04
Revises: b7e2f4a1c903
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5a9f3e21d04'
down_revision: Union[str, None] = 'b7e2f4a1c903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('devices', 'rx_bytes',
                    existing_type=sa.Integer(), type_=sa.BigInteger(),
                    existing_nullable=True)
    op.alter_column('devices', 'tx_bytes',
                    existing_type=sa.Integer(), type_=sa.BigInteger(),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column('devices', 'tx_bytes',
                    existing_type=sa.BigInteger(), type_=sa.Integer(),
                    existing_nullable=True)
    op.alter_column('devices', 'rx_bytes',
                    existing_type=sa.BigInteger(), type_=sa.Integer(),
                    existing_nullable=True)