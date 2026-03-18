"""Google Sheets integration using gspread v6+."""

import logging

import gspread
from google.oauth2.service_account import Credentials
from gspread import BackOffHTTPClient
from gspread_formatting import (
    CellFormat,
    Color,
    TextFormat,
    format_cell_range,
    set_column_width,
)

from src.models import ProcessingResult

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Name",
    "Property Value",
    "Mortgage Balance",
    "Equity",
    "Equity %",
    "LTV %",
    "Borrowing Capacity",
    "PMI Eligible",
    "Position",
    "Personalized Message",
]


def get_sheets_client(credentials_path: str) -> gspread.Client:
    """Create a gspread client with automatic rate limit retry."""
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    client = gspread.Client(auth=creds, http_client=BackOffHTTPClient)
    return client


def read_homeowner_data(
    client: gspread.Client, spreadsheet_id: str, sheet_name: str
) -> list[dict]:
    """Read homeowner data from a Google Sheets worksheet."""
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
    except gspread.exceptions.APIError as e:
        logger.error("Auth/API error opening spreadsheet %s: %s", spreadsheet_id, e)
        return []
    except Exception as e:
        logger.error("Failed to open spreadsheet %s: %s", spreadsheet_id, e)
        return []

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.error("Sheet '%s' not found in spreadsheet %s", sheet_name, spreadsheet_id)
        return []

    try:
        records = worksheet.get_all_records()
    except Exception as e:
        logger.error("Failed to read records from '%s': %s", sheet_name, e)
        return []

    if not records:
        logger.warning("Sheet '%s' is empty, no records found", sheet_name)
        return []

    logger.info("Read %d records from '%s'", len(records), sheet_name)
    return records


def write_results(
    client: gspread.Client,
    spreadsheet_id: str,
    sheet_name: str,
    results: list[ProcessingResult],
) -> None:
    """Write processing results to a worksheet with formatted values."""
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
    except Exception as e:
        logger.error("Failed to open spreadsheet %s: %s", spreadsheet_id, e)
        return

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        logger.info("Found existing worksheet '%s'", sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(results) + 1, cols=len(HEADERS))
        logger.info("Created new worksheet '%s'", sheet_name)

    rows = []
    for r in results:
        rows.append([
            r.homeowner.name,
            f"${r.homeowner.property_value:,.2f}",
            f"${r.homeowner.mortgage_balance:,.2f}",
            f"${r.equity.equity:,.2f}",
            f"{r.equity.equity_percentage:.1f}%",
            f"{r.equity.ltv:.1f}%",
            f"${r.equity.borrowing_capacity:,.2f}",
            "Yes" if r.equity.can_remove_pmi else "No",
            r.equity.position,
            r.message,
        ])

    try:
        worksheet.update("A1", [HEADERS] + rows)
        logger.info("Wrote %d result rows to '%s'", len(rows), sheet_name)
    except Exception as e:
        logger.error("Failed to write results to '%s': %s", sheet_name, e)
        return

    try:
        format_output_sheet(worksheet)
    except Exception as e:
        logger.error("Failed to format worksheet '%s': %s", sheet_name, e)


def format_output_sheet(worksheet) -> None:
    """Apply formatting to the output worksheet."""
    # Bold header row
    header_fmt = CellFormat(
        textFormat=TextFormat(bold=True),
        backgroundColor=Color(0.85, 0.85, 0.85),
    )
    format_cell_range(worksheet, "A1:J1", header_fmt)

    # Set column widths
    col_widths = {
        0: 180,   # Name
        1: 140,   # Property Value
        2: 140,   # Mortgage Balance
        3: 130,   # Equity
        4: 90,    # Equity %
        5: 90,    # LTV %
        6: 150,   # Borrowing Capacity
        7: 100,   # PMI Eligible
        8: 140,   # Position
        9: 500,   # Personalized Message
    }
    for col_idx, width in col_widths.items():
        set_column_width(worksheet, col_idx + 1, width)

    # Color code rows based on Position column (column I)
    try:
        all_values = worksheet.get_all_values()
    except Exception as e:
        logger.error("Failed to read values for formatting: %s", e)
        return

    position_col = HEADERS.index("Position")

    green = Color(0.831, 0.929, 0.855)    # #d4edda
    yellow = Color(1.0, 0.953, 0.804)     # #fff3cd
    red = Color(0.973, 0.843, 0.855)      # #f8d7da

    formats = []
    for row_idx, row in enumerate(all_values[1:], start=2):
        if row_idx > len(all_values):
            break
        position = row[position_col] if position_col < len(row) else ""
        if "Strong" in position:
            bg = green
        elif "Moderate" in position:
            bg = yellow
        else:
            bg = red

        cell_range = f"A{row_idx}:J{row_idx}"
        formats.append((cell_range, CellFormat(backgroundColor=bg)))

    if formats:
        from gspread_formatting import format_cell_ranges
        format_cell_ranges(worksheet, formats)

    logger.info("Applied formatting to %d data rows", len(all_values) - 1)
