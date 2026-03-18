from unittest.mock import patch, MagicMock
import pytest
from src.models import HomeownerData, EquityResult, EquityMessage, ProcessingResult
from src.main import validate_records, process_sync, print_summary


class TestValidateRecords:
    def test_valid_records(self):
        records = [
            {"Name": "John Smith", "Property Value": "450000", "Mortgage Balance": "280000"},
            {"Name": "Jane Doe", "Property Value": "350000", "Mortgage Balance": "150000"},
        ]
        result = validate_records(records)
        assert len(result) == 2

    def test_skips_invalid_records(self):
        records = [
            {"Name": "John Smith", "Property Value": "450000", "Mortgage Balance": "280000"},
            {"Name": "", "Property Value": "", "Mortgage Balance": ""},
            {"Name": "Bad Data", "Property Value": "abc", "Mortgage Balance": "200000"},
        ]
        result = validate_records(records)
        assert len(result) == 1

    def test_empty_records(self):
        result = validate_records([])
        assert len(result) == 0


class TestProcessSync:
    def test_dry_run_skips_openai(self):
        homeowners = [
            HomeownerData(name="John Smith", property_value=450000, mortgage_balance=280000),
        ]
        # dry_run should NOT call OpenAI at all
        results = process_sync(homeowners, dry_run=True)
        assert len(results) == 1
        assert "[Dry run]" in results[0].message
        assert results[0].error is None

    @patch("src.main.generate_message_sync")
    @patch("src.main.combine_message")
    def test_sync_with_mocked_openai(self, mock_combine, mock_generate):
        mock_msg = EquityMessage(
            greeting="Hi John,",
            equity_highlight="Great equity!",
            opportunity="Consider a HELOC.",
            call_to_action="Call Chris.",
        )
        mock_generate.return_value = (mock_msg, None)
        mock_combine.return_value = "Hi John, Great equity! Consider a HELOC. Call Chris."

        homeowners = [
            HomeownerData(name="John Smith", property_value=450000, mortgage_balance=280000),
        ]
        results = process_sync(homeowners, dry_run=False)
        assert len(results) == 1
        assert "Hi John" in results[0].message
        assert results[0].error is None


class TestPrintSummary:
    def test_prints_without_error(self, capsys):
        results = [
            ProcessingResult(
                homeowner=HomeownerData(name="John", property_value=450000, mortgage_balance=280000),
                equity=EquityResult(equity=170000, equity_percentage=37.8, ltv=62.2, borrowing_capacity=80000, has_strong_equity=True, can_remove_pmi=True, position="Strong Equity"),
                message="Test message",
            ),
        ]
        print_summary(results)
        captured = capsys.readouterr()
        assert "1 homeowners" in captured.out
        assert "Strong Equity" in captured.out
