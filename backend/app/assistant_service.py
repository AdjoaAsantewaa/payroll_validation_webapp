"""Payroll Assistant: a read-only, retrieval-augmented guidance layer.

Two kinds of context feed every answer, and they are deliberately kept
separate:

1. Structured application context (build_context) -- who is asking, their
   role and department, the submission/exceptions/employee record relevant
   to what they're looking at. This always comes straight from the
   database, scoped by the AUTHENTICATED user's own role and department
   (never from a client-supplied claim) -- that's the role-isolation
   boundary. It is never put in the knowledge base or the retrieval index.

2. Retrieved policy guidance (rag.retrieve) -- ranked chunks of the
   markdown knowledge base in backend/knowledge/, ranked against the
   user's question. Organisational policy text, not employee data.

The assistant is read-only by construction, not just by instruction: it has
no tool/function-calling wired to any endpoint that writes to the database,
so there is no mechanism by which a chat message can approve, reject,
modify a value, send a query, resubmit a file, or create a user -- the
system prompt says so too, but the real guarantee is that the capability
simply doesn't exist here.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.config import ANTHROPIC_API_KEY, AI_MODEL
from app.models import (
    User, Role, Submission, SubmissionRow, Exception as ExceptionModel,
    ExceptionStatus, Employee, CorrectionQuery, Cycle,
)
from app.issue_presentation import present_issue
from app import rag

_client = None
if ANTHROPIC_API_KEY:
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception:
        _client = None


def assistant_available() -> bool:
    return _client is not None


GUARDRAILS = (
    "You are the Payroll Assistant inside a payroll validation application. "
    "You explain and recommend -- you never take action yourself. You "
    "cannot and must never claim to modify payroll values, change employee "
    "records, approve a submission, reject a submission, send a correction "
    "query, resubmit a file, or create a user; those are human actions "
    "taken elsewhere in the application. If asked to do any of these, say "
    "plainly that you can't and point to where they can do it themselves.\n\n"
    "Distinguish clearly between wrong data (the submitter should correct "
    "the source file and resubmit) and a potentially legitimate anomaly "
    "(the right move is to explain it for review, not necessarily change "
    "it).\n\n"
    "Ground your answer in the application context and policy excerpts "
    "given to you below. If they don't contain enough to answer "
    "confidently, say plainly that you don't have enough information, "
    "rather than inventing payroll policy.\n\n"
    "Never say that you are an AI or a language model, never name the "
    "underlying model, and never mention retrieval, embeddings, sources, "
    "confidence scores, or any other internal technical term for how you "
    "work. Speak plainly, like a knowledgeable colleague.\n\n"
    "When the person asks about 'my issues', 'this submission', 'what is "
    "wrong', 'what do I need to fix', 'the problem', which rows need "
    "attention, or why something was flagged -- and the application "
    "context below lists a current submission or issues -- you MUST "
    "answer from that actual list first: real row, staff ID, issue type "
    "and recommended action. Use the policy guidance only to explain or "
    "supplement those real issues, never to replace them or answer with "
    "an unrelated policy topic. If the listed issues are empty, say "
    "plainly that the current submission has no unresolved issues -- "
    "never invent an issue out of policy text.\n\n"
    "A Payroll Specialist asking the same kind of vague question with no "
    "specific submission open (e.g. from the Dashboard) must be answered "
    "from the 'Unresolved issues across all departments' summary in the "
    "context below -- a live per-department breakdown by issue type, not a "
    "policy passage. If that summary shows zero total, say plainly: "
    "'There are no unresolved issues requiring your attention.'"
)

ROLE_FRAMING = {
    "submitter": (
        "The person you're helping is a Department Submitter. When relevant, "
        "prioritise: what is wrong, how to correct it, whether they need to "
        "resubmit, whether an explanation is more appropriate than a "
        "correction, and what the Payroll Specialist is asking them to "
        "confirm."
    ),
    "specialist": (
        "The person you're helping is a Payroll Specialist. When relevant, "
        "prioritise: summarising submission issues, explaining anomalies, "
        "identifying what the department should verify, helping them "
        "understand a submitter's response, and suggesting clarification "
        "questions. You do not make the approval decision yourself -- that "
        "is always theirs, in the Exceptions screen."
    ),
    "admin": (
        "The person you're helping manages user accounts, not payroll data "
        "directly. Keep guidance to policy and process questions; if they "
        "ask about a specific submission, explain that submission detail "
        "is reviewed by the Payroll Specialist."
    ),
}

SUGGESTED_PROMPTS = {
    "submitter": [
        "What do I need to fix?",
        "Explain my current issues",
        "Why is this employee flagged?",
        "How do I resubmit?",
        "What does the Payroll Specialist need from me?",
    ],
    "specialist": [
        "Summarise these issues",
        "What should I ask the department to confirm?",
        "Which issues require correction?",
        "Help me understand this submission",
    ],
    "admin": [
        "How do submitters resubmit a corrected file?",
        "What counts as a valid payroll submission?",
    ],
}


# ---------------------------------------------------------------------------
# Structured application context -- always from the database, always scoped
# to the authenticated user's own role/department.
# ---------------------------------------------------------------------------

def _current_cycle(db: Session) -> Cycle | None:
    return db.query(Cycle).filter(Cycle.is_current == True).first()  # noqa: E712


def _current_submission_for_dept(db: Session, department_id: int, cycle_id: int) -> Submission | None:
    return db.query(Submission).filter(
        Submission.department_id == department_id, Submission.cycle_id == cycle_id,
        Submission.is_current == True,  # noqa: E712
    ).first()


def _dashboard_summary_for_specialist(db: Session, cycle_id: int | None) -> dict:
    """Cross-department live workload for a Specialist who isn't looking at
    any one submission (e.g. the global Dashboard) -- same data, same
    department visibility the rest of the app already gives a Specialist,
    just grouped for a one-glance answer instead of forcing them to open
    each department. Only ever called for Role.specialist (see
    build_context), so this never runs for a Submitter."""
    q = db.query(Submission).filter(Submission.is_current == True)  # noqa: E712
    if cycle_id:
        q = q.filter(Submission.cycle_id == cycle_id)
    submissions = q.all()

    departments = []
    total_open = 0
    for sub in submissions:
        exceptions = db.query(ExceptionModel).filter(
            ExceptionModel.submission_id == sub.id,
            ExceptionModel.status.in_([ExceptionStatus.open, ExceptionStatus.query_open]),
        ).all()
        if not exceptions:
            continue
        row_ids = [e.row_id for e in exceptions if e.row_id]
        rows_by_id = {}
        if row_ids:
            rows_by_id = {
                r.id: r for r in db.query(SubmissionRow).filter(SubmissionRow.id.in_(row_ids)).all()
            }
        by_type: dict[str, int] = {}
        for e in exceptions:
            row = rows_by_id.get(e.row_id)
            presentation = present_issue(
                field=e.field, source=e.source.value, issue_text=e.issue_text,
                submitted_value=e.submitted_value, usual_value=e.usual_value,
                ai_explanation=e.ai_explanation, existing_recommended_action=e.recommended_action,
                staff_id=row.staff_id if row else None, full_name=row.full_name if row else None,
            )
            by_type[presentation["issue_type"]] = by_type.get(presentation["issue_type"], 0) + 1
        departments.append({
            "department": sub.department.name if sub.department else "Unknown department",
            "submission_id": sub.id,
            "open_count": len(exceptions),
            "by_type": by_type,
        })
        total_open += len(exceptions)

    departments.sort(key=lambda d: -d["open_count"])
    return {"total_open": total_open, "departments": departments}


def _exception_summary(e: ExceptionModel, row: SubmissionRow | None) -> dict:
    presentation = present_issue(
        field=e.field, source=e.source.value, issue_text=e.issue_text,
        submitted_value=e.submitted_value, usual_value=e.usual_value,
        ai_explanation=e.ai_explanation, existing_recommended_action=e.recommended_action,
        staff_id=row.staff_id if row else None, full_name=row.full_name if row else None,
    )
    return {
        "row_label": e.row_label,
        "issue_type": presentation["issue_type"],
        "problem": presentation["problem"],
        "recommended_action": presentation["recommended_action"],
        "status": e.status.value,
        "staff_id": row.staff_id if row else None,
        "full_name": row.full_name if row else None,
        "submitted_value": e.submitted_value,
        "usual_value": e.usual_value,
    }


def build_context(db: Session, user: User, page: str = "",
                   submission_id: int | None = None, exception_id: int | None = None) -> dict:
    """Builds the structured context block for one assistant request. The
    only inputs trusted for authorization are fields on `user` (the
    authenticated User row) -- `submission_id`/`exception_id` are hints from
    the frontend about what the user is currently looking at, and are only
    honoured after confirming they actually belong to that user's own
    department (submitters) or are visible at all (specialists, who --
    exactly like the rest of this application -- can see any department).
    """
    ctx: dict = {"role": user.role.value, "name": user.name, "page": page}
    cycle = _current_cycle(db)
    if cycle:
        ctx["cycle"] = cycle.label

    submission: Submission | None = None

    if user.role == Role.submitter:
        ctx["department"] = user.department.name if user.department else None
        if cycle and user.department_id:
            submission = _current_submission_for_dept(db, user.department_id, cycle.id)
        if submission_id:
            candidate = db.query(Submission).filter(Submission.id == submission_id).first()
            if candidate and candidate.department_id == user.department_id:
                submission = candidate
            # else: silently ignored -- a submitter's context never follows
            # a submission_id outside their own department, regardless of
            # what the page claims.

    elif user.role == Role.specialist:
        if submission_id:
            submission = db.query(Submission).filter(Submission.id == submission_id).first()
        # Specialists can reference any department's submission, matching
        # their existing permissions everywhere else in the application.

    if submission:
        ctx["department"] = submission.department.name
        ctx["submission"] = {
            "status": submission.status.value,
            "row_count": submission.row_count,
            "version": submission.version,
            "last_activity": submission.last_activity,
        }
        exceptions = db.query(ExceptionModel).filter(
            ExceptionModel.submission_id == submission.id
        ).order_by(ExceptionModel.id).limit(25).all()
        row_ids = [e.row_id for e in exceptions if e.row_id]
        rows_by_id = {}
        if row_ids:
            rows_by_id = {
                r.id: r for r in db.query(SubmissionRow).filter(SubmissionRow.id.in_(row_ids)).all()
            }
        ctx["exceptions"] = [_exception_summary(e, rows_by_id.get(e.row_id)) for e in exceptions]
        ctx["open_issue_count"] = sum(
            1 for e in exceptions if e.status in (ExceptionStatus.open, ExceptionStatus.query_open)
        )
    elif user.role == Role.specialist:
        # A Specialist with no specific submission in view (the global
        # Dashboard) has no single "current submission" to fall back to --
        # unlike a Submitter, who always has their own department's. Give a
        # cross-department summary instead so a vague question here still
        # answers from live data rather than falling through to RAG.
        ctx["dashboard_summary"] = _dashboard_summary_for_specialist(db, cycle.id if cycle else None)

    if exception_id:
        exc = db.query(ExceptionModel).filter(ExceptionModel.id == exception_id).first()
        if exc:
            owning_submission = db.query(Submission).filter(Submission.id == exc.submission_id).first()
            allowed = user.role == Role.specialist or (
                user.role == Role.submitter and owning_submission is not None
                and owning_submission.department_id == user.department_id
            )
            if allowed:
                row = db.query(SubmissionRow).filter(SubmissionRow.id == exc.row_id).first() if exc.row_id else None
                ctx["focused_exception"] = _exception_summary(exc, row)
                ctx["focused_exception"]["row_label"] = exc.row_label

                if row and row.staff_id:
                    employee = db.query(Employee).filter(Employee.staff_id == row.staff_id).first()
                    # An employee record is only attached to context if it
                    # belongs to the requesting submitter's own department,
                    # or the requester is a specialist. Same boundary as
                    # everywhere else the application shows "usual" values.
                    if employee and (
                        user.role == Role.specialist or employee.department_id == user.department_id
                    ):
                        ctx["employee"] = {
                            "staff_id": employee.staff_id,
                            "full_name": employee.full_name,
                            "department": employee.department.name if employee.department else None,
                            "status": employee.status.value,
                            "exited_date": employee.exited_date,
                            "avg_overtime_hours": employee.avg_overtime_hours,
                        }
                        ctx["current_payroll_row"] = {
                            "overtime_hours": row.overtime_hours,
                            "basic_pay": row.basic_pay,
                            "allowances": row.allowances,
                        }

                queries = db.query(CorrectionQuery).filter(
                    CorrectionQuery.submission_id == exc.submission_id
                ).order_by(CorrectionQuery.id.desc()).limit(1).all()
                if queries:
                    ctx["latest_correction_query"] = {
                        "subject": queries[0].subject, "status": queries[0].status.value,
                    }

    return ctx


def format_context_block(ctx: dict) -> str:
    lines = [f"Role: {ctx['role']}"]
    if ctx.get("department"):
        lines.append(f"Department: {ctx['department']}")
    if ctx.get("cycle"):
        lines.append(f"Cycle: {ctx['cycle']}")

    if "submission" in ctx:
        s = ctx["submission"]
        lines.append(
            f"Current submission: {s['row_count']} rows, status {s['status']}, "
            f"version {s['version']}, last activity: {s['last_activity']}"
        )
        lines.append(f"Open issues on this submission: {ctx.get('open_issue_count', 0)}")

    if ctx.get("exceptions"):
        lines.append("Issues on this submission:")
        for e in ctx["exceptions"]:
            who = ", ".join(filter(None, [e.get("staff_id"), e.get("full_name")]))
            who_part = f", {who}" if who else ""
            lines.append(
                f"  - [{e['status']}] {e['row_label']}{who_part}: {e['issue_type']} -- {e['problem']}"
            )
            if e.get("submitted_value") not in (None, ""):
                usual_part = f", usual={e['usual_value']}" if e.get("usual_value") not in (None, "") else ""
                lines.append(f"    submitted={e['submitted_value']}{usual_part}")
            lines.append(f"    Recommended action: {e['recommended_action']}")

    if "dashboard_summary" in ctx:
        ds = ctx["dashboard_summary"]
        lines.append(
            f"Unresolved issues across all departments you can see: {ds['total_open']} total, "
            f"across {len(ds['departments'])} department(s) with open issues."
        )
        for d in ds["departments"]:
            lines.append(f"  - {d['department']}: {d['open_count']} issues (submission_id={d['submission_id']})")
            for itype, count in d["by_type"].items():
                lines.append(f"      {count} {itype}")

    if "employee" in ctx:
        emp = ctx["employee"]
        lines.append("")
        lines.append(emp["staff_id"])
        lines.append(emp["full_name"])
        lines.append(f"Department: {emp['department']}")
        lines.append(f"Employee status: {emp['status']}")
        if emp.get("exited_date"):
            lines.append(f"Exited date: {emp['exited_date']}")
        lines.append(f"Employee's average overtime: {emp['avg_overtime_hours']:g}h")
        if "current_payroll_row" in ctx:
            row = ctx["current_payroll_row"]
            lines.append(
                f"Current payroll row: overtime_hours={row['overtime_hours']}, "
                f"basic_pay={row['basic_pay']}, allowances={row['allowances']}"
            )

    if "focused_exception" in ctx:
        fe = ctx["focused_exception"]
        lines.append(f"Current exception: {fe['issue_type']} -- {fe['problem']}")

    if "latest_correction_query" in ctx:
        q = ctx["latest_correction_query"]
        lines.append(f"Latest correction query to this department: \"{q['subject']}\" ({q['status']})")

    return "\n".join(lines)


def format_knowledge_block(chunks: list[dict]) -> str:
    if not chunks:
        return "(no closely matching policy guidance found)"
    parts = []
    for c in chunks:
        parts.append(f"### {c['doc_title']} -- {c['heading']}\n{c['text']}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------

def _call_claude(system: str, user_prompt: str) -> str | None:
    if not _client:
        return None
    try:
        resp = _client.messages.create(
            model=AI_MODEL, max_tokens=600, system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(b.text for b in resp.content if hasattr(b, "text"))
    except Exception:
        return None


def answer(db: Session, user: User, message: str, page: str = "",
           submission_id: int | None = None, exception_id: int | None = None) -> dict:
    """Returns {"reply": str}. `retrieved` (which chunks fed the answer) is
    intentionally not part of this return value -- it's for tests/debugging
    via rag.retrieve() directly, never surfaced to the chat UI."""
    ctx = build_context(db, user, page, submission_id, exception_id)
    retrieved = rag.retrieve(message, k=4)

    if _client:
        system = GUARDRAILS + "\n\n" + ROLE_FRAMING.get(user.role.value, "")
        prompt = (
            f"Application context:\n{format_context_block(ctx)}\n\n"
            f"Relevant policy guidance:\n{format_knowledge_block(retrieved)}\n\n"
            f"Question: {message}"
        )
        raw = _call_claude(system, prompt)
        if raw:
            return {"reply": raw.strip()}

    return {"reply": _mock_answer(user, message, ctx, retrieved)}


# Phrasings that mean "tell me about my own current submission/issues", as
# opposed to a general policy question -- these must be answered from live
# application context first (see build_context), never from a generic
# retrieved policy passage. Kept as a broad net (exact phrases + a looser
# issue-word + context-word combination) because real users phrase this a
# great many ways ("what is the issue", "what do I fix", "which rows need
# attention", "why was this flagged", ...) and a narrow keyword list is
# exactly what let a "what is the issue?" question fall through to an
# unrelated policy chunk before this fix.
_CONTEXTUAL_ISSUE_PATTERNS = (
    "what is the issue", "what's the issue", "whats the issue",
    "what is wrong", "what's wrong", "whats wrong",
    "what do i need to fix", "what do i fix", "what should i fix",
    "what needs fixing", "what needs to be fixed",
    "explain my issue", "explain my current issue", "explain the issue",
    "which rows need attention", "what rows need attention",
    "why was my submission flagged", "why is my submission flagged",
    "why was this flagged", "why is this flagged", "why was it flagged",
    "current issues", "my issues", "the problem", "problem with my submission",
    "issues with my submission", "which issues", "these issues", "issues require",
    "needs my attention", "need my attention", "requires my attention",
    "what do i need to review", "need to review", "what should i review",
    "things to review", "summar", "help me understand",
)
_ISSUE_WORDS = ("issue", "wrong", "problem", "fix", "flag", "error")
_CONTEXT_WORDS = ("my", "this", "current", "submission", "row")


def _is_contextual_issue_query(msg_lower: str) -> bool:
    if any(p in msg_lower for p in _CONTEXTUAL_ISSUE_PATTERNS):
        return True
    return (
        any(w in msg_lower for w in _ISSUE_WORDS)
        and any(w in msg_lower for w in _CONTEXT_WORDS)
    )


def _format_dashboard_summary(ds: dict) -> str:
    if ds["total_open"] == 0:
        return "There are no unresolved issues requiring your attention."
    n_dept = len(ds["departments"])
    lines = [
        f"You currently have {ds['total_open']} unresolved issue"
        f"{'s' if ds['total_open'] != 1 else ''} across {n_dept} department"
        f"{'s' if n_dept != 1 else ''}:"
    ]
    for d in ds["departments"]:
        lines.append("")
        lines.append(f"{d['department']} — {d['open_count']} issue{'s' if d['open_count'] != 1 else ''}")
        for itype, count in d["by_type"].items():
            lines.append(f"  • {count} {itype}")
    lines.append("")
    lines.append("Open a department to review the individual exceptions.")
    return "\n".join(lines)


def _format_issue_line(e: dict) -> str:
    who_bits = [b for b in (e.get("staff_id"), e.get("full_name")) if b]
    who = f" ({', '.join(who_bits)})" if who_bits else ""
    line = f"- {e['row_label']}{who}: {e['issue_type']} -- {e['problem']}"
    if e.get("submitted_value") not in (None, ""):
        line += f" [submitted: {e['submitted_value']}"
        if e.get("usual_value") not in (None, ""):
            line += f", usual: {e['usual_value']}"
        line += "]"
    line += f" Recommended action: {e['recommended_action']}"
    return line


def _mock_answer(user: User, message: str, ctx: dict, retrieved: list[dict]) -> str:
    """Deterministic, template-based fallback so the assistant works with no
    ANTHROPIC_API_KEY -- same convention as ai_service.py's mock fallbacks.
    Still genuinely grounded: it uses the actual retrieved knowledge chunk
    and the actual structured context, not a hardcoded canned reply."""
    msg_lower = message.lower()

    # Refuse action requests explicitly and immediately -- this must never
    # fall through to a general-topic answer that merely sounds adjacent to
    # complying. The real guarantee is that this endpoint has no write path
    # at all (see the module docstring); this check just makes sure the
    # reply says so plainly instead of dodging the question.
    action_phrases = (
        "approve this", "approve my", "approve it", "reject this", "reject my",
        "modify this value", "change this value", "change the value", "edit this row",
        "edit the row", "send the query", "send this query", "resubmit this for me",
        "create a user", "create an account", "delete this", "for me right now",
    )
    if any(p in msg_lower for p in action_phrases) or (
        "approve" in msg_lower and any(w in msg_lower for w in ("please", "can you", "will you", "for me"))
    ):
        who = "the Payroll Specialist" if user.role != Role.specialist else "you, in the Exceptions screen"
        return (
            "I can't do that -- I can only explain and recommend, not take action. Approving, "
            "rejecting, modifying a value, sending a query, resubmitting a file, or creating a "
            f"user all have to be done directly in the application by {who}."
        )

    # A specific exception is in focus -- answer about that first, since
    # it's almost always what "why is this flagged" / "explain this" means.
    if "focused_exception" in ctx:
        fe = ctx["focused_exception"]
        lead = f"{fe['issue_type']}: {fe['problem']}"
        action = f"\n\nWhat to do: {fe.get('problem') and _action_for(ctx)}"
        return (lead + action).strip()

    if _is_contextual_issue_query(msg_lower):
        exceptions = ctx.get("exceptions") or []
        open_ones = [e for e in exceptions if e["status"] in ("open", "query_open")]
        if open_ones:
            by_type: dict[str, int] = {}
            for e in open_ones:
                by_type[e["issue_type"]] = by_type.get(e["issue_type"], 0) + 1
            summary = ", ".join(f"{count} {itype}" for itype, count in by_type.items())
            lines = [f"There {'are' if len(open_ones) != 1 else 'is'} {len(open_ones)} open issue"
                     f"{'s' if len(open_ones) != 1 else ''} on your current submission: {summary}."]
            for e in open_ones[:6]:
                lines.append(_format_issue_line(e))
            if len(open_ones) > 6:
                lines.append(f"...and {len(open_ones) - 6} more.")
            return "\n".join(lines)
        if "submission" in ctx:
            return "Your current submission has no unresolved issues."
        if "dashboard_summary" in ctx:
            return _format_dashboard_summary(ctx["dashboard_summary"])
        return "I don't see a current submission to check yet. Upload a file first, or open a specific submission."

    if any(k in msg_lower for k in ("resubmit", "how do i correct", "how do i fix")):
        chunk = next((c for c in retrieved if "resubmission" in c["doc_id"] or "faq" in c["doc_id"]), None)
        if chunk:
            return chunk["text"]

    if any(k in msg_lower for k in ("what should i ask", "what does the specialist need",
                                     "confirm", "verify")):
        exceptions = ctx.get("exceptions") or []
        if exceptions:
            lines = ["Worth confirming with the department:"]
            for e in exceptions[:5]:
                lines.append(f"- {e['row_label']} ({e['issue_type']}): {e['problem']}")
            return "\n".join(lines)

    # General question: ground the answer in the best-matching policy chunk.
    if retrieved:
        top = retrieved[0]
        return f"{top['text']}"

    return (
        "I don't have enough information to answer that confidently. Try asking about a "
        "specific issue on your current submission, or rephrase your question."
    )


def _action_for(ctx: dict) -> str:
    fe = ctx["focused_exception"]
    # Reuse the same recommended_action text present_issue would generate --
    # cheap to recompute here since we only have the summary, not the model.
    itype = fe["issue_type"]
    if itype == "Unknown employee":
        return ("Check the Staff ID against your department records. If this is a new "
                "employee, they must first be added to the employee master data. If the ID "
                "was entered incorrectly, correct the spreadsheet and resubmit.")
    if itype == "Exited employee":
        return ("Remove this employee from the current payroll file, or provide an "
                "explanation if payment is genuinely still due.")
    if itype == "Unusual overtime":
        return ("If this figure is correct, provide an explanation for the Payroll "
                "Specialist. Otherwise correct the value and resubmit.")
    if itype == "Duplicate entry":
        return "Keep only the correct entry for this employee and resubmit."
    if itype == "Missing information":
        return "Fill in the missing value in the source file and resubmit."
    if itype == "Invalid value":
        return "Correct the value in the source file and resubmit."
    return "Review this item and resubmit if needed."
