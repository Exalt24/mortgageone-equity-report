"""Convert a local loan export workbook into a sample CSV for testing.

For purchases: Property Value = Total Loan Amount + Down Payment Amount
For refinances: Property Value is unknown from loan data alone (down payment = $0).
    We flag these so the equity report handles them gracefully.

Usage:
    python convert_sample.py
    # Creates loan_export_sample.csv ready for --csv or Google Sheets upload
"""

import csv
import logging
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("Install openpyxl first: pip install openpyxl")
    raise SystemExit(1)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

INPUT_FILE = Path(__file__).parent.parent / "Sample79.xlsx"
OUTPUT_FILE = Path(__file__).parent / "loan_export_sample.csv"


def convert():
    wb = openpyxl.load_workbook(INPUT_FILE, read_only=True)
    ws = wb.active

    rows_written = 0
    refis_flagged = 0

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Property Value", "Mortgage Balance"])

        for row in ws.iter_rows(min_row=2, values_only=True):
            name = row[0]
            loan_type = row[1]
            loan_amount = row[4] or 0
            down_payment = row[5] or 0
            purpose = row[7] or ""

            if not name or not loan_amount:
                continue

            # Flip "Last, First" to "First Last"
            if "," in str(name):
                parts = str(name).split(",", 1)
                name = f"{parts[1].strip()} {parts[0].strip()}"

            # For purchases: property value = loan + down payment
            # For refis: down payment is 0, so property value = loan amount
            # This understates equity for refis, but it's the best we can do
            # without an external home value source (Zillow, ATTOM, etc.)
            property_value = loan_amount + down_payment

            writer.writerow([name, int(property_value), int(loan_amount)])
            rows_written += 1

            if "Refi" in purpose:
                refis_flagged += 1

    logger.info("Converted %d borrowers to %s", rows_written, OUTPUT_FILE)
    if refis_flagged:
        logger.info(
            "Note: %d refinance borrowers have estimated property values "
            "(loan amount only, no down payment data). For accurate equity "
            "on refis, integrate a home value API like ATTOM or Zillow.",
            refis_flagged,
        )


if __name__ == "__main__":
    convert()
