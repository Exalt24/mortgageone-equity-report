from unittest.mock import patch, MagicMock
import pytest
from src.models import HomeownerData, EquityResult, EquityMessage
from src.message_generator import (
    build_user_prompt,
    generate_message_sync,
    combine_message,
    estimate_cost,
)


class TestBuildUserPrompt:
    def test_includes_homeowner_data(self):
        homeowner = HomeownerData(name="John Smith", property_value=450000, mortgage_balance=280000)
        equity = EquityResult(equity=170000, equity_percentage=37.8, ltv=62.2, borrowing_capacity=80000, has_strong_equity=True, can_remove_pmi=True, position="Strong Equity")
        prompt = build_user_prompt(homeowner, equity, "Chris Lamm")
        assert "John" in prompt
        assert "$450,000" in prompt
        assert "$280,000" in prompt
        assert "Strong Equity" in prompt
        assert "Chris Lamm" in prompt

    def test_uses_first_name(self):
        homeowner = HomeownerData(name="Dorothy O'Brien", property_value=380000, mortgage_balance=152000)
        equity = EquityResult(equity=228000, equity_percentage=60.0, ltv=40.0, borrowing_capacity=152000, has_strong_equity=True, can_remove_pmi=True, position="Strong Equity")
        prompt = build_user_prompt(homeowner, equity, "Chris")
        assert "Dorothy" in prompt


class TestCombineMessage:
    def test_combines_all_parts(self):
        msg = EquityMessage(
            greeting="Hi John,",
            equity_highlight="Your equity is $170,000.",
            opportunity="You could remove PMI.",
            call_to_action="Call Chris to discuss.",
        )
        result = combine_message(msg)
        assert "Hi John," in result
        assert "Your equity is $170,000." in result
        assert "You could remove PMI." in result
        assert "Call Chris to discuss." in result


class TestGenerateMessageSync:
    @patch("src.message_generator._get_client")
    def test_successful_generation(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_msg = MagicMock()
        mock_msg.refusal = None
        mock_msg.parsed = EquityMessage(
            greeting="Hi Sarah,",
            equity_highlight="Great equity!",
            opportunity="Consider a HELOC.",
            call_to_action="Let's chat.",
        )
        mock_client.beta.chat.completions.parse.return_value = MagicMock(
            choices=[MagicMock(message=mock_msg)]
        )

        homeowner = HomeownerData(name="Sarah Johnson", property_value=450000, mortgage_balance=280000)
        equity = EquityResult(equity=170000, equity_percentage=37.8, ltv=62.2, borrowing_capacity=80000, has_strong_equity=True, can_remove_pmi=True, position="Strong Equity")

        result, error = generate_message_sync(homeowner, equity)
        assert result is not None
        assert error is None
        assert result.greeting == "Hi Sarah,"

    @patch("src.message_generator._get_client")
    def test_refusal_handling(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_msg = MagicMock()
        mock_msg.refusal = "I cannot generate this content"
        mock_client.beta.chat.completions.parse.return_value = MagicMock(
            choices=[MagicMock(message=mock_msg)]
        )

        homeowner = HomeownerData(name="Test User", property_value=400000, mortgage_balance=200000)
        equity = EquityResult(equity=200000, equity_percentage=50.0, ltv=50.0, borrowing_capacity=120000, has_strong_equity=True, can_remove_pmi=True, position="Strong Equity")

        result, error = generate_message_sync(homeowner, equity)
        assert result is None
        assert error is not None
        assert "refused" in error.lower() or "refusal" in error.lower() or "Failed" in error


class TestEstimateCost:
    def test_returns_all_fields(self):
        result = estimate_cost(100)
        assert "sync_cost" in result
        assert "batch_cost" in result
        assert "cached_sync_cost" in result
        assert "cached_batch_cost" in result
        assert "summary" in result

    def test_batch_cheaper_than_sync(self):
        result = estimate_cost(1000)
        assert result["batch_cost"] < result["sync_cost"]

    def test_cached_cheaper_than_uncached(self):
        result = estimate_cost(1000)
        assert result["cached_sync_cost"] < result["sync_cost"]
