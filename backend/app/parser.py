"""File parsing — pandas/openpyxl. Purely mechanical, no judgement here."""
import io
import pandas as pd

from app.ai_service import CANONICAL_FIELDS


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


def apply_mapping(df: pd.DataFrame, mapping: dict[str, str | None]) -> list[dict]:
    """mapping: {source_column: canonical_field_or_None}. Returns canonical row dicts."""
    rows = []
    for row_index, (_, series) in enumerate(df.iterrows(), start=1):
        raw = {str(k): (None if pd.isna(v) else _py(v)) for k, v in series.items()}
        canonical = {field: None for field in CANONICAL_FIELDS}
        for source_col, target_field in mapping.items():
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
