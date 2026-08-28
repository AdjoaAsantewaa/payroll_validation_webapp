"""add user is_admin

Adds an `is_admin` capability flag to `users`, defaulting to false for every
existing row. This is a flag on top of the existing specialist/submitter
Role enum, not a new role -- an admin is a specialist who can also create
submitter accounts, not a distinct account type.

Revision ID: 8a9c80d52b5e
Revises: f5c5f78e908e
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a9c80d52b5e'
down_revision: Union[str, None] = 'f5c5f78e908e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
