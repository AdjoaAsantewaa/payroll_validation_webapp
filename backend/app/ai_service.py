"""The only three places AI touches this system:

1. map_columns        — infer a schema mapping from uploaded column headers
2. explain_anomaly     — judge & explain a row that passed rules but looks unusual
3. draft_correction    — write a correction-request email from a list of exceptions

AI never computes payroll figures and never decides what gets paid — all
arithmetic happens in rules_engine.py before these functions are ever called.
Every function falls back to a deterministic, template-based mock so the app
runs fully without an API key.
"""
import json
import re
from app.config import ANTHROPIC_API_KEY, AI_MODEL

_TOKEN_RE = re.compile(r"[a-z0-9]+")

CANONICAL_FIELDS = ["staff_id", "full_name", "overtime_hours", "basic_pay", "allowances"]

_client = None
if ANTHROPIC_API_KEY:
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception:
        _client = None


def ai_available() -> bool:
    return _client is not None


def _call_claude(system: str, user: str, max_tokens: int = 800) -> str | None:
    if not _client:
        return None
    try:
        resp = _client.messages.create(
            model=AI_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if hasattr(b, "text"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. Schema mapping
# ---------------------------------------------------------------------------

_HEADER_SYNONYMS = {
    "staff_id": ["staff id", "emp no", "employee no", "employee id", "id", "emp id", "staff no", "personnel no"],
    "full_name": ["name", "full name", "employee name", "staff name"],
    "overtime_hours": ["hrs ot", "overtime", "overtime hours", "ot hours", "ot", "hrs overtime"],
    "basic_pay": ["basic", "basic pay", "salary", "base pay", "basic salary"],
    "allowances": ["allow", "allowance", "allowances", "other allowance"],
}


def map_columns(source_columns: list[str], sample_rows: list[dict]) -> dict:
    """Returns {"mapping": {source_col: canonical_field | None}, "confidence": {source_col: float}}"""
    if _client:
        prompt = (
            "You are mapping a payroll spreadsheet's column headers to a canonical schema.\n"
            f"Canonical fields: {CANONICAL_FIELDS}\n"
            f"Source columns: {source_columns}\n"
            f"Sample rows: {json.dumps(sample_rows[:3], default=str)}\n"
            "Return ONLY a JSON object mapping each source column to the best-fit canonical "
            "field name, or null if unsure/unmatched. Example: "
            '{"Emp No.": "staff_id", "Name": "full_name"}'
        )
        raw = _call_claude(
            "You map spreadsheet columns to a canonical payroll schema. Respond with strict JSON only.",
            prompt,
        )
        if raw:
            try:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                mapping = json.loads(match.group(0)) if match else {}
                if mapping:
                    return {"mapping": mapping, "source": "ai"}
            except Exception:
                pass

    # Mock fallback: fuzzy match against known synonyms, order-independent
    # (e.g. "OT Hrs" and "Hrs OT" must both match overtime_hours).
    mapping = {}
    for col in source_columns:
        tokens = set(_TOKEN_RE.findall(col.lower()))
        matched = None
        for field, synonyms in _HEADER_SYNONYMS.items():
            for syn in synonyms:
                syn_tokens = set(_TOKEN_RE.findall(syn))
                if tokens == syn_tokens or (syn_tokens and syn_tokens.issubset(tokens)):
                    matched = field
                    break
            if matched:
                break
        mapping[col] = matched
    return {"mapping": mapping, "source": "mock"}


# ---------------------------------------------------------------------------
# 2. Anomaly explanation
# ---------------------------------------------------------------------------

def explain_anomaly(candidate: dict, row: dict, employee, department_name: str) -> dict:
    """candidate comes from rules_engine.detect_* — code has already decided this is
    worth judgement. AI assigns severity + writes the explanation + recommendation."""
    if _client:
        prompt = (
            f"A payroll row passed structural validation but looks statistically unusual.\n"
            f"Department: {department_name}\n"
            f"Employee: {row.get('full_name')} (staff {row.get('staff_id')})\n"
            f"Signal: {json.dumps(candidate, default=str)}\n"
            f"Employee's recent average overtime: {getattr(employee, 'avg_overtime_hours', None)}\n"
            "Judge how serious this is (severity: high, med, or low) and write a short, "
            "plain-English explanation (1-2 sentences) a payroll specialist can act on, plus a short "
            "recommended action. Do not calculate or state any payment amount as fact — only compare "
            "submitted vs usual. Return ONLY JSON: "
            '{"severity": "high|med|low", "explanation": "...", "recommended_action": "..."}'
        )
        raw = _call_claude(
            "You are a payroll anomaly reviewer. You judge and explain; you never compute or authorize payments. Respond with strict JSON only.",
            prompt,
        )
        if raw:
            try:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                data = json.loads(match.group(0)) if match else None
                if data and "explanation" in data:
                    data.setdefault("severity", "med")
                    data["source"] = "ai"
                    return data
            except Exception:
                pass

    return _mock_explain_anomaly(candidate, row, employee, department_name)


def explain_anomalies_batch(items: list[dict], department_name: str) -> list[dict]:
    """Same judgement as explain_anomaly, but for every candidate row in a
    submission in ONE round-trip instead of one Claude call per row.

    A submission with several dozen anomalous rows previously made that many
    sequential blocking API calls during /submissions/upload -- easily the
    single biggest source of a slow-feeling upload once a real
    ANTHROPIC_API_KEY is configured (the mock fallback is local and fast
    either way, so this only matters for live AI).

    `items`: [{"candidate": ..., "full_name": ..., "staff_id": ...,
                "avg_overtime_hours": ...}, ...]
    Returns a list of judgements in the same order and length as `items`,
    always -- even a partially-malformed AI response is backfilled with the
    mock so the caller never has to special-case a short list.
    """
    if not items:
        return []

    if _client:
        prompt = (
            f"Department: {department_name}\n"
            f"{len(items)} payroll rows passed structural validation but look statistically "
            f"unusual. Judge each independently.\n"
            f"Rows: {json.dumps(items, default=str)}\n"
            "For each row (in the same order), judge severity (high, med, or low) and write a "
            "short plain-English explanation (1-2 sentences) plus a short recommended action. "
            "Do not calculate or state any payment amount as fact — only compare submitted vs "
            "usual. Return ONLY a JSON array, one object per row, same order and length as the "
            "input: [{\"severity\": \"high|med|low\", \"explanation\": \"...\", "
            "\"recommended_action\": \"...\"}, ...]"
        )
        raw = _call_claude(
            "You are a payroll anomaly reviewer. You judge and explain; you never compute or "
            "authorize payments. Respond with a strict JSON array only.",
            prompt,
            max_tokens=400 * len(items) + 200,
        )
        if raw:
            try:
                match = re.search(r"\[.*\]", raw, re.DOTALL)
                data = json.loads(match.group(0)) if match else None
                if isinstance(data, list) and len(data) == len(items):
                    results = []
                    for item, judged in zip(items, data):
                        if isinstance(judged, dict) and "explanation" in judged:
                            judged.setdefault("severity", "med")
                            judged["source"] = "ai"
                            results.append(judged)
                        else:
                            results.append(_mock_explain_anomaly(
                                item["candidate"], item, item.get("employee"), department_name))
                    return results
            except Exception:
                pass

    return [
        _mock_explain_anomaly(item["candidate"], item, item.get("employee"), department_name)
        for item in items
    ]


def _mock_explain_anomaly(candidate: dict, row: dict, employee, department_name: str) -> dict:
    ctype = candidate.get("type")
    if ctype == "overtime_anomaly":
        ratio = candidate["ratio"]
        submitted = candidate["submitted_value"]
        usual = candidate["usual_value"]
        severity = "high" if ratio >= 3 else "med"
        explanation = (
            f"Overtime of {submitted:g}h is within the permitted ceiling, so no rule fired — "
            f"but it is about {ratio:g} times this employee's own average and the highest in "
            f"{department_name} this cycle. Likely a monthly total entered where weekly hours "
            f"were expected."
        )
        return {
            "severity": severity,
            "explanation": explanation,
            "recommended_action": "Query the department before approval.",
            "source": "mock",
        }
    if ctype == "new_allowance":
        return {
            "severity": "med",
            "explanation": (
                f"An allowance of {candidate['submitted_value']:g} has been submitted for "
                f"{row.get('full_name')}, but no allowance has previously been paid at this grade."
            ),
            "recommended_action": "Confirm the allowance is authorised before approval.",
            "source": "mock",
        }
    if ctype == "wage_bill_variance":
        direction = "up" if candidate["variance_pct"] >= 0 else "down"
        return {
            "severity": "med",
            "explanation": (
                f"{department_name}'s submitted wage bill is {direction} {abs(candidate['variance_pct']):g}% "
                f"versus its usual total, with no matching change in headcount ({candidate['headcount']} staff)."
            ),
            "recommended_action": "Ask the department to confirm the cause of the variance.",
            "source": "mock",
        }
    return {
        "severity": "low",
        "explanation": "This value falls outside the department's typical pattern.",
        "recommended_action": "Review before approval.",
        "source": "mock",
    }


# ---------------------------------------------------------------------------
# 3. Correction drafting
# ---------------------------------------------------------------------------

def draft_correction(department_name: str, cycle_label: str, exceptions: list[dict],
                      cutoff_date: str = "") -> dict:
    if _client:
        prompt = (
            f"Draft a short, professional correction-request email to the {department_name} "
            f"department about their {cycle_label} payroll submission.\n"
            f"Exceptions to raise: {json.dumps(exceptions, default=str)}\n"
            "List each item numbered, referencing row numbers and a one-line description asking "
            "them to confirm or correct it. Keep it concise and polite. Return ONLY JSON: "
            '{"subject": "...", "body": "..."}'
        )
        raw = _call_claude(
            "You draft correction-request emails for a payroll team. A human reviews and edits before sending. Respond with strict JSON only.",
            prompt,
        )
        if raw:
            try:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                data = json.loads(match.group(0)) if match else None
                if data and "body" in data:
                    return data
            except Exception:
                pass

    return _mock_draft_correction(department_name, cycle_label, exceptions, cutoff_date)


def _mock_draft_correction(department_name: str, cycle_label: str, exceptions: list[dict],
                            cutoff_date: str) -> dict:
    lines = []
    for i, exc in enumerate(exceptions, start=1):
        lines.append(f"{i}. {exc.get('row_label', 'Row')} — {exc.get('issue_text', '')}. "
                      f"Please confirm or correct.")
    body = (
        f"Hello,\n\n"
        f"Before the {cycle_label} cycle is approved, {len(exceptions)} item"
        f"{'s' if len(exceptions) != 1 else ''} in the {department_name} submission need"
        f"{'s' if len(exceptions) == 1 else ''} confirmation:\n\n"
        + "\n".join(lines) +
        (f"\n\nReplies by {cutoff_date} keep you in this cycle.\n\n" if cutoff_date else "\n\n")
        + "— Payroll"
    )
    subject = f"{cycle_label} payroll — {len(exceptions)} item{'s' if len(exceptions) != 1 else ''} to confirm before approval"
    return {"subject": subject, "body": body, "source": "mock"}
