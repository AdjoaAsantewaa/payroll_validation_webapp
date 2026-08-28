import datetime
import enum

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON, Enum,
    UniqueConstraint, Index, text
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.datetime.utcnow()


class Role(str, enum.Enum):
    specialist = "specialist"
    submitter = "submitter"
    admin = "admin"


class EmployeeStatus(str, enum.Enum):
    active = "active"
    exited = "exited"


class SubmissionStatus(str, enum.Enum):
    not_submitted = "not_submitted"
    needs_review = "needs_review"
    query_sent = "query_sent"
    approved = "approved"


class ExceptionSeverity(str, enum.Enum):
    high = "high"
    med = "med"
    low = "low"


class ExceptionSource(str, enum.Enum):
    rule = "rule"
    ai = "ai"


class ExceptionStatus(str, enum.Enum):
    open = "open"
    accepted = "accepted"
    rejected = "rejected"
    query_open = "query_open"
    query_answered = "query_answered"


class QueryStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    answered = "answered"


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    contact_email = Column(String, nullable=True)

    users = relationship("User", back_populates="department")
    employees = relationship("Employee", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    initials = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False)
    password_hash = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)

    department = relationship("Department", back_populates="users")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    staff_id = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    status = Column(Enum(EmployeeStatus), default=EmployeeStatus.active, nullable=False)
    grade = Column(String, nullable=True)
    basic_pay = Column(Float, nullable=False, default=0.0)
    allowances = Column(Float, nullable=False, default=0.0)
    avg_overtime_hours = Column(Float, nullable=False, default=0.0)
    exited_date = Column(String, nullable=True)

    department = relationship("Department", back_populates="employees")


class Cycle(Base):
    __tablename__ = "cycles"

    id = Column(Integer, primary_key=True)
    label = Column(String, nullable=False)
    cutoff_date = Column(String, nullable=False)
    is_current = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)


class ColumnMapping(Base):
    __tablename__ = "column_mappings"

    id = Column(Integer, primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    source_columns = Column(JSON, nullable=False)
    mapping = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Submission(Base):
    """One row per *version* of a department's payroll file for a cycle.

    Uploading a fresh file never mutates history: it supersedes the previous
    current version (is_current=False) and inserts a new row (version+1).
    Editing the column mapping of the same upload (remap) is not a new file,
    so it updates the current version in place instead.

    At most one row can be is_current=True per (department_id, cycle_id) —
    enforced by a partial unique index, not just application logic, so a
    race between two concurrent uploads can't silently create two "current"
    submissions that both get counted (the root cause of a dashboard/
    submitter count mismatch: aggregation code that summed all submissions
    for a department+cycle instead of just the current one).
    """
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("department_id", "cycle_id", "version", name="uq_submission_dept_cycle_version"),
        Index(
            "uq_submission_one_current_per_dept_cycle",
            "department_id", "cycle_id",
            unique=True,
            sqlite_where=text("is_current"),
            postgresql_where=text("is_current"),
        ),
    )

    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey("cycles.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    submitted_by = Column(String, nullable=True)
    filename = Column(String, nullable=True)
    uploaded_at = Column(DateTime, nullable=True)
    row_count = Column(Integer, default=0)
    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.not_submitted)
    self_fixed_count = Column(Integer, default=0)
    last_activity = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String, nullable=True)
    superseded_at = Column(DateTime, nullable=True)

    cycle = relationship("Cycle")
    department = relationship("Department")
    rows = relationship("SubmissionRow", back_populates="submission", cascade="all, delete-orphan")
    exceptions = relationship("Exception", back_populates="submission", cascade="all, delete-orphan")


class SubmissionRow(Base):
    __tablename__ = "submission_rows"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False, index=True)
    row_index = Column(Integer, nullable=False)
    staff_id = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    overtime_hours = Column(Float, nullable=True)
    basic_pay = Column(Float, nullable=True)
    allowances = Column(Float, nullable=True)
    raw = Column(JSON, nullable=True)

    submission = relationship("Submission", back_populates="rows")


class Exception(Base):
    __tablename__ = "exceptions"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False, index=True)
    row_id = Column(Integer, ForeignKey("submission_rows.id"), nullable=True)
    row_label = Column(String, nullable=True)
    field = Column(String, nullable=True)
    severity = Column(Enum(ExceptionSeverity), nullable=False)
    source = Column(Enum(ExceptionSource), nullable=False)
    issue_text = Column(Text, nullable=False)
    submitted_value = Column(String, nullable=True)
    usual_value = Column(String, nullable=True)
    ai_explanation = Column(Text, nullable=True)
    recommended_action = Column(String, nullable=True)
    status = Column(Enum(ExceptionStatus), default=ExceptionStatus.open, index=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    resolved_at = Column(DateTime, nullable=True)

    submission = relationship("Submission", back_populates="exceptions")


class CorrectionQuery(Base):
    __tablename__ = "correction_queries"

    id = Column(Integer, primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    cycle_id = Column(Integer, ForeignKey("cycles.id"), nullable=False)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=True)
    to_emails = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    status = Column(Enum(QueryStatus), default=QueryStatus.draft)
    created_at = Column(DateTime, default=utcnow)
    sent_at = Column(DateTime, nullable=True)
    exception_ids = Column(JSON, nullable=True)


class QueryAnswer(Base):
    __tablename__ = "query_answers"

    id = Column(Integer, primary_key=True)
    exception_id = Column(Integer, ForeignKey("exceptions.id"), nullable=False)
    query_id = Column(Integer, ForeignKey("correction_queries.id"), nullable=True)
    answer_type = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    answered_at = Column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    actor_email = Column(String, nullable=False)
    actor_name = Column(String, nullable=True)
    action = Column(String, nullable=False)
    entity = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utcnow)
