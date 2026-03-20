"""MortgageOne Home Equity Report Generator - CLI entry point."""

import argparse
import csv
import logging
import sys

from tqdm import tqdm

from src.config import get_settings
from src.equity import calculate_equity, validate_homeowner_data, format_currency, format_percentage
from src.message_generator import (
    generate_message_sync,
    combine_message,
    prepare_batch_file,
    submit_batch,
    poll_batch,
    estimate_cost,
    EquityMessage,
)
from src.models import HomeownerData, EquityResult, ProcessingResult
from src.sheets import get_sheets_client, read_homeowner_data, write_results


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("equity_report.log"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate personalized home equity reports from Google Sheets data."
    )
    parser.add_argument("--sheet-id", help="Override spreadsheet ID from .env")
    parser.add_argument("--output-sheet", help="Override output sheet name from .env")
    parser.add_argument("--dry-run", action="store_true", help="Calculate equity only, skip OpenAI and sheet writes")
    parser.add_argument("--estimate-only", action="store_true", help="Print projected API cost and exit")
    parser.add_argument("--batch", action="store_true", help="Use OpenAI Batch API (50%% cheaper, async)")
    parser.add_argument("--csv", help="Read from local CSV file instead of Google Sheets")
    return parser.parse_args()


def read_from_csv(file_path: str) -> list[dict]:
    """Read homeowner data from a local CSV file."""
    logger = logging.getLogger(__name__)
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    logger.info("Read %d records from %s", len(records), file_path)
    return records


def _detect_and_normalize(record: dict) -> dict:
    """Auto-detect column format and normalize to Name/Property Value/Mortgage Balance.

    Supports two formats:
    1. Standard: Name, Property Value, Mortgage Balance
    2. Loan export: Borrower Name, Total Loan Amount, Down Payment Amount
       (Property Value = Loan Amount + Down Payment, Mortgage Balance = Loan Amount)
    """
    if "Name" in record:
        return record

    if "Borrower Name" in record:
        name = record.get("Borrower Name", "")
        loan_amount = record.get("Total Loan Amount", 0)
        down_payment = record.get("Down Payment Amount", 0)

        # Flip "Last, First" to "First Last"
        if "," in str(name):
            parts = str(name).split(",", 1)
            name = f"{parts[1].strip()} {parts[0].strip()}"

        try:
            loan_amount = float(str(loan_amount).replace(",", "")) if loan_amount else 0
            down_payment = float(str(down_payment).replace(",", "")) if down_payment else 0
        except (ValueError, TypeError):
            return {"Name": name, "Property Value": "", "Mortgage Balance": ""}

        return {
            "Name": name,
            "Property Value": loan_amount + down_payment,
            "Mortgage Balance": loan_amount,
        }

    return record


def validate_records(records: list[dict]) -> list[HomeownerData]:
    """Validate raw records and return clean HomeownerData objects."""
    logger = logging.getLogger(__name__)
    valid = []

    if records and "Borrower Name" in records[0]:
        logger.info("Detected loan export format, converting automatically")

    for i, record in enumerate(records):
        record = _detect_and_normalize(record)
        name = record.get("Name", "")
        prop_val = record.get("Property Value", "")
        mort_bal = record.get("Mortgage Balance", "")

        homeowner, error = validate_homeowner_data(name, prop_val, mort_bal)
        if error:
            logger.warning("Row %d skipped: %s", i + 2, error)
            continue
        valid.append(homeowner)

    logger.info("Validated %d of %d records", len(valid), len(records))
    return valid


def process_sync(homeowners: list[HomeownerData], dry_run: bool = False) -> list[ProcessingResult]:
    """Process homeowners synchronously."""
    logger = logging.getLogger(__name__)
    results = []

    for homeowner in tqdm(homeowners, desc="Processing homeowners"):
        equity = calculate_equity(homeowner.property_value, homeowner.mortgage_balance)

        if dry_run:
            message = f"[Dry run] Equity: {format_currency(equity.equity)} ({format_percentage(equity.equity_percentage)}) | Position: {equity.position}"
            results.append(ProcessingResult(
                homeowner=homeowner,
                equity=equity,
                message=message,
            ))
            continue

        msg, error = generate_message_sync(homeowner, equity)
        if msg:
            results.append(ProcessingResult(
                homeowner=homeowner,
                equity=equity,
                message=combine_message(msg),
                raw_message=msg,
            ))
        else:
            results.append(ProcessingResult(
                homeowner=homeowner,
                equity=equity,
                message=f"[Error generating message: {error}]",
                error=error,
            ))

    return results


