"""timestamps with time zone

SQLModel 0.0.47 maps `datetime` fields to TIMESTAMP WITH TIME ZONE and rejects
naive values on insert. Existing installs have TIMESTAMP WITHOUT TIME ZONE
columns holding UTC values, so convert them in place.

Revision ID: f2c4b7d18a90
Revises: e1f7c2a9b5d3
Create Date: 2026-09-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2c4b7d18a90'
down_revision: Union[str, None] = 'e1f7c2a9b5d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# table -> datetime columns
TIMESTAMP_COLUMNS: dict[str, tuple[str, ...]] = {
    'configurations': ('inserted_at', 'updated_at'),
    'connectivity_checks': ('inserted_at',),
    'users': (
        'last_signed_in_at',
        'sign_in_token_created_at',
        'disabled_at',
        'inserted_at',
        'updated_at',
    ),
    'api_tokens': ('expires_at', 'inserted_at'),
    'devices': ('latest_handshake', 'inserted_at', 'updated_at'),
    'mfa_methods': ('last_used_at', 'inserted_at', 'updated_at'),
    'oidc_connections': ('refreshed_at', 'inserted_at', 'updated_at'),
    'rules': ('inserted_at', 'updated_at'),
}


def upgrade() -> None:
    for table, columns in TIMESTAMP_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(timezone=True),
                existing_type=sa.DateTime(),
                # stored values were already UTC, just unlabelled
                postgresql_using=f'{column} AT TIME ZONE \'UTC\'',
            )


def downgrade() -> None:
    for table, columns in TIMESTAMP_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(),
                existing_type=sa.DateTime(timezone=True),
                postgresql_using=f'{column} AT TIME ZONE \'UTC\'',
            )
