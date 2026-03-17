"""
Data loading, caching, and analytics extraction layer.
Replaces Streamlit's st.cache_data with a simple TTL dict cache.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from sheets_connector import load_sheet_data
from config_helpers import get_event_config, load_event_dashboard_config
from utils import (
    extract_sheet_id,
    safe_json_loads,
    merge_json_dicts,
    normalize_chart_label,
    parse_daily_registrations,
    daily_registrations_to_line_data,
    aggregate_numeric_columns,
    COL_DAILY_REG,
    COL_GENDER,
    COL_COUNTRY,
    COL_STATE,
    COL_CITY,
    COL_OCCUPATION,
    COL_CITY_STAT,
    NUMERIC_KPI_COLUMNS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL cache
# ---------------------------------------------------------------------------
_cache: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL = 300  # 5 minutes


def cached_load_sheet(sheet_id: str, credentials_path: str) -> Optional[pd.DataFrame]:
    key = f"{sheet_id}::{credentials_path}"
    now = time.time()
    if key in _cache:
        ts, df = _cache[key]
        if now - ts < CACHE_TTL:
            return df
    try:
        df = load_sheet_data(sheet_id, credentials_path)
    except RuntimeError as e:
        logger.error("Sheet load failed: %s", e)
        return None
    _cache[key] = (now, df)
    return df


def clear_cache():
    _cache.clear()


# ---------------------------------------------------------------------------
# Event list
# ---------------------------------------------------------------------------
def get_event_list(df: Optional[pd.DataFrame]) -> List[str]:
    if df is None or df.empty or "Initiative Name" not in df.columns:
        return []
    return sorted(df["Initiative Name"].dropna().unique().tolist())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _find_column(df: pd.DataFrame, *keywords: str) -> Optional[str]:
    if df is None or df.columns is None:
        return None
    lower_kw = [k.lower() for k in keywords]
    for c in df.columns:
        if all(k in str(c).strip().lower() for k in lower_kw):
            return c
    return None


def _parse_distribution(df: pd.DataFrame, col: str, top_n: int = 12) -> List[Dict]:
    """Parse a JSON distribution column into sorted [{label, value}] list."""
    if col not in df.columns:
        return []
    dicts = [safe_json_loads(v) for v in df[col]]
    merged = merge_json_dicts(dicts)
    if not merged:
        return []
    items = sorted(merged.items(), key=lambda x: -x[1])[:top_n]
    return [{"label": normalize_chart_label(k), "value": v} for k, v in items]


# ---------------------------------------------------------------------------
# Full analytics payload for one event
# ---------------------------------------------------------------------------
def get_event_analytics(df: pd.DataFrame, event_name: str) -> Dict[str, Any]:
    """
    Return a dict with all analytics data for the given event, ready for
    JSON serialisation and client-side Plotly rendering.
    """
    filtered = df[df["Initiative Name"] == event_name].copy()
    config = get_event_config(load_event_dashboard_config(), event_name)
    reg_target = config.get("registration_target") or 0

    # KPIs
    kpis = aggregate_numeric_columns(filtered, NUMERIC_KPI_COLUMNS)
    reg_count = kpis.get("Registration Count", 0)

    # Daily registrations
    daily = _build_daily_registrations(filtered, event_name, reg_target)

    # Demographics
    gender = _parse_distribution(filtered, COL_GENDER)
    occupation = _parse_distribution(filtered, COL_OCCUPATION)

    # Geography
    country = _parse_distribution(filtered, COL_COUNTRY, top_n=12)
    state = _parse_distribution(filtered, COL_STATE, top_n=12)
    city = _parse_distribution(filtered, COL_CITY, top_n=15)

    # City Stat
    city_stat = _parse_distribution(filtered, COL_CITY_STAT, top_n=15)

    return {
        "event_name": event_name,
        "config": config,
        "kpis": {
            "registrations": reg_count,
            "submissions": kpis.get("Submission Count", 0),
            "teams": kpis.get("Teams Count", 0),
            "page_visits": kpis.get("Page Visits", 0),
        },
        "reg_target": reg_target,
        "daily": daily,
        "gender": gender,
        "occupation": occupation,
        "country": country,
        "state": state,
        "city": city,
        "city_stat": city_stat,
    }


def _build_daily_registrations(filtered: pd.DataFrame, event_name: str, reg_target: int) -> Dict[str, Any]:
    """Build daily registration chart data with average lines."""
    if COL_DAILY_REG not in filtered.columns:
        return {"dates": [], "counts": [], "cumulative": [], "bar_colors": []}

    combined = parse_daily_registrations(filtered[COL_DAILY_REG])
    dates, counts = daily_registrations_to_line_data(combined)
    if not dates:
        return {"dates": [], "counts": [], "cumulative": [], "bar_colors": []}

    # Cumulative
    cumulative = []
    running = 0
    for c in counts:
        running += c
        cumulative.append(running)

    # Average daily calculation
    average_daily = None
    days_from_sheet = None
    span_days = None
    end_dt = None

    REG_START_COL, REG_END_COL = "Registration Start Date", "Registration End Date"
    has_start = REG_START_COL in filtered.columns
    has_end = REG_END_COL in filtered.columns

    start_col = REG_START_COL if has_start else _find_column(filtered, "registration", "start")
    end_col = REG_END_COL if has_end else _find_column(filtered, "registration", "end")
    if not start_col:
        start_col = "Created At" if "Created At" in filtered.columns else None
    if start_col and start_col not in filtered.columns:
        start_col = None
    if end_col and end_col not in filtered.columns:
        end_col = None

    if reg_target and end_col and start_col:
        row = filtered.iloc[0]
        sv, ev = row.get(start_col), row.get(end_col)
        if pd.notna(sv) and pd.notna(ev):
            sdt = pd.to_datetime(sv, errors="coerce", dayfirst=True)
            edt = pd.to_datetime(ev, errors="coerce", dayfirst=True)
            if hasattr(sdt, "normalize"):
                sdt = sdt.normalize()
            if hasattr(edt, "normalize"):
                edt = edt.normalize()
            end_dt = edt
            if pd.notna(sdt) and pd.notna(edt):
                days_from_sheet = max(1, (edt - sdt).days + 1)
                if days_from_sheet > 1:
                    average_daily = reg_target / days_from_sheet

    if reg_target and dates:
        try:
            mn = pd.to_datetime(min(dates), errors="coerce")
            mx = pd.to_datetime(max(dates), errors="coerce")
            if pd.notna(mn) and pd.notna(mx):
                span_days = max(1, (mx - mn).days + 1)
                if average_daily is None or (days_from_sheet and days_from_sheet <= 1):
                    average_daily = reg_target / span_days
        except Exception:
            pass

    # Required daily average
    req_avg = None
    req_avg_label = None
    if reg_target and dates and counts and end_dt is not None:
        ets = end_dt.normalize() if hasattr(end_dt, "normalize") else end_dt
        mask = []
        for d in dates:
            dt = pd.to_datetime(d, errors="coerce")
            if pd.notna(dt) and hasattr(dt, "normalize"):
                dt = dt.normalize()
            mask.append(pd.notna(dt) and dt <= ets)
        if any(mask):
            tsf = sum(c for c, m in zip(counts, mask) if m)
            dr_dates = [d for d, m in zip(dates, mask) if m]
            ld = pd.to_datetime(max(dr_dates), errors="coerce")
            if pd.notna(ld) and hasattr(ld, "normalize"):
                ld = ld.normalize()
            dr = (ets - ld).days
            if dr > 0:
                req_avg = max(0, reg_target - tsf) / dr
                req_avg_label = f"Req: {round(req_avg):,}"
            elif average_daily is not None:
                req_avg = average_daily
                req_avg_label = f"Period avg: {round(req_avg):,}"

    # Bar colors
    if average_daily:
        bar_colors = ["#10b981" if c >= average_daily else "#ef4444" for c in counts]
    else:
        bar_colors = ["#818cf8"] * len(counts)

    return {
        "dates": dates,
        "counts": counts,
        "cumulative": cumulative,
        "bar_colors": bar_colors,
        "average_daily": round(average_daily) if average_daily else None,
        "req_avg": round(req_avg) if req_avg else None,
        "req_avg_label": req_avg_label,
        "reg_target": reg_target,
    }
