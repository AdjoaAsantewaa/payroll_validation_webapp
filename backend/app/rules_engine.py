"""Deterministic validation rules. No AI, no judgement calls — pure code.

Anything that can be decided objectively (missing data, out-of-range values,
unknown/exited staff IDs, duplicates) is handled here. Rows that pass every
rule but still look statistically unusual are handed off as "candidates" for
the AI service to judge and explain (see ai_service.py) — the arithmetic
behind that judgement (ratios, variances) is still computed here in code.
"""
from typing import Optional

MAX_OVERTIME_HOURS = 100.0
MIN_OVERTIME_HOURS = 0.0
OVERTIME_ANOMALY_RATIO = 3.0  # candidate for AI review when >= 3x own average
ALLOWANCE_NEW_THRESHOLD = 0.01
WAGE_BILL_VARIANCE_THRESHOLD = 0.15  # 15%


def validate_rows(rows: list[dict], employees_by_staff_id: dict[str, "Employee"]) -> list[dict]:
    """Run deterministic checks against parsed rows.

    `rows` are canonical dicts: {row_index, staff_id, full_name, overtime_hours, basic_pay, allowances, raw}
    Returns a list of exception dicts (source='rule').
    """
    exceptions: list[dict] = []
    seen_staff_ids: dict[str, list[int]] = {}

    for row in rows:
        row_index = row["row_index"]
        staff_id = (row.get("staff_id") or "").strip()
        full_name = row.get("full_name")
        overtime_hours = row.get("overtime_hours")
        row_label = f"Row {row_index}"

        # Missing required fields
        if not staff_id:
            exceptions.append(_exc(row, row_label, "staff_id", "high",
                                    "Staff ID missing (required)"))
        if not full_name:
            exceptions.append(_exc(row, row_label, "full_name", "high",
                                    "Employee name missing (required)"))
        if overtime_hours is None:
            exceptions.append(_exc(row, row_label, "overtime_hours", "high",
                                    "Overtime hours missing (required)"))

        # Range checks
        if overtime_hours is not None:
            if overtime_hours > MAX_OVERTIME_HOURS:
                exceptions.append(_exc(
                    row, row_label, "overtime_hours", "high",
                    f"Overtime {overtime_hours:g}h exceeds the permitted ceiling of {MAX_OVERTIME_HOURS:g}h",
                    submitted_value=str(overtime_hours), usual_value=f"<= {MAX_OVERTIME_HOURS:g}"))
            elif overtime_hours < MIN_OVERTIME_HOURS:
                exceptions.append(_exc(
                    row, row_label, "overtime_hours", "high",
                    "Overtime hours cannot be negative",
                    submitted_value=str(overtime_hours)))

        if not staff_id:
            continue

        # Staff ID existence / exited check
        employee = employees_by_staff_id.get(staff_id)
        if employee is None:
            exceptions.append(_exc(
                row, row_label, "staff_id", "high",
                f"Staff ID {staff_id} is not on the employee record",
                submitted_value=staff_id))
        elif employee.status.value == "exited":
            exceptions.append(_exc(
                row, row_label, "staff_id", "high",
                f"Exited employee — Staff ID {staff_id} belongs to an exited employee",
                submitted_value=staff_id,
                usual_value=f"exited {employee.exited_date or ''}".strip()))

        seen_staff_ids.setdefault(staff_id, []).append(row_index)

    # Duplicate entries within this submission — one exception per duplicate group,
    # anchored on the first occurrence.
    for staff_id, indices in seen_staff_ids.items():
        if len(indices) > 1:
            labels = ", ".join(str(i) for i in indices)
            anchor_row = next(r for r in rows if r["row_index"] == indices[0])
            exceptions.append(_exc(
                anchor_row, f"Rows {labels}", "duplicate", "high",
                f"Same entry appears twice — duplicate of row(s) {labels}",
                submitted_value=staff_id))

    return exceptions


def find_cross_department_duplicates(staff_id: str, department_name: str,
                                      other_rows: list[tuple[str, int]]) -> Optional[str]:
    """other_rows: list of (department_name, row_index) where staff_id already appears
    in another department's submission this cycle."""
    others = [d for d, _ in other_rows if d != department_name]
    if others:
        return f"Staff ID {staff_id} already submitted this cycle under {others[0]}"
    return None


def detect_overtime_candidate(row: dict, employee) -> Optional[dict]:
    """Code-computed feature detection: is this overtime value worth AI judgement?
    Only called on rows that already passed the rule checks above."""
    overtime_hours = row.get("overtime_hours")
    if overtime_hours is None or employee is None:
        return None
    avg = employee.avg_overtime_hours or 0.0
    if avg <= 0:
        return None
    ratio = overtime_hours / avg
    if ratio >= OVERTIME_ANOMALY_RATIO:
        return {
            "type": "overtime_anomaly",
            "ratio": round(ratio, 2),
            "submitted_value": overtime_hours,
            "usual_value": avg,
        }
    return None


def detect_allowance_candidate(row: dict, employee) -> Optional[dict]:
    allowances = row.get("allowances")
    if allowances is None or employee is None:
        return None
    usual = employee.allowances or 0.0
    if abs(allowances - usual) > max(ALLOWANCE_NEW_THRESHOLD, usual * 0.05) and usual == 0 and allowances > 0:
        return {
            "type": "new_allowance",
            "submitted_value": allowances,
            "usual_value": usual,
        }
    return None


def detect_wage_bill_variance(department_name: str, submitted_total: float,
                               usual_total: float, submitted_headcount: int,
                               usual_headcount: int) -> Optional[dict]:
    if usual_total <= 0:
        return None
    variance = (submitted_total - usual_total) / usual_total
    headcount_changed = submitted_headcount != usual_headcount
    if abs(variance) >= WAGE_BILL_VARIANCE_THRESHOLD and not headcount_changed:
        return {
            "type": "wage_bill_variance",
            "variance_pct": round(variance * 100, 1),
            "submitted_total": round(submitted_total, 2),
            "usual_total": round(usual_total, 2),
            "headcount": submitted_headcount,
        }
    return None


def _exc(row: dict, row_label: str, field: str, severity: str, issue_text: str,
         submitted_value: str = None, usual_value: str = None) -> dict:
    return {
        "row_index": row["row_index"],
        "row_label": row_label,
        "field": field,
        "severity": severity,
        "source": "rule",
        "issue_text": issue_text,
        "submitted_value": submitted_value,
        "usual_value": usual_value,
        "ai_explanation": None,
        "recommended_action": None,
    }
