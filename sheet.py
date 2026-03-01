"""
Google Sheets integration for outreach tracking.

Reads/writes a tracker sheet with columns:
  URL | Agent Name | Agent Email | Agent Phone | Status | Tour Date | Notes

Usage:
    from sheet import get_client, get_tracker, get_new_rows, update_row
"""

import os

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "authorized_user.json")

# Set via env var or hardcode your sheet URL here.
SHEET_URL = os.environ.get("SHEET_URL", "")

# Expected column layout (1-indexed). Data starts at B3 (row 1 & col A are spacing).
HEADER_ROW = 2
DATA_START_ROW = 3
COL_URL = 2
COL_AGENT_NAME = 3
COL_AGENT_EMAIL = 4
COL_AGENT_PHONE = 5
COL_AVAILABLE = 6
COL_STATUS = 7
COL_TOUR_DATE = 8
COL_NOTES = 9


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def get_client() -> gspread.Client:
    """Authenticate via OAuth and return a gspread client.

    On first run, opens a browser for consent. Subsequent runs reuse the
    stored token at TOKEN_PATH.
    """
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save for next run.
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return gspread.authorize(creds)


# ---------------------------------------------------------------------------
# Sheet helpers
# ---------------------------------------------------------------------------


def get_tracker(client: gspread.Client) -> gspread.Worksheet:
    """Open the tracker spreadsheet and return the first worksheet."""
    if not SHEET_URL:
        raise ValueError(
            "SHEET_URL is not set. Export it as an env var or set it in sheet.py."
        )
    spreadsheet = client.open_by_url(SHEET_URL)
    return spreadsheet.sheet1


def get_new_rows(worksheet: gspread.Worksheet) -> list[dict]:
    """Return rows that have a URL but no Agent Name (i.e. need processing).

    Each dict has 'row' (1-indexed row number) and 'url'.
    """
    all_values = worksheet.get_all_values()
    new_rows = []

    # Data starts at DATA_START_ROW (row 3). Skip header + spacing rows.
    for i, row in enumerate(all_values, start=1):
        if i < DATA_START_ROW:
            continue
        url = row[COL_URL - 1].strip() if len(row) >= COL_URL else ""
        agent_name = (
            row[COL_AGENT_NAME - 1].strip() if len(row) >= COL_AGENT_NAME else ""
        )

        if url and not agent_name:
            new_rows.append({"row": i, "url": url})

    return new_rows


def update_row(
    worksheet: gspread.Worksheet,
    row_num: int,
    *,
    agent_name: str = "",
    agent_email: str = "",
    agent_phone: str = "",
    available_date: str = "",
    tour_dates: str = "",
) -> None:
    """Write contact info into the given row."""
    # Prefix with ' so Sheets treats values as plain text (avoids formula parse
    # errors for strings like "+1 (212) ...").
    worksheet.update_cell(row_num, COL_AGENT_NAME, f"'{agent_name}")
    worksheet.update_cell(row_num, COL_AGENT_EMAIL, f"'{agent_email}")
    worksheet.update_cell(row_num, COL_AGENT_PHONE, f"'{agent_phone}")
    if available_date:
        worksheet.update_cell(row_num, COL_AVAILABLE, f"'{available_date}")
    if tour_dates:
        worksheet.update_cell(row_num, COL_TOUR_DATE, f"'{tour_dates}")

    # Set status to "new" if it's empty.
    current_status = worksheet.cell(row_num, COL_STATUS).value or ""
    if not current_status.strip():
        worksheet.update_cell(row_num, COL_STATUS, "new")
