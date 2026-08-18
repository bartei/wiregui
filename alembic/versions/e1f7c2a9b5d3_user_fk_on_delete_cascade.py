"""user FKs ON DELETE CASCADE

Deleting a user failed with a FK violation whenever any child row existed
(issue #7: OIDC auto-created users always have an oidc_connections row, so the
admin Delete button silently did nothing). The initial schema created all
user_id foreign keys without any ON DELETE behavior; recreate them with
ON DELETE CASCADE so the database removes a user's devices, rules, MFA
methods, API tokens and OIDC connections atomically. Rules with a NULL
user_id (global rules) are unaffected.

Revision ID: e1f7c2a9b5d3
Revises: c8d3e5f1a204
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1f7c2a9b5d3'
down_revision: Union[str, None] = 'c8d3e5f1a204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The initial migration created these FKs unnamed, so they carry the
# Postgres default constraint name <table>_user_id_fkey.
_TABLES = ('devices', 'rules', 'mfa_methods', 'api_tokens', 'oidc_connections')


def upgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f'{table}_user_id_fkey', table, type_='foreignkey')
        op.create_foreign_key(
            f'{table}_user_id_fkey', table, 'users',
            ['user_id'], ['id'], ondelete='CASCADE',
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f'{table}_user_id_fkey', table, type_='foreignkey')
        op.create_foreign_key(
            f'{table}_user_id_fkey', table, 'users',
            ['user_id'], ['id'],
        )
