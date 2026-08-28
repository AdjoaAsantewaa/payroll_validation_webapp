"""role admin, drop is_admin flag

Replaces the is_admin capability flag with a real `admin` value on the
Role enum. Product direction changed: an admin should log in as admin --
distinct from specialist and submitter, not a specialist with an extra
flag -- so role itself is now the single source of truth for what an
account can do.

Postgres stores Role as a native ENUM type, so adding a member needs
ALTER TYPE ... ADD VALUE (SQLite has no real enum type -- its CHECK
constraint there is regenerated from the Python enum on the next
create_all(), which only happens in local dev and never runs through
this migration, so no SQLite-specific handling is needed here).

Revision ID: b56c49075001
Revises: 8a9c80d52b5e
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b56c49075001'
down_revision: Union[str, None] = '8a9c80d52b5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'admin'")

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('is_admin')


def downgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Postgres has no ALTER TYPE ... DROP VALUE -- reassign any role='admin'
    # rows to 'specialist' (with is_admin=true) manually before downgrading
    # if this is ever run against real data.
