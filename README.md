# MortgageOne Home Equity Report Generator

Automated pipeline that reads homeowner data from Google Sheets, calculates equity metrics (equity amount, equity percentage, LTV ratio, borrowing capacity, and PMI eligibility), generates personalized messages using AI, and outputs color-coded results back to a formatted Google Sheet ready for review.

## Features

- Reads homeowner data directly from Google Sheets
- Calculates equity, equity %, LTV ratio, borrowing capacity, and PMI eligibility
- Generates personalized messages via OpenAI (structured outputs for consistent format)
- Color-coded output sheet (green = strong equity, yellow = moderate, red = underwater/low)
- CLI with `--dry-run`, `--estimate-only`, `--batch`, and `--csv` modes
- Batch API mode for 50% cost savings at scale
- Progress bar for visual feedback during processing
- Auto-detects input format (standard columns or raw loan export with Borrower Name, Loan Amount, Down Payment)
- Handles edge cases: missing data, negative equity, special characters, empty rows

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/Exalt24/mortgageone-equity-report.git
   cd mortgageone-equity-report
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Google access** (see [Google Sheets Setup](#google-sheets-setup) below)

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your `SPREADSHEET_ID` and `OPENAI_API_KEY`.

   On Windows PowerShell, use:
   ```powershell
   Copy-Item .env.example .env
   ```

5. **Run the report**
   ```bash
   python -m src.main
   ```

To test without any API keys or Google access:

```bash
python -m src.main --dry-run --csv sample_data.csv
```

## Usage

```bash
# Standard run (reads from Google Sheets, generates AI messages, writes results)
python -m src.main

# Dry run (skips OpenAI, no cost incurred, great for testing)
python -m src.main --dry-run

# Cost estimate only (shows what a run would cost without processing)
python -m src.main --estimate-only

# Batch mode (50% cheaper, processes asynchronously within 24 hours)
python -m src.main --batch

# Local CSV file (useful for testing or one-off lists)
python -m src.main --csv sample_data.csv --dry-run

# Override sheet ID or output worksheet name
python -m src.main --sheet-id YOUR_ID --output-sheet "March Reports"
```

## Google Sheets Setup

This tool uses a Google Cloud service account to read and write spreadsheet data. Here is how to set that up:

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Enable the **Google Sheets API** and the **Google Drive API**
4. Go to **Credentials** > **Create Credentials** > **Service Account**
5. Download the JSON key file and save it as `credentials.json` in the project root
6. Copy the service account email (it looks like `name@project.iam.gserviceaccount.com`)
7. Open your Google Sheet, click **Share**, paste the service account email, and give it **Editor** access

The tool auto-detects two input formats:

**Standard format:**

| Name | Property Value | Mortgage Balance |
|------|---------------|-----------------|
| Jane Smith | 450000 | 320000 |

**Loan export format** (paste directly from your loan system):

| Borrower Name | Total Loan Amount | Down Payment Amount | ... |
|--------------|------------------|--------------------| --- |
| Smith, Jane | 320000 | 80000 | ... |

When loan export format is detected, the tool automatically flips "Last, First" names, calculates property value from loan amount plus down payment, and processes everything. No manual conversion needed.

The tool reads from the input sheet, runs calculations, and writes results to a separate output worksheet.

## Configuration

All settings are managed through environment variables in your `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_SHEETS_CREDENTIALS_PATH` | Path to service account JSON | `credentials.json` |
| `SPREADSHEET_ID` | Google Sheet ID (from the URL) | (required) |
| `INPUT_SHEET_NAME` | Worksheet to read from | `Homeowner Data` |
| `OUTPUT_SHEET_NAME` | Worksheet to write to | `Equity Reports` |
| `OPENAI_API_KEY` | OpenAI API key | (required) |
| `OPENAI_MODEL` | Model to use | `gpt-4o-mini` |
| `OPENAI_TEMPERATURE` | Message creativity (0.0-1.0) | `0.4` |
| `SENDER_NAME` | Loan officer name in messages | `Chris Lamm` |

The `SPREADSHEET_ID` is the long string in your Google Sheet URL between `/d/` and `/edit`. For example, in `https://docs.google.com/spreadsheets/d/abc123xyz/edit`, the ID is `abc123xyz`.

## Architecture

The pipeline flows in a straight line:

```
Google Sheets -> Validate Data -> Calculate Equity -> Generate AI Messages -> Color-Format -> Output Sheet
```

Each step is handled by a focused module:

- **src/config.py** - Environment configuration and validation
- **src/models.py** - Data contracts using Pydantic for type safety
- **src/equity.py** - Equity calculations (LTV, borrowing capacity, PMI eligibility)
- **src/message_generator.py** - OpenAI integration with both sync and batch modes
- **src/sheets.py** - Google Sheets read/write with color formatting
- **src/main.py** - CLI parsing and pipeline orchestration

## Cost Analysis

Costs using GPT-4o-mini (as of March 2026):

| Homeowners | Sync | Sync + Cache | Batch | Batch + Cache |
|------------|------|--------------|-------|---------------|
| 100 | $0.02 | $0.01 | $0.01 | $0.01 |
| 1,000 | $0.20 | $0.11 | $0.10 | $0.05 |
| 10,000 | $1.95 | $1.07 | $0.98 | $0.53 |

Prompt caching kicks in automatically for repeated system prompts longer than 1,024 tokens. Batch API processes requests asynchronously within 24 hours in exchange for the 50% discount.

**Compared to Homebot:** Homebot pricing starts at $125/month (Starter, 200 clients) and goes up to $300/month (Unlimited), plus a $100 setup fee. This tool costs approximately $0.01 to $0.05 per run depending on list size and mode.

## Compliance Notes

- **CAN-SPAM Act:** Messages generated by this tool should be sent through a CAN-SPAM compliant email platform with proper unsubscribe mechanisms, accurate sender information, and a physical mailing address.
- **Homebuyers Privacy Protection Act (March 2026):** This law restricts trigger lead sales. Equity reports sent to existing clients with a pre-existing business relationship are fully compliant.
- **TRID (TILA-RESPA):** Generated messages do not constitute loan estimates or closing disclosures. They are informational equity updates only.

## Testing

```bash
python -m pytest tests/ -v
```

Tests cover:

- Equity calculations (normal, underwater, zero-value, high-value properties)
- Data validation (missing fields, special characters, type conversion)
- Message generation (mocked OpenAI responses, refusal handling)
- Integration pipeline (dry run mode, validation errors)

## Future Enhancements

- **Email Delivery:** SendGrid or Mailgun integration for automated monthly delivery (note: SendGrid requires a paid plan since May 2025, Mailgun offers 1,000 free emails/month)
- **Market Data Integration:** ATTOM or Zillow API for automated home value estimates instead of manual entry
- **Refinance Calculator:** Model rate scenarios and show potential savings for each homeowner
- **Rate Drop Alerts:** Trigger personalized outreach when rates drop below a homeowner's current rate (22% re-engagement rate industry average)
- **Dashboard:** Web interface for the team to manage homeowner lists, view reports, and track engagement
- **Homeowner Check-In:** Periodic "how's your home?" messages for relationship building
- **White-Label:** Package for mortgage coaching clients to use with their own branding
- **Full Homebot Replacement:** Market temperature, rental income estimates, extra payment calculator, purchasing power module

## License

MIT
