import pytest
from src.equity import (
    calculate_equity,
    classify_equity_position,
    format_currency,
    format_percentage,
    validate_homeowner_data,
)


class TestCalculateEquity:
    def test_normal_case(self):
        result = calculate_equity(450_000, 280_000)
        assert result.equity == 170_000
        assert round(result.equity_percentage, 1) == 37.8
        assert round(result.ltv, 1) == 62.2
        assert result.borrowing_capacity == 80_000
        assert result.position == "Strong Equity"
        assert result.can_remove_pmi is True

    def test_zero_mortgage(self):
        result = calculate_equity(400_000, 0)
        assert result.equity == 400_000
        assert result.equity_percentage == 100.0
        assert result.ltv == 0.0
        assert result.borrowing_capacity == 320_000
        assert result.can_remove_pmi is True

    def test_underwater(self):
        result = calculate_equity(420_000, 435_000)
        assert result.equity == -15_000
        assert result.ltv > 100
        assert result.borrowing_capacity == 0
        assert result.position == "Underwater"

    def test_zero_property_value(self):
        result = calculate_equity(0, 150_000)
        assert result.equity == 0
        assert result.equity_percentage == 0
        assert result.ltv == 0
        assert result.borrowing_capacity == 0
        assert result.position == "Unknown"

    def test_very_high_values(self):
        result = calculate_equity(10_000_000, 5_000_000)
        assert result.equity == 5_000_000
        assert round(result.equity_percentage, 1) == 50.0
        assert round(result.ltv, 1) == 50.0
        assert result.borrowing_capacity == 3_000_000

    def test_equal_values(self):
        result = calculate_equity(400_000, 400_000)
        assert result.equity == 0
        assert result.equity_percentage == 0.0
        assert result.ltv == 100.0
        assert result.borrowing_capacity == 0
        assert result.position == "Low Equity"

    def test_just_over_20_percent_equity(self):
        result = calculate_equity(500_000, 399_000)
        assert result.position == "Strong Equity"
        assert result.can_remove_pmi is True

    def test_just_under_20_percent_equity(self):
        result = calculate_equity(500_000, 401_000)
        assert result.position == "Moderate Equity"
        assert result.can_remove_pmi is False


class TestClassifyEquityPosition:
    @pytest.mark.parametrize(
        "percentage, expected",
        [
            (25, "Strong Equity"),
            (15, "Moderate Equity"),
            (5, "Low Equity"),
            (-5, "Underwater"),
            (20, "Strong Equity"),
            (10, "Moderate Equity"),
            (0, "Low Equity"),
        ],
    )
    def test_classification(self, percentage, expected):
        assert classify_equity_position(percentage) == expected


class TestFormatCurrency:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (170_000, "$170,000"),
            (-15_000, "-$15,000"),
            (0, "$0"),
            (1_234_567.89, "$1,234,568"),
        ],
    )
    def test_format(self, value, expected):
        assert format_currency(value) == expected


class TestFormatPercentage:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (37.78, "37.8%"),
            (100.0, "100.0%"),
            (-3.57, "-3.6%"),
        ],
    )
    def test_format(self, value, expected):
        assert format_percentage(value) == expected


class TestValidateHomeownerData:
    def test_valid_data(self):
        data, error = validate_homeowner_data("John Smith", 450_000, 280_000)
        assert data is not None
        assert error is None

    def test_empty_name(self):
        data, error = validate_homeowner_data("", 450_000, 280_000)
        assert data is None
        assert error is not None

    def test_none_name(self):
        data, error = validate_homeowner_data(None, 450_000, 280_000)
        assert data is None
        assert error is not None

    def test_text_in_property_value(self):
        data, error = validate_homeowner_data("John", "abc", 280_000)
        assert data is None
        assert error is not None

    def test_empty_property_value(self):
        data, error = validate_homeowner_data("John", "", 280_000)
        assert data is None
        assert error is not None

    def test_none_property_value(self):
        data, error = validate_homeowner_data("John", None, 280_000)
        assert data is None
        assert error is not None

    def test_negative_property_value(self):
        data, error = validate_homeowner_data("John", -100, 280_000)
        assert data is None
        assert error is not None

    def test_string_numbers_convert(self):
        data, error = validate_homeowner_data("John", "450000", "280000")
        assert data is not None
        assert error is None

    def test_whitespace_name_stripped(self):
        data, error = validate_homeowner_data("  John Smith  ", 450_000, 280_000)
        assert data is not None
        assert data.name == "John Smith"

    def test_special_chars_in_name(self):
        data, error = validate_homeowner_data("O'Brien", 380_000, 152_000)
        assert data is not None
        assert error is None

    def test_hyphenated_name(self):
        data, error = validate_homeowner_data("Martinez-Lopez", 395_000, 316_000)
        assert data is not None
        assert error is None
