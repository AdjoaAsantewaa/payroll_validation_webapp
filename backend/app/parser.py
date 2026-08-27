"""File parsing — pandas/openpyxl. Purely mechanical, no judgement here."""
import io
import pandas as pd

from app.ai_service import CANONICAL_FIELDS

# Fields the rules engine already treats as required on every row (see
# rules_engine.validate_rows). If NONE of the source columns even claim to
# represent one of these, that's a structural signal the file itself isn't
# payroll-shaped -- not just that some rows have missing values.
REQUIRED_PAYROLL_FIELDS = ["staff_id", "full_name", "overtime_hours"]


def read_upload(filename: str, content: bytes) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    elif lower.endswith(".xlsx") or lower.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(content))
    else:
        raise ValueError("Unsupported file type. Please upload a .csv or .xlsx file.")
    df = df.dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def find_mapping_conflicts(mapping: dict[str, str | None]) -> dict[str, list[str]]:
    """Two source columns must never map to the same canonical field --
    apply_mapping would otherwise silently let whichever one is processed
    last overwrite the other with no indication anything was dropped.
    Returns {target_field: [source_col, source_col, ...]} for every
    canonical field claimed by more than one source column; empty dict
    means no conflicts. This is the single source of truth for the
    conflict rule -- both apply_mapping (defensive) and the upload/remap
    routes (blocking) call it, so the rule can't be bypassed by hitting
    the API directly instead of the mapping-edit UI."""
    by_target: dict[str, list[str]] = {}
    for source_col, target_field in mapping.items():
        if not target_field:
            continue
        by_target.setdefault(target_field, []).append(source_col)
    return {field: cols for field, cols in by_target.items() if len(cols) > 1}


def missing_required_fields(mapping: dict[str, str | None]) -> list[str]:
    """Deterministic payroll-shape check, run before any row-level validation:
    which required canonical fields have NO source column mapped to them at
    all. A file that never claims to have an overtime column, for example,
    isn't a payroll file with bad data -- it's structurally not a payroll
    file. Pure schema check, no AI, no per-row logic, and not specific to
    any one known-bad file -- it just checks REQUIRED_PAYROLL_FIELDS against
    whatever the mapping (AI-assisted or hand-edited) actually claims."""
    mapped_targets = {t for t in mapping.values() if t}
    return [f for f in REQUIRED_PAYROLL_FIELDS if f not in mapped_targets]


def apply_mapping(df: pd.DataFrame, mapping: dict[str, str | None]) -> list[dict]:
    """mapping: {source_column: canonical_field_or_None}. Returns canonical row dicts.

    Defensive: if the mapping has a conflict (two source columns targeting
    the same field), that field is left unpopulated here rather than
    silently taking whichever column happens to be processed last. Callers
    are expected to check find_mapping_conflicts() and block *before*
    calling this, but this guarantees the silent-overwrite bug can't happen
    even if that check is ever skipped.
    """
    conflicts = find_mapping_conflicts(mapping)
    safe_mapping = {
        source_col: (None if target_field in conflicts else target_field)
        for source_col, target_field in mapping.items()
    }

    rows = []
    for row_index, (_, series) in enumerate(df.iterrows(), start=1):
        raw = {str(k): (None if pd.isna(v) else _py(v)) for k, v in series.items()}
        canonical = {field: None for field in CANONICAL_FIELDS}
        for source_col, target_field in safe_mapping.items():
            if target_field and source_col in series.index:
                val = series[source_col]
                canonical[target_field] = None if pd.isna(val) else _py(val)

        canonical["staff_id"] = _clean_staff_id(canonical.get("staff_id"))
        canonical["full_name"] = _clean_str(canonical.get("full_name"))
        canonical["overtime_hours"] = _to_float(canonical.get("overtime_hours"))
        canonical["basic_pay"] = _to_float(canonical.get("basic_pay"))
        canonical["allowances"] = _to_float(canonical.get("allowances"))

        rows.append({
            "row_index": row_index,
            "raw": raw,
            **canonical,
        })
    return rows


def _py(v):
    try:
        if hasattr(v, "item"):
            return v.item()
    except Exception:
        pass
    return v


def _clean_staff_id(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
