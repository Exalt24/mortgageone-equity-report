"""Pure calculation and validation functions for equity analysis."""

import logging
from src.models import HomeownerData, EquityResult

logger = logging.getLogger(__name__)


def classify_equity_position(equity_percentage: float) -> str:
    if equity_percentage >= 20:
        return "Strong Equity"
    if equity_percentage >= 10:
        return "Moderate Equity"
    if equity_percentage >= 0:
        return "Low Equity"
    return "Underwater"


def calculate_equity(property_value: float, mortgage_balance: float) -> EquityResult:
    if property_value <= 0:
        logger.warning("Property value is <= 0 (got %s), returning zeroed result", property_value)
        return EquityResult(
            equity=0.0,
            equity_percentage=0.0,
            ltv=0.0,
            borrowing_capacity=0.0,
            has_strong_equity=False,
            can_remove_pmi=False,
            position="Unknown",
        )

    equity = property_value - mortgage_balance
    equity_percentage = (equity / property_value) * 100
    ltv = (mortgage_balance / property_value) * 100
    borrowing_capacity = max(0.0, (property_value * 0.80) - mortgage_balance)
    position = classify_equity_position(equity_percentage)

    return EquityResult(
        equity=equity,
        equity_percentage=equity_percentage,
        ltv=ltv,
        borrowing_capacity=borrowing_capacity,
        has_strong_equity=equity_percentage >= 20,
        can_remove_pmi=ltv <= 80,
        position=position,
    )


def format_currency(value: float) -> str:
    if value < 0:
        return f"-${abs(value):,.0f}"
    return f"${value:,.0f}"


def format_percentage(value: float) -> str:
    return f"{value:.1f}%"


def validate_homeowner_data(
    name: str,
    property_value_raw,
    mortgage_balance_raw,
) -> tuple[HomeownerData | None, str | None]:
    if name is None or str(name).strip() == "":
        return None, "Name cannot be empty"

    clean_name = str(name).strip()

    try:
        property_value = float(property_value_raw) if property_value_raw is not None and property_value_raw != "" else None
    except (ValueError, TypeError):
        return None, f"Property value must be numeric, got: {property_value_raw!r}"

    if property_value is None:
        return None, "Property value is required"
    if property_value < 0:
        return None, "Property value cannot be negative"

    try:
        mortgage_balance = float(mortgage_balance_raw) if mortgage_balance_raw is not None and mortgage_balance_raw != "" else None
    except (ValueError, TypeError):
        return None, f"Mortgage balance must be numeric, got: {mortgage_balance_raw!r}"

    if mortgage_balance is None:
        return None, "Mortgage balance is required"
    if mortgage_balance < 0:
        return None, "Mortgage balance cannot be negative"

    logger.info("Validated homeowner data for %s", clean_name)
    return HomeownerData(name=clean_name, property_value=property_value, mortgage_balance=mortgage_balance), None
