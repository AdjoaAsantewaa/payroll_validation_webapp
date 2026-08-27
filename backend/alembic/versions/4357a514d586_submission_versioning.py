"""submission versioning

Adds version/is_current/superseded_at to submissions and enforces (at the
database level, not just in application code) that at most one submission
row can be "current" per (department_id, cycle_id).

This is a data migration as much as a schema one: if this database already
has duplicate submission rows for the same department+cycle -- e.g. from a
race between two concurrent uploads before this fix existed, which is the
believed root cause of exception counts that didn't match between the
submitter's and specialist's views -- adding the new NOT NULL columns and
the partial-unique constraint would fail outright against that data. So
this migration first assigns version numbers within each (department_id,
cycle_id) group by id order and marks only the highest-id row in each group
"current", before adding the constraints.

Review before running against real production data: the "highest id = most
recent = correct current version" heuristic is a reasonable default but is
a judgment call about data this migration can't fully see ahead of time.
Older rows in a group become historical/superseded (is_current=False), not
deleted -- nothing here is destructive.

Revision ID: 4357a514d586
Revises: ad87728f6413
Create Date: 2026-08-26 18:59:15.634245

"""
import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4357a514d586'
down_revision: Union[str, None] = 'ad87728f6413'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable first -- existing rows get real values via the data
    # migration below before NOT NULL is enforced.
    op.add_column('submissions', sa.Column('version', sa.Integer(), nullable=True))
    op.add_column('submissions', sa.Column('is_current', sa.Boolean(), nullable=True))
    op.add_column('submissions', sa.Column('superseded_at', sa.DateTime(), nullable=True))

    bind = op.get_bind()
    submissions_t = sa.table(
        'submissions',
        sa.column('id', sa.Integer),
        sa.column('department_id', sa.Integer),
        sa.column('cycle_id', sa.Integer),
        sa.column('version', sa.Integer),
        sa.column('is_current', sa.Boolean),
        sa.column('superseded_at', sa.DateTime),
    )

    existing = bind.execute(sa.text(
        "SELECT id, department_id, cycle_id FROM submissions ORDER BY department_id, cycle_id, id"
    )).fetchall()

    groups: dict[tuple, list[int]] = {}
    for row in existing:
        key = (row.department_id, row.cycle_id)
        groups.setdefault(key, []).append(row.id)

    now = datetime.datetime.utcnow()
    for ids in groups.values():
        for i, sub_id in enumerate(ids, start=1):
            is_last = i == len(ids)
            bind.execute(
                submissions_t.update()
                .where(submissions_t.c.id == sub_id)
                .values(
                    version=i,
                    is_current=is_last,
                    superseded_at=None if is_last else now,
                )
            )

    # batch_alter_table: SQLite has no ALTER COLUMN ... SET NOT NULL and no
    # ALTER TABLE ADD CONSTRAINT at all; Alembic emulates both there via a
    # single rebuild-and-copy. Passes through as plain ALTER statements on
    # Postgres. The plain (non-partial) indexes below don't need batching --
    # SQLite supports CREATE INDEX, including partial (WHERE) indexes,
    # without a table rebuild.
    with op.batch_alter_table('submissions') as batch_op:
        batch_op.alter_column('version', nullable=False)
        batch_op.alter_column('is_current', nullable=False)
        batch_op.create_unique_constraint(
            'uq_submission_dept_cycle_version', ['department_id', 'cycle_id', 'version'])

    op.create_index(op.f('ix_exceptions_status'), 'exceptions', ['status'], unique=False)
    op.create_index(op.f('ix_exceptions_submission_id'), 'exceptions', ['submission_id'], unique=False)
    op.create_index(op.f('ix_submission_rows_submission_id'), 'submission_rows', ['submission_id'], unique=False)
    op.create_index(op.f('ix_submissions_cycle_id'), 'submissions', ['cycle_id'], unique=False)
    op.create_index(op.f('ix_submissions_department_id'), 'submissions', ['department_id'], unique=False)
    op.create_index(
        'uq_submission_one_current_per_dept_cycle', 'submissions', ['department_id', 'cycle_id'],
        unique=True, sqlite_where=sa.text('is_current'), postgresql_where=sa.text('is_current'))


def downgrade() -> None:
    op.drop_index('uq_submission_one_current_per_dept_cycle', table_name='submissions',
                   sqlite_where=sa.text('is_current'), postgresql_where=sa.text('is_current'))
    op.drop_index(op.f('ix_submissions_department_id'), table_name='submissions')
    op.drop_index(op.f('ix_submissions_cycle_id'), table_name='submissions')

    with op.batch_alter_table('submissions') as batch_op:
        batch_op.drop_constraint('uq_submission_dept_cycle_version', type_='unique')
        batch_op.drop_column('superseded_at')
        batch_op.drop_column('is_current')
        batch_op.drop_column('version')

    op.drop_index(op.f('ix_submission_rows_submission_id'), table_name='submission_rows')
    op.drop_index(op.f('ix_exceptions_submission_id'), table_name='exceptions')
    op.drop_index(op.f('ix_exceptions_status'), table_name='exceptions')
