"""
Utilities for JSON parsing and aggregating event data.
"""

import json
import re
from typing import Any, Dict, List, Optional
import pandas as pd


def extract_sheet_id(value: str) -> str:
    """
    Extract Google Sheet ID from pasted input.
    Accepts either the raw Sheet ID or a full URL like:
    https://docs.google.com/spreadsheets/d/SHEET_ID/edit...
    """
    if not value or not isinstance(value, str):
        return ""
    s = value.strip()
    # Match /d/SHEET_ID/ or /d/SHEET_ID (end or followed by ? or #)
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    # Otherwise treat whole string as ID if it looks like one (no spaces, no ://)
    if s and " " not in s and "://" not in s:
        return s
    return ""


def safe_json_loads(value: Any) -> Optional[Dict[str, Any]]:
    """
    Safely parse a JSON string into a dictionary.
    Returns None for invalid/missing values.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value or value in ("{}", "[]", ""):
            return None
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def merge_json_dicts(dicts: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Merge multiple JSON dictionaries by summing numeric values for each key.
    Used for aggregating Gender, Country, State, Occupation, etc. across events.
    """
    result: Dict[str, Any] = {}
    for d in dicts:
        if not d:
            continue
        for key, val in d.items():
            if key not in result:
                result[key] = 0
            try:
                result[key] += int(val) if isinstance(val, (int, float)) else 0
            except (TypeError, ValueError):
                pass
    return result


def parse_daily_registrations(series: pd.Series) -> Dict[str, int]:
    """
    Parse 'Daily Registrations (JSON)' column(s) from selected rows.
    Combine all date->count mappings and sum counts per date.
    Returns dict: date_str -> total_count
    """
    combined: Dict[str, int] = {}
    for val in series.dropna():
        d = safe_json_loads(val)
        if not d:
            continue
        for date_str, count in d.items():
            try:
                combined[date_str] = combined.get(date_str, 0) + int(count)
            except (TypeError, ValueError):
                pass
    return combined


def daily_registrations_to_line_data(combined: Dict[str, int]) -> tuple[List[str], List[int]]:
    """
    Convert merged daily registrations dict to sorted (dates, counts) for Plotly.
    """
    if not combined:
        return [], []
    sorted_items = sorted(combined.items(), key=lambda x: x[0])
    dates = [item[0] for item in sorted_items]
    counts = [item[1] for item in sorted_items]
    return dates, counts


def normalize_chart_label(key: Any) -> str:
    """
    Return a display label for chart legends. Empty or whitespace keys (e.g. from JSON \"\")
    become \"(Unknown)\" so Plotly does not show them as \"1\" or blank.
    """
    if key is None:
        return "(Unknown)"
    s = str(key).strip()
    return s if s else "(Unknown)"


def aggregate_numeric_columns(df: pd.DataFrame, columns: List[str]) -> Dict[str, int]:
    """Sum numeric columns over the filtered dataframe. Returns column_name -> sum."""
    result = {}
    for col in columns:
        if col not in df.columns:
            result[col] = 0
            continue
        try:
            result[col] = int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
        except (TypeError, ValueError):
            result[col] = 0
    return result


# Column name constants (match sheet headers)
COL_DAILY_REG = "Daily Registrations"
COL_GENDER = "Gender Distribution"
COL_COUNTRY = "Country"
COL_STATE = "State"
COL_CITY = "City"
COL_OCCUPATION = "Occupation"

NUMERIC_KPI_COLUMNS = [
    "Registration Count",
    "Submission Count",
    "Teams Count",
    "Page Visits",
]
