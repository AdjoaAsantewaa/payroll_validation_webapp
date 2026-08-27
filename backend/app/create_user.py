"""Create a real login (specialist or submitter) without a public sign-up
endpoint. Uses the same password hashing and User model as normal auth --
this is not a separate auth system, just a command-line insert.

Usage (interactive):
    python -m app.create_user

Usage (non-interactive, e.g. for scripting/CI):
    python -m app.create_user --email you@company.com --password "..." \\
        --name "Your Name" --role specialist

    python -m app.create_user --email you@company.com --password "..." \\
        --name "Your Name" --role submitter --department "Finance"

Run this against whichever DATABASE_URL you want the account created in --
export DATABASE_URL (or set it in backend/.env) to point at Supabase before
running it against production.
"""
import argparse
import getpass
import sys

from app.database import SessionLocal
from app.models import Department, Role, User
from app.security import hash_password


def list_departments(db) -> list[Department]:
    return db.query(Department).order_by(Department.name).all()


def prompt_department(db) -> Department:
    depts = list_departments(db)
    if not depts:
        print("No departments found. Seed the database first (python -m app.seed).")
        sys.exit(1)
    print("\nDepartments:")
    for i, d in enumerate(depts, start=1):
        print(f"  {i}. {d.name}")
    while True:
        choice = input("Select a department (number): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(depts):
            return depts[int(choice) - 1]
        print("Invalid choice, try again.")


def create_user(email: str, password: str, name: str, role: str,
                 department_name: str | None) -> None:
    db = SessionLocal()
    try:
        email = email.strip().lower()
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"A user with email {email} already exists (id={existing.id}, role={existing.role.value}).")
            sys.exit(1)

        if role not in ("specialist", "submitter"):
            print("role must be 'specialist' or 'submitter'")
            sys.exit(1)

        department_id = None
        if role == "submitter":
            if department_name:
                dept = db.query(Department).filter(Department.name == department_name).first()
                if not dept:
                    names = ", ".join(d.name for d in list_departments(db))
                    print(f"Department '{department_name}' not found. Available: {names}")
                    sys.exit(1)
            else:
                dept = prompt_department(db)
            department_id = dept.id

        initials = "".join(part[0] for part in name.split() if part)[:2].upper() or "U"

        user = User(
            email=email, name=name, initials=initials,
            role=Role(role), password_hash=hash_password(password),
            department_id=department_id,
        )
        db.add(user)
        db.commit()

        dept_note = f" in {dept.name}" if role == "submitter" else ""
        print(f"Created {role} user '{name}' <{email}>{dept_note}. You can sign in now.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Create a Payroll Validation user account.")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--name")
    parser.add_argument("--role", choices=["specialist", "submitter"])
    parser.add_argument("--department", help="Required for --role submitter")
    args = parser.parse_args()

    email = args.email or input("Email: ").strip()
    name = args.name or input("Full name: ").strip()
    role = args.role
    if not role:
        role = ""
        while role not in ("specialist", "submitter"):
            role = input("Role (specialist/submitter): ").strip().lower()

    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.")
            sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)

    create_user(email, password, name, role, args.department)


if __name__ == "__main__":
    main()
