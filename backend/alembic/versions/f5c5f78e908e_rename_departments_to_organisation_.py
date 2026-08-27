"""rename departments to organisation-neutral names

Data-only migration: renames the 12 existing department rows in place
(UPDATE, not delete+recreate) so every foreign key that references
departments.id -- users, employees, submissions, exceptions, correction
queries, audit log entries -- keeps working unchanged. Nothing about the
submission-versioning fix in the previous migration depends on this; it's
kept separate so each migration has one job.

Renaming in place, rather than via seed.py, is what actually changes an
already-populated database (Supabase or otherwise) -- seed.py only ever
inserts on a database that has zero Department rows, so on its own it does
nothing here.

Mapping (old -> new), matching app/seed.py's fresh-seed narrative:
    Nursing                -> Operations
    Facilities             -> Finance
    Transport               -> Human Resources
    Catering                -> Information Technology
    Estates                 -> Sales & Business Development
    Security                 -> Marketing & Communications
    Library                  -> Procurement
    Housekeeping             -> Customer Services
    Maintenance              -> Legal & Compliance
    IT Support                -> Facilities & Administration
    Administration            -> Quality & Risk
    Grounds                    -> Corporate Services

Idempotent: each UPDATE only matches rows still bearing the old name, so a
second run is a no-op. Defensive: if a row with the target new name already
exists (e.g. a partial manual rename happened before this ran), that pair is
skipped rather than raising a unique-constraint error -- skipped pairs are
printed so they can be reviewed and fixed by hand. If your live database has
department names outside this list (e.g. you already renamed some
yourself, or seeded with different names), they are left untouched; extend
RENAMES below and re-run if you need those covered too.

Revision ID: f5c5f78e908e
Revises: 4357a514d586
Create Date: 2026-08-26 21:39:52.627040

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5c5f78e908e'
down_revision: Union[str, None] = '4357a514d586'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RENAMES = [
    ("Nursing", "Operations"),
    ("Facilities", "Finance"),
    ("Transport", "Human Resources"),
    ("Catering", "Information Technology"),
    ("Estates", "Sales & Business Development"),
    ("Security", "Marketing & Communications"),
    ("Library", "Procurement"),
    ("Housekeeping", "Customer Services"),
    ("Maintenance", "Legal & Compliance"),
    ("IT Support", "Facilities & Administration"),
    ("Administration", "Quality & Risk"),
    ("Grounds", "Corporate Services"),
]


def _slug_email(name: str) -> str:
    slug = name.lower().replace(" & ", "").replace(" ", "")
    return f"{slug}.payroll@company.com"


def _apply_renames(pairs: list[tuple[str, str]]) -> None:
    bind = op.get_bind()
    departments_t = sa.table(
        "departments",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("contact_email", sa.String),
    )

    existing_names = {
        row[0] for row in bind.execute(sa.text("SELECT name FROM departments")).fetchall()
    }

    skipped = []
    for old_name, new_name in pairs:
        if old_name not in existing_names:
            continue  # nothing to rename -- already renamed, or never existed here
        if new_name in existing_names:
            skipped.append((old_name, new_name))
            continue
        bind.execute(
            departments_t.update()
            .where(departments_t.c.name == old_name)
            .values(name=new_name, contact_email=_slug_email(new_name))
        )
        existing_names.discard(old_name)
        existing_names.add(new_name)

    if skipped:
        print(
            "WARNING: skipped renaming the following departments because a row with "
            "the target name already exists -- review and fix manually if needed: "
            + ", ".join(f"{old!r} -> {new!r}" for old, new in skipped)
        )


def upgrade() -> None:
    _apply_renames(RENAMES)


def downgrade() -> None:
    _apply_renames([(new, old) for old, new in RENAMES])
