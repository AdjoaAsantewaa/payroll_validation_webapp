"""User-facing presentation of a validation Exception.

The backend keeps recording, per exception, whether it came from
deterministic validation (`source="rule"`) or contextual judgement
(`source="ai"`) -- that's unchanged, and still visible in the API response
and audit trail for debugging. What changes here is the layer users
actually see: instead of a raw "Rule"/"AI" label, every exception is
classified into a plain-language issue type with a Problem statement and a
Recommended action, derived deterministically from fields the application
already fully controls (`field`, `source`, `issue_text`) -- never from user
input, so this is exact classification, not guessing.

No schema change: issue_type/problem/recommended_action are computed at
read time in _exc_to_dict(), not persisted. The existing `field`/`source`/
`issue_text` columns remain the source of truth; this module is a pure
presentation layer over them.
"""
from __future__ import annotations


def present_issue(
    *,
    field: str | None,
    source: str,
    issue_text: str,
    submitted_value: str | None,
    usual_value: str | None,
    ai_explanation: str | None,
    existing_recommended_action: str | None,
    staff_id: str | None = None,
    full_name: str | None = None,
) -> dict:
    """Returns {"issue_type": str, "problem": str, "recommended_action": str}."""
    text_lower = (issue_text or "").lower()
    who = full_name or (f"Staff ID {staff_id}" if staff_id else "This employee")
    id_prefix = f"{staff_id} " if staff_id else ""

    if field == "staff_id" and source == "rule" and "not on the employee record" in text_lower:
        return {
            "issue_type": "Unknown employee",
            "problem": (
                f"{id_prefix}does not match any employee on record for this department."
            ).strip(),
            "recommended_action": (
                "Check the Staff ID against your department records. If this is a new "
                "employee, they must first be added to the employee master data. If the "
                "ID was entered incorrectly, correct the spreadsheet and resubmit."
            ),
        }

    if field == "staff_id" and source == "rule" and "exited" in text_lower:
        return {
            "issue_type": "Exited employee",
            "problem": (
                f"{id_prefix}belongs to {who if full_name else 'an employee'}, whose employee "
                f"record shows that they have exited the organisation."
            ),
            "recommended_action": (
                "Remove this employee from the current payroll file, or provide an "
                "explanation if payment is genuinely still due."
            ),
        }

    if field == "duplicate":
        return {
            "issue_type": "Duplicate entry",
            "problem": issue_text,
            "recommended_action": "Keep only the correct entry for this employee and resubmit.",
        }

    if "missing (required)" in text_lower:
        return {
            "issue_type": "Missing information",
            "problem": issue_text,
            "recommended_action": "Fill in the missing value in the source file and resubmit.",
        }

    if field == "overtime_hours" and source == "rule":
        return {
            "issue_type": "Invalid value",
            "problem": issue_text,
            "recommended_action": "Correct the value in the source file and resubmit.",
        }

    if field == "overtime_hours" and source == "ai":
        return {
            "issue_type": "Unusual overtime",
            "problem": ai_explanation or issue_text,
            "recommended_action": existing_recommended_action or (
                "If this figure is correct, provide an explanation for the Payroll "
                "Specialist. Otherwise correct the value and resubmit."
            ),
        }

    if field == "allowances" and source == "ai":
        return {
            "issue_type": "Unusual allowance",
            "problem": ai_explanation or issue_text,
            "recommended_action": existing_recommended_action or (
                "If this allowance is correct, provide an explanation for the Payroll "
                "Specialist. Otherwise correct the value and resubmit."
            ),
        }

    if field == "wage_bill":
        return {
            "issue_type": "Unusual wage bill",
            "problem": ai_explanation or issue_text,
            "recommended_action": existing_recommended_action or (
                "Confirm the cause of the variance with the department before approval."
            ),
        }

    # Fallback: keeps returning something sensible even if a future rule
    # doesn't have a matching branch above yet, rather than showing nothing.
    return {
        "issue_type": "Data quality issue",
        "problem": ai_explanation or issue_text,
        "recommended_action": existing_recommended_action or "Review this item and resubmit if needed.",
    }


# Presentation for the two upload-time gates, which aren't stored as
# Exception rows at all (see submissions.py's blocked-upload response) --
# kept here so the same terminology ("Column mapping issue" / "File
# structure issue") is defined in exactly one place.
BLOCK_REASON_ISSUE_TYPE = {
    "mapping_conflict": "Column mapping issue",
    "not_payroll_shaped": "File structure issue",
}
