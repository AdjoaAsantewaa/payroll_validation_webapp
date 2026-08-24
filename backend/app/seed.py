"""Seeds realistic demo data matching the Payroll Validation design mockups:
August 2026 cycle, 12 departments, K. Owusu (specialist), assorted submitters,
and the specific exception rows shown in the wireframes (N. Adjei overtime,
staff 40188 exited, duplicate rows 91/402, etc).
"""
import datetime
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app.models import (
    Department, User, Role, Employee, EmployeeStatus, Cycle,
    Submission, SubmissionStatus, SubmissionRow, Exception as ExceptionModel,
    ExceptionSeverity, ExceptionSource, ExceptionStatus, CorrectionQuery, QueryStatus,
    AuditLog,
)
from app.security import hash_password

DEMO_PASSWORD = "password123"


def seed(db: Session):
    if db.query(Department).first():
        return  # already seeded

    dept_names = [
        "Nursing", "Facilities", "Transport", "Catering", "Estates", "Security",
        "Library", "Housekeeping", "Maintenance", "IT Support", "Administration", "Grounds",
    ]
    depts = {}
    for name in dept_names:
        d = Department(name=name, contact_email=f"{name.lower().replace(' ', '')}.payroll@company.com")
        db.add(d)
        depts[name] = d
    db.flush()

    specialist = User(
        email="k.owusu@company.com", name="K. Owusu", initials="KO",
        role=Role.specialist, password_hash=hash_password(DEMO_PASSWORD),
    )
    db.add(specialist)

    submitters = [
        ("a.mensah@company.com", "A. Mensah", "AM", "Facilities"),
        ("j.tetteh@company.com", "J. Tetteh", "JT", "Nursing"),
        ("k.asare@company.com", "K. Asare", "KA", "Transport"),
        ("d.owusu@company.com", "D. Owusu", "DO", "Catering"),
        ("e.appiah@company.com", "E. Appiah", "EA", "Estates"),
        ("f.boateng@company.com", "F. Boateng", "FB", "Security"),
        ("g.nkrumah@company.com", "G. Nkrumah", "GN", "Library"),
        ("h.addo@company.com", "H. Addo", "HA", "Housekeeping"),
        ("i.darko@company.com", "I. Darko", "ID", "Maintenance"),
        ("l.frimpong@company.com", "L. Frimpong", "LF", "IT Support"),
        ("m.sarpong@company.com", "M. Sarpong", "MS", "Administration"),
        ("n.osei@company.com", "N. Osei", "NO", "Grounds"),
    ]
    for email, name, initials, dept in submitters:
        db.add(User(email=email, name=name, initials=initials, role=Role.submitter,
                     password_hash=hash_password(DEMO_PASSWORD), department_id=depts[dept].id))

    cycle = Cycle(label="August 2026", cutoff_date="2026-08-24", is_current=True)
    db.add(cycle)
    db.flush()

    # --- Employee master records ---------------------------------------
    employees = [
        # Nursing
        dict(staff_id="20714", full_name="N. Adjei", department_id=depts["Nursing"].id,
             status=EmployeeStatus.active, grade="N4", basic_pay=3200.0, allowances=180.0,
             avg_overtime_hours=24.3),
        dict(staff_id="40188", full_name="P. Kwarteng", department_id=depts["Nursing"].id,
             status=EmployeeStatus.exited, grade="N2", basic_pay=2600.0, allowances=120.0,
             avg_overtime_hours=12.0, exited_date="2026-06-30"),
        dict(staff_id="20330", full_name="L. Boateng", department_id=depts["Nursing"].id,
             status=EmployeeStatus.active, grade="N3", basic_pay=2900.0, allowances=0.0,
             avg_overtime_hours=18.0),
        dict(staff_id="20091", full_name="R. Amoah", department_id=depts["Nursing"].id,
             status=EmployeeStatus.active, grade="N2", basic_pay=2750.0, allowances=100.0,
             avg_overtime_hours=16.0),
        dict(staff_id="20088", full_name="C. Yeboah", department_id=depts["Nursing"].id,
             status=EmployeeStatus.active, grade="N3", basic_pay=2850.0, allowances=110.0,
             avg_overtime_hours=20.0),
        dict(staff_id="20500", full_name="B. Ansong", department_id=depts["Nursing"].id,
             status=EmployeeStatus.active, grade="N2", basic_pay=2700.0, allowances=95.0,
             avg_overtime_hours=15.0),
        # Facilities
        dict(staff_id="F2004", full_name="S. Owusu-Ansah", department_id=depts["Facilities"].id,
             status=EmployeeStatus.active, grade="F3", basic_pay=2400.0, allowances=140.0,
             avg_overtime_hours=24.0),
        dict(staff_id="F2041", full_name="T. Agyeman", department_id=depts["Facilities"].id,
             status=EmployeeStatus.active, grade="F2", basic_pay=2200.0, allowances=100.0,
             avg_overtime_hours=14.0),
        dict(staff_id="F2058", full_name="V. Asante", department_id=depts["Facilities"].id,
             status=EmployeeStatus.active, grade="F2", basic_pay=2250.0, allowances=100.0,
             avg_overtime_hours=13.0),
        # Transport
        dict(staff_id="T3005", full_name="W. Danso", department_id=depts["Transport"].id,
             status=EmployeeStatus.active, grade="T2", basic_pay=2100.0, allowances=90.0,
             avg_overtime_hours=18.0),
        dict(staff_id="T3040", full_name="Y. Gyasi", department_id=depts["Transport"].id,
             status=EmployeeStatus.active, grade="T2", basic_pay=2150.0, allowances=90.0,
             avg_overtime_hours=17.0),
        dict(staff_id="T3066", full_name="Z. Opoku", department_id=depts["Transport"].id,
             status=EmployeeStatus.active, grade="T2", basic_pay=2100.0, allowances=90.0,
             avg_overtime_hours=16.0),
    ]
    emp_objs = {}
    for e in employees:
        obj = Employee(**e)
        db.add(obj)
        emp_objs[e["staff_id"]] = obj
    db.flush()

    # --- Submissions ------------------------------------------------------
    def make_submission(dept, status, row_count, self_fixed, last_activity,
                         submitted_by=None, uploaded_at=None, approved_at=None,
                         approved_by=None, filename=None):
        s = Submission(
            cycle_id=cycle.id, department_id=depts[dept].id, status=status,
            row_count=row_count, self_fixed_count=self_fixed, last_activity=last_activity,
            submitted_by=submitted_by, uploaded_at=uploaded_at, approved_at=approved_at,
            approved_by=approved_by, filename=filename,
        )
        db.add(s)
        db.flush()
        return s

    now = datetime.datetime.utcnow()

    sub_nursing = make_submission(
        "Nursing", SubmissionStatus.needs_review, 604, 20, "Submitted yesterday",
        submitted_by="J. Tetteh", uploaded_at=now - datetime.timedelta(days=1),
        filename="nursing_aug.xlsx")
    sub_facilities = make_submission(
        "Facilities", SubmissionStatus.needs_review, 142, 6, "Resubmitted 09:41",
        submitted_by="A. Mensah", uploaded_at=now, filename="facilities_aug.xlsx")
    sub_transport = make_submission(
        "Transport", SubmissionStatus.query_sent, 88, 5, "Query sent 14 Aug",
        submitted_by="K. Asare", uploaded_at=now - datetime.timedelta(days=10),
        filename="transport_aug.csv")
    sub_catering = make_submission(
        "Catering", SubmissionStatus.approved, 96, 3, "Approved 13 Aug",
        submitted_by="D. Owusu", uploaded_at=now - datetime.timedelta(days=11),
        approved_at=now - datetime.timedelta(days=11), approved_by="K. Owusu",
        filename="catering_aug.xlsx")
    sub_estates = make_submission(
        "Estates", SubmissionStatus.approved, 51, 2, "Approved 13 Aug",
        submitted_by="E. Appiah", uploaded_at=now - datetime.timedelta(days=11),
        approved_at=now - datetime.timedelta(days=11), approved_by="K. Owusu",
        filename="estates_aug.xlsx")
    sub_library = make_submission(
        "Library", SubmissionStatus.approved, 34, 2, "Approved 12 Aug",
        submitted_by="G. Nkrumah", uploaded_at=now - datetime.timedelta(days=12),
        approved_at=now - datetime.timedelta(days=12), approved_by="K. Owusu",
        filename="library_aug.xlsx")
    make_submission("Housekeeping", SubmissionStatus.needs_review, 60, 1, "Submitted 11 Aug",
                     submitted_by="H. Addo", uploaded_at=now - datetime.timedelta(days=13),
                     filename="housekeeping_aug.xlsx")
    make_submission("Maintenance", SubmissionStatus.needs_review, 45, 1, "Submitted 11 Aug",
                     submitted_by="I. Darko", uploaded_at=now - datetime.timedelta(days=13),
                     filename="maintenance_aug.xlsx")
    make_submission("IT Support", SubmissionStatus.needs_review, 28, 1, "Submitted 10 Aug",
                     submitted_by="L. Frimpong", uploaded_at=now - datetime.timedelta(days=14),
                     filename="itsupport_aug.xlsx")
    make_submission("Security", SubmissionStatus.not_submitted, 0, 0, "Reminder sent 15 Aug")
    make_submission("Administration", SubmissionStatus.not_submitted, 0, 0, "Reminder sent 15 Aug")
    make_submission("Grounds", SubmissionStatus.not_submitted, 0, 0, "Reminder sent 15 Aug")

    db.flush()

    # --- Nursing exceptions (9 total: 5 high, 3 med, 1 low) ---------------
    def add_row(sub, idx, staff_id=None, full_name=None, overtime=None, basic=None, allow=None):
        r = SubmissionRow(submission_id=sub.id, row_index=idx, staff_id=staff_id,
                           full_name=full_name, overtime_hours=overtime, basic_pay=basic,
                           allowances=allow, raw={})
        db.add(r)
        db.flush()
        return r

    def add_exc(sub, row, row_label, field, severity, source, issue_text,
                submitted_value=None, usual_value=None, ai_explanation=None,
                recommended_action=None, status=ExceptionStatus.open):
        e = ExceptionModel(
            submission_id=sub.id, row_id=row.id if row else None, row_label=row_label,
            field=field, severity=severity, source=source, issue_text=issue_text,
            submitted_value=submitted_value, usual_value=usual_value,
            ai_explanation=ai_explanation, recommended_action=recommended_action,
            status=status,
        )
        db.add(e)
        return e

    r214 = add_row(sub_nursing, 214, "20714", "N. Adjei", 96.0, 3200.0, 180.0)
    add_exc(sub_nursing, r214, "Row 214 · N. Adjei · staff 20714", "overtime_hours",
            ExceptionSeverity.high, ExceptionSource.ai,
            "Overtime entry — 96h vs own average 24h",
            submitted_value="96.0", usual_value="24.3 avg (6 periods)",
            ai_explanation=("Overtime of 96h is within the permitted ceiling, so no rule fired — "
                             "but it is about four times this employee's own average and the "
                             "highest in Nursing this cycle. Likely a monthly total entered where "
                             "weekly hours were expected."),
            recommended_action="Query the department before approval.")

    r77 = add_row(sub_nursing, 77, "40188", "P. Kwarteng")
    add_exc(sub_nursing, r77, "Row 77 · staff 40188", "staff_id",
            ExceptionSeverity.high, ExceptionSource.rule,
            "Exited employee — Staff ID belongs to an exited employee",
            usual_value="exited 2026-06-30")

    r91 = add_row(sub_nursing, 91, "20091", "R. Amoah", 18.0, 2750.0, 100.0)
    r402 = add_row(sub_nursing, 402, "20091", "R. Amoah", 18.0, 2750.0, 100.0)
    add_exc(sub_nursing, r91, "Rows 91, 402", "duplicate",
            ExceptionSeverity.high, ExceptionSource.rule,
            "Same entry appears twice across submissions")

    r145 = add_row(sub_nursing, 145, "20500", "B. Ansong", None, 2700.0, 95.0)
    add_exc(sub_nursing, r145, "Row 145 · B. Ansong", "overtime_hours",
            ExceptionSeverity.high, ExceptionSource.rule,
            "Overtime hours missing (required)")

    r260 = add_row(sub_nursing, 260, "29999", "Unknown")
    add_exc(sub_nursing, r260, "Row 260 · staff 29999", "staff_id",
            ExceptionSeverity.high, ExceptionSource.rule,
            "Staff ID 29999 is not on the employee record")

    add_exc(sub_nursing, None, "Department total", "wage_bill",
            ExceptionSeverity.med, ExceptionSource.ai,
            "Wage bill variance — +18% with no headcount change",
            submitted_value="+18%", usual_value="0% (no headcount change)",
            ai_explanation=("Nursing's submitted wage bill is up 18% versus its usual total, "
                             "with no matching change in headcount. Worth confirming before "
                             "approval."),
            recommended_action="Ask the department to confirm the cause of the variance.")

    r330 = add_row(sub_nursing, 330, "20330", "L. Boateng", 18.0, 2900.0, 60.0)
    add_exc(sub_nursing, r330, "Row 330 · L. Boateng", "allowances",
            ExceptionSeverity.med, ExceptionSource.ai,
            "New allowance — Not previously paid at this grade",
            submitted_value="60.00", usual_value="0.00",
            ai_explanation=("An allowance of 60.00 has been submitted for L. Boateng, but no "
                             "allowance has previously been paid at this grade."),
            recommended_action="Confirm the allowance is authorised before approval.")

    r88row = add_row(sub_nursing, 88, "20088", "C. Yeboah", 45.0, 2850.0, 110.0)
    add_exc(sub_nursing, r88row, "Row 88 · C. Yeboah", "overtime_hours",
            ExceptionSeverity.med, ExceptionSource.ai,
            "Overtime 45h vs own average 20h — within tolerance but worth a note",
            submitted_value="45.0", usual_value="20.0 avg (6 periods)",
            ai_explanation=("Overtime of 45h is a little over twice this employee's usual "
                             "average, but not extreme enough to block on its own."),
            recommended_action="No action required; monitor next cycle.")

    r500 = add_row(sub_nursing, 500, "20500", "B. Ansong", 15.0, 2700.0, 95.5)
    add_exc(sub_nursing, r500, "Row 500 · B. Ansong", "allowances",
            ExceptionSeverity.low, ExceptionSource.rule,
            "Allowances differ from usual by a small rounding amount",
            submitted_value="95.50", usual_value="95.00")

    # --- Facilities exceptions (4 total: 2 high) ---------------------------
    r12 = add_row(sub_facilities, 12, "F9999", "Unknown")
    add_exc(sub_facilities, r12, "Row 12", "staff_id",
            ExceptionSeverity.high, ExceptionSource.rule,
            "Staff ID F9999 is not on the employee record")

    r31 = add_row(sub_facilities, 31, "F2041", "T. Agyeman", None, 2200.0, 100.0)
    add_exc(sub_facilities, r31, "Row 31", "overtime_hours",
            ExceptionSeverity.high, ExceptionSource.rule,
            "Overtime hours missing (required)")

    r58 = add_row(sub_facilities, 58, "F2004", "S. Owusu-Ansah", 96.0, 2400.0, 140.0)
    add_exc(sub_facilities, r58, "Row 58", "overtime_hours",
            ExceptionSeverity.med, ExceptionSource.ai,
            "Overtime 96h — about 4x this employee's own average",
            submitted_value="96.0", usual_value="24.0 avg (6 periods)",
            ai_explanation=("Overtime of 96h is about four times S. Owusu-Ansah's own average "
                             "and the highest in Facilities this cycle. Likely a monthly total "
                             "entered where weekly hours were expected."),
            recommended_action="Query the department before approval.")

    r41 = add_row(sub_facilities, 41, "F2058", "V. Asante", 13.0, 2250.0, 100.0)
    r77f = add_row(sub_facilities, 77, "F2058", "V. Asante", 13.0, 2250.0, 100.0)
    add_exc(sub_facilities, r77f, "Row 77", "duplicate",
            ExceptionSeverity.low, ExceptionSource.rule,
            "Duplicate of row 41")

    # --- Transport exceptions (4 total, query already sent) ----------------
    t5 = add_row(sub_transport, 5, "T9999", "Unknown")
    add_exc(sub_transport, t5, "Row 5", "staff_id",
            ExceptionSeverity.high, ExceptionSource.rule,
            "Staff ID T9999 is not on the employee record",
            status=ExceptionStatus.query_open)

    t22 = add_row(sub_transport, 22, "T3040", "Y. Gyasi", None, 2150.0, 90.0)
    add_exc(sub_transport, t22, "Row 22", "overtime_hours",
            ExceptionSeverity.high, ExceptionSource.rule,
            "Overtime hours missing (required)", status=ExceptionStatus.query_open)

    t40 = add_row(sub_transport, 40, "T3005", "W. Danso", 55.0, 2100.0, 90.0)
    add_exc(sub_transport, t40, "Row 40", "overtime_hours",
            ExceptionSeverity.med, ExceptionSource.ai,
            "Overtime 55h vs own average 18h",
            submitted_value="55.0", usual_value="18.0 avg (6 periods)",
            ai_explanation=("Overtime of 55h is roughly three times W. Danso's usual average. "
                             "Worth confirming with Transport."),
            recommended_action="Query the department before approval.",
            status=ExceptionStatus.query_open)

    t66 = add_row(sub_transport, 66, "T3066", "Z. Opoku", 16.0, 2100.0, 90.0)
    t70 = add_row(sub_transport, 70, "T3066", "Z. Opoku", 16.0, 2100.0, 90.0)
    add_exc(sub_transport, t66, "Rows 66, 70", "duplicate",
            ExceptionSeverity.low, ExceptionSource.rule,
            "Same entry appears twice across submissions", status=ExceptionStatus.query_open)

    # --- Materialize clean rows for approved (export-ready) departments ----
    def gen_clean_rows(sub, prefix, count, base_pay, base_allow):
        for i in range(1, count + 1):
            add_row(sub, i, f"{prefix}{1000 + i}", f"{prefix} Staff {i}",
                    round(10 + (i % 8) * 1.5, 1), base_pay + (i % 5) * 25.0,
                    base_allow + (i % 3) * 10.0)

    gen_clean_rows(sub_catering, "CAT", 96, 2050.0, 80.0)
    gen_clean_rows(sub_estates, "EST", 51, 2150.0, 85.0)
    gen_clean_rows(sub_library, "LIB", 34, 2000.0, 70.0)

    db.flush()
    transport_exceptions = db.query(ExceptionModel).filter(
        ExceptionModel.submission_id == sub_transport.id).all()
    q = CorrectionQuery(
        department_id=depts["Transport"].id, cycle_id=cycle.id, submission_id=sub_transport.id,
        to_emails="transport.payroll@company.com",
        subject="August payroll — 4 items to confirm before approval",
        body=(
            "Hello,\n\nBefore the August cycle is approved, 4 items in the Transport "
            "submission need confirmation:\n\n"
            "1. Row 5 — Staff ID T9999 is not on the employee record. Please confirm or correct.\n"
            "2. Row 22 — Overtime hours missing (required). Please confirm or correct.\n"
            "3. Row 40 — Overtime 55h vs own average 18h. Please confirm whether this is correct.\n"
            "4. Rows 66, 70 — Same entry appears twice. Please confirm which is correct.\n\n"
            "Replies by 22 Aug keep you in this cycle.\n\n— K. Owusu, Payroll"
        ),
        status=QueryStatus.sent,
        sent_at=now - datetime.timedelta(days=10),
        exception_ids=[e.id for e in transport_exceptions],
    )
    db.add(q)

    db.add(AuditLog(actor_email="k.owusu@company.com", actor_name="K. Owusu",
                     action="query_sent", entity="department", entity_id=str(depts["Transport"].id),
                     detail="Sent correction request to Transport (4 items)",
                     timestamp=now - datetime.timedelta(days=10)))
    db.add(AuditLog(actor_email="k.owusu@company.com", actor_name="K. Owusu",
                     action="approved", entity="submission", entity_id=str(sub_catering.id),
                     detail="Approved Catering submission (96 rows)",
                     timestamp=now - datetime.timedelta(days=11)))
    db.add(AuditLog(actor_email="k.owusu@company.com", actor_name="K. Owusu",
                     action="approved", entity="submission", entity_id=str(sub_estates.id),
                     detail="Approved Estates submission (51 rows)",
                     timestamp=now - datetime.timedelta(days=11)))
    db.add(AuditLog(actor_email="k.owusu@company.com", actor_name="K. Owusu",
                     action="approved", entity="submission", entity_id=str(sub_library.id),
                     detail="Approved Library submission (34 rows)",
                     timestamp=now - datetime.timedelta(days=12)))

    # --- Historical cycles for the submitter "earlier cycles" view (Facilities) --
    past_cycles = [
        ("July 2026", "2026-07-24", 140, 2, "approved"),
        ("June 2026", "2026-06-24", 139, 0, "approved"),
        ("May 2026", "2026-05-24", 141, 0, "approved_with_query"),
    ]
    for label, cutoff, rows, self_fixed, outcome in past_cycles:
        past_cycle = Cycle(label=label, cutoff_date=cutoff, is_current=False)
        db.add(past_cycle)
        db.flush()
        past_sub = Submission(
            cycle_id=past_cycle.id, department_id=depts["Facilities"].id,
            status=SubmissionStatus.approved, row_count=rows, self_fixed_count=self_fixed,
            submitted_by="A. Mensah", uploaded_at=now - datetime.timedelta(days=30),
            approved_at=now - datetime.timedelta(days=28), approved_by="K. Owusu",
            filename=f"facilities_{label.split()[0].lower()}.xlsx",
            last_activity="Approved",
        )
        db.add(past_sub)
        db.flush()
        if outcome == "approved_with_query":
            db.add(ExceptionModel(
                submission_id=past_sub.id, row_label="Row 58", field="overtime_hours",
                severity=ExceptionSeverity.med, source=ExceptionSource.ai,
                issue_text="Overtime queried and confirmed correct",
                status=ExceptionStatus.query_answered,
            ))

    db.commit()


def init_db_and_seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    init_db_and_seed()
    print("Database initialized and seeded.")
