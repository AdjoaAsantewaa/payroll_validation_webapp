"""Read-only preview of what the submission-versioning + department-rename
migrations (4357a514d586, f5c5f78e908e) will do to a REAL database, before
you run them. Makes no writes -- SELECT only.

This exists because nobody -- including the person who wrote the migration
-- can honestly predict the resulting dashboard numbers without looking at
your actual data. It queries the pre-migration schema directly (no ORM
models, since the new version/is_current columns don't exist yet on a
database that hasn't been migrated), so it's safe to run against your
current live Supabase database right now, before touching anything.

Usage:
    cd backend
    DATABASE_URL="postgresql://...supabase pooler URL..." \\
        ./venv/Scripts/python -m app.preview_migration
"""
import sys

import sqlalchemy as sa

from app.config import DATABASE_URL

# Same mapping as alembic/versions/f5c5f78e908e_*.py -- kept in sync manually
# since this script intentionally doesn't import the migration module.
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


def main():
    engine = sa.create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print(f"Connected to: {engine.url.render_as_string(hide_password=True)}\n")

        _preview_departments(conn)
        print()
        _preview_submission_duplicates(conn)


def _preview_departments(conn):
    print("=== Department rename preview ===")
    rows = conn.execute(sa.text("SELECT name FROM departments")).fetchall()
    existing = {r[0] for r in rows}

    old_names = {old for old, _ in RENAMES}
    unmapped = existing - old_names - {new for _, new in RENAMES}
    if unmapped:
        print(f"Departments NOT covered by the rename mapping (left untouched): "
              f"{sorted(unmapped)}")

    for old_name, new_name in RENAMES:
        if old_name not in existing:
            continue
        if new_name in existing:
            print(f"  COLLISION -- '{old_name}' would be SKIPPED: a department named "
                  f"'{new_name}' already exists. Migration will leave both as-is; "
                  f"resolve manually.")
        else:
            print(f"  '{old_name}' -> '{new_name}'")

    if not any(old in existing for old, _ in RENAMES):
        print("  No old-style department names found -- nothing to rename "
              "(already renamed, or this database uses a different naming scheme).")


def _preview_submission_duplicates(conn):
    print("=== Submission versioning preview (the 175/162-style bug) ===")

    cycle_row = conn.execute(
        sa.text("SELECT id, label FROM cycles WHERE is_current = true")
    ).fetchone()
    if not cycle_row:
        print("  No current cycle found.")
        return
    cycle_id, cycle_label = cycle_row
    print(f"  Current cycle: {cycle_label} (id={cycle_id})\n")

    dept_rows = conn.execute(sa.text("SELECT id, name FROM departments")).fetchall()
    dept_names = {r[0]: r[1] for r in dept_rows}

    submissions = conn.execute(sa.text(
        "SELECT id, department_id, row_count, status, uploaded_at "
        "FROM submissions WHERE cycle_id = :cycle_id ORDER BY department_id, id"
    ), {"cycle_id": cycle_id}).fetchall()

    groups: dict[int, list] = {}
    for row in submissions:
        groups.setdefault(row.department_id, []).append(row)

    total_before = 0
    total_after = 0
    any_duplicates = False

    for dept_id, rows in groups.items():
        dept_name = dept_names.get(dept_id, f"department #{dept_id}")
        exc_counts = []
        for row in rows:
            count = conn.execute(sa.text(
                "SELECT COUNT(*) FROM exceptions WHERE submission_id = :sid "
                "AND status IN ('open', 'query_open')"
            ), {"sid": row.id}).scalar()
            exc_counts.append(count)

        before = sum(exc_counts)
        after = exc_counts[-1] if exc_counts else 0  # highest id = last in the list
        total_before += before
        total_after += after

        if len(rows) > 1:
            any_duplicates = True
            print(f"  {dept_name}: {len(rows)} submission rows found for this cycle "
                  f"(DUPLICATES -- this is the bug)")
            for row, count in zip(rows, exc_counts):
                marker = " <- becomes CURRENT" if row.id == rows[-1].id else " -> becomes historical"
                print(f"      id={row.id}  rows={row.row_count}  status={row.status}  "
                      f"uploaded={row.uploaded_at}  unresolved_exceptions={count}{marker}")
        elif rows:
            print(f"  {dept_name}: 1 submission (normal, no duplicates) -- "
                  f"{exc_counts[0]} unresolved exceptions")

    print(f"\n  TOTAL unresolved exceptions today (all rows, current buggy behavior): {total_before}")
    print(f"  TOTAL unresolved exceptions after migration (current version only):     {total_after}")
    if not any_duplicates:
        print("\n  No duplicate submissions found for the current cycle -- the before/after "
              "totals above should match, and the migration only adds the columns/constraint "
              "as a safeguard against this happening in the future.")
    else:
        print("\n  Nothing is deleted. Every row above stays in the database and remains "
              "viewable via GET /submissions/{id} (\"View submission\" in the UI) -- rows "
              "marked 'becomes historical' just stop counting toward dashboard/exception "
              "totals, the same way a fixed resubmission always should have.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- this is a diagnostic script
        print(f"Could not complete preview: {exc}", file=sys.stderr)
        sys.exit(1)
