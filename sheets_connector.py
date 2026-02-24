"""
Google Sheets connector for loading hackathon/event data.
Uses gspread with service account authentication.
"""

import logging
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from typing import Optional
import streamlit as st

logger = logging.getLogger(__name__)

# Expected column names
EXPECTED_COLUMNS = [
    "Initiative Name",
    "Initiative URL",
    "Created At",
    "Created By",
    "Registration End Date",
    "Submission Start Date",
    "Submission End Date",
    "Registration Count",
    "Submission Count",
    "Teams Count",
    "Page Visits",
    "Gender Distribution",
    "Daily Registrations",
    "Country",
    "State",
    "City",
    "Occupation",
]


def get_credentials(credentials_path: str = "credentials.json"):
    """Load Google service account credentials from JSON file."""
    logger.info("Loading credentials from %s", credentials_path)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    logger.info("Credentials loaded successfully")
    return creds


def load_sheet_data(sheet_id: str, credentials_path: str = "credentials.json") -> Optional[pd.DataFrame]:
    """
    Connect to Google Sheet by ID and load first worksheet into a DataFrame.
    Returns None on failure.
    """
    logger.info("Loading sheet: sheet_id=%s, credentials_path=%s", sheet_id, credentials_path)
    try:
        creds = get_credentials(credentials_path)
        logger.info("Authorizing gspread client...")
        client = gspread.authorize(creds)
        logger.info("Opening spreadsheet by key...")
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1
        logger.info("Fetching all records from worksheet '%s'...", worksheet.title)
        data = worksheet.get_all_records()
        if not data:
            logger.warning("Sheet is empty (no data rows)")
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df = _normalize_columns(df)
        logger.info("Sheet loaded successfully: %d rows, %d columns", len(df), len(df.columns))
        return df
    except FileNotFoundError as e:
        logger.error("Credentials file not found: %s", credentials_path, exc_info=True)
        st.error(f"Credentials file not found: {credentials_path}")
        return None
    except gspread.exceptions.APIError as e:
        logger.error("Google Sheets API error: %s", e, exc_info=True)
        st.error(f"Google Sheets API error: {e}")
        return None
    except gspread.exceptions.SpreadsheetNotFound as e:
        logger.error("Spreadsheet not found (check Sheet ID and sharing): %s", e, exc_info=True)
        st.error(f"Spreadsheet not found. Check the Sheet ID and ensure the sheet is shared with the service account email.")
        return None
    except Exception as e:
        logger.exception("Failed to load sheet: %s", e)
        st.error(f"Failed to load sheet: {e}")
        return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names: strip whitespace."""
    df.columns = [str(c).strip() for c in df.columns]
    return df
