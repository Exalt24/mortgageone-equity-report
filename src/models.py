from pydantic import BaseModel, Field


class HomeownerData(BaseModel):
    """Raw homeowner data from Google Sheets."""

    name: str
    property_value: float
    mortgage_balance: float


class EquityResult(BaseModel):
    """Calculated equity metrics."""

    equity: float
    equity_percentage: float
    ltv: float
    borrowing_capacity: float
    has_strong_equity: bool
    can_remove_pmi: bool
    position: str  # "Strong Equity", "Moderate Equity", "Low Equity", "Underwater"


class EquityMessage(BaseModel):
    """Structured output from OpenAI. All fields required for structured outputs compliance."""

    greeting: str = Field(description="Warm greeting using homeowner's first name")
    equity_highlight: str = Field(
        description="Positive framing of their equity position"
    )
    opportunity: str = Field(
        description="One specific actionable opportunity based on their numbers"
    )
    call_to_action: str = Field(
        description="Invitation to discuss options with the loan officer"
    )


class ProcessingResult(BaseModel):
    """Result for a single homeowner after full pipeline."""

    homeowner: HomeownerData
    equity: EquityResult
    message: str  # Combined message text
    raw_message: EquityMessage | None = None  # Structured parts, None if generation failed
    error: str | None = None