def process_batch(homeowners: list[HomeownerData]) -> list[ProcessingResult]:
    """Process homeowners using OpenAI Batch API."""
    logger = logging.getLogger(__name__)

    # Calculate equity for all
    items = []
    for h in homeowners:
        equity = calculate_equity(h.property_value, h.mortgage_balance)
        items.append((h, equity))

    # Prepare and submit batch
    file_path = prepare_batch_file(items)
    batch_id = submit_batch(file_path)
    logger.info("Batch submitted: %s. Polling for results...", batch_id)

    raw_results = poll_batch(batch_id)

    # Parse results back into ProcessingResults
    results = []
    # Sort by custom_id to maintain order
    raw_results.sort(key=lambda r: int(r["custom_id"].split("-")[1]))

    for raw, (homeowner, equity) in zip(raw_results, items):
        try:
            response = raw["response"]
            body = response["body"]
            content = body["choices"][0]["message"]["content"]
            parsed = EquityMessage.model_validate_json(content)
            results.append(ProcessingResult(
                homeowner=homeowner,
                equity=equity,
                message=combine_message(parsed),
                raw_message=parsed,
            ))
        except Exception as e:
            logger.error("Failed to parse batch result for %s: %s", homeowner.name, e)
            results.append(ProcessingResult(
                homeowner=homeowner,
                equity=equity,
                message=f"[Batch error: {e}]",
                error=str(e),
            ))

    return results


def print_summary(results: list[ProcessingResult]) -> None:
    """Print a summary of processing results."""
    logger = logging.getLogger(__name__)
    total = len(results)
    errors = sum(1 for r in results if r.error)
    positions = {}
    for r in results:
        pos = r.equity.position
        positions[pos] = positions.get(pos, 0) + 1

    print(f"\n{'='*50}")
    print(f"Processing Complete: {total} homeowners")
    print(f"{'='*50}")
    for pos, count in sorted(positions.items()):
        print(f"  {pos}: {count}")
    if errors:
        print(f"  Errors: {errors}")
    print()


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    args = parse_args()
    settings = get_settings()

    sheet_id = args.sheet_id or settings.spreadsheet_id
    output_sheet = args.output_sheet or settings.output_sheet_name

    # Estimate-only mode
    if args.estimate_only:
        if args.csv:
            records = read_from_csv(args.csv)
        else:
            if not sheet_id:
                print("Error: No spreadsheet ID. Use --sheet-id or set SPREADSHEET_ID in .env")
                sys.exit(1)
            client = get_sheets_client(settings.google_sheets_credentials_path)
            records = read_homeowner_data(client, sheet_id, settings.input_sheet_name)

        homeowners = validate_records(records)
        cost = estimate_cost(len(homeowners), use_batch=args.batch)
        print(cost["summary"])
        sys.exit(0)

    # Read data
    if args.csv:
        records = read_from_csv(args.csv)
    else:
        if not sheet_id:
            print("Error: No spreadsheet ID. Use --sheet-id or set SPREADSHEET_ID in .env")
            sys.exit(1)
        client = get_sheets_client(settings.google_sheets_credentials_path)
        records = read_homeowner_data(client, sheet_id, settings.input_sheet_name)

    if not records:
        print("No records found. Exiting.")
        sys.exit(1)

    homeowners = validate_records(records)
    if not homeowners:
        print("No valid records after validation. Exiting.")
        sys.exit(1)

    logger.info("Processing %d homeowners", len(homeowners))

    # Process
    if args.batch and not args.dry_run:
        results = process_batch(homeowners)
    else:
        results = process_sync(homeowners, dry_run=args.dry_run)

    print_summary(results)

    # Write output
    if not args.dry_run and not args.csv:
        write_results(client, sheet_id, output_sheet, results)
        logger.info("Results written to '%s'", output_sheet)
    else:
        # Print results to console in dry-run or CSV mode
        for r in results:
            print(f"{r.homeowner.name}: {r.message}")
            print()


if __name__ == "__main__":
    main()
