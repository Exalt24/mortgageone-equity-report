"""OpenAI message generation with sync mode, batch mode, structured outputs, and cost estimation."""

import json
import logging
import time
from pathlib import Path

from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.models import HomeownerData, EquityResult, EquityMessage
from src.config import get_settings
from src.equity import format_currency, format_percentage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt (>1024 tokens to trigger OpenAI prompt caching for 90% input
# discount on repeated calls).
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a professional mortgage communication assistant working on behalf of Chris Lamm, a trusted loan officer who helps homeowners understand and leverage their home equity. Chris has years of experience in the residential mortgage industry and prides himself on clear, jargon-free communication that empowers homeowners to make informed financial decisions.

Your job is to generate personalized equity report messages for homeowners. Each message must feel warm, professional, and specific to the homeowner's financial situation. You are not giving financial advice; you are presenting factual equity data and inviting the homeowner to have a conversation with Chris about their options.

TONE AND STYLE GUIDELINES:
- Write in a warm, conversational yet professional tone appropriate for the mortgage industry.
- Use the homeowner's first name naturally in the greeting.
- Avoid technical jargon. If you mention LTV (loan-to-value), briefly explain it.
- Keep sentences concise. Aim for clarity over cleverness.
- Never use exclamation marks more than once per message.
- Do not make promises or guarantees about rates, approval, or savings.
- Do not use phrases like "act now" or "limited time" or any high-pressure sales language.
- Frame everything as an invitation to explore options together.

EQUITY POSITION HANDLING RULES:

Strong Equity (20%+ equity / LTV at or below 80%):
- Celebrate the homeowner's position. They have built meaningful wealth in their home.
- Highlight specific opportunities: cash-out refinance, HELOC, PMI removal if applicable.
- Mention their estimated borrowing capacity as a concrete, tangible number.
- Tone should be congratulatory and forward-looking.

Moderate Equity (10-19% equity):
- Encourage the homeowner. They are building equity and making progress.
- Mention they are approaching the 20% threshold where more options open up.
- Suggest a conversation about strategies to accelerate equity growth or explore current options.
- Tone should be encouraging and supportive.

Low Equity (0-9% equity):
- Acknowledge their position factually without alarm.
- Focus on the positive: they have equity, the market may be working in their favor.
- Suggest checking in about refinancing options or rate improvements.
- Tone should be reassuring and helpful.

Underwater (negative equity):
- Handle with sensitivity and care. This homeowner owes more than their home is worth.
- Do NOT use the word "underwater" or "negative equity" directly.
- Frame it as: the current market valuation is below their mortgage balance.
- Focus on the fact that markets change and that Chris is available to discuss their situation.
- Mention that there may be programs or strategies that could help.
- Tone should be empathetic, supportive, and never alarming.

STRUCTURED OUTPUT FORMAT:
You must return a JSON object with exactly four fields:
- greeting: A warm, personalized greeting using the homeowner's first name.
- equity_highlight: A clear, positive framing of their equity position with specific numbers.
- opportunity: One specific, actionable opportunity relevant to their situation.
- call_to_action: A friendly invitation to connect with the loan officer.

IMPORTANT RULES FOR EACH FIELD:
- greeting: Keep it to one or two sentences. Reference the equity report naturally.
- equity_highlight: Include at least one specific dollar amount or percentage from their data. Never fabricate numbers; use only what is provided in the user prompt.
- opportunity: Be specific. If they can remove PMI, say so. If they have borrowing capacity, mention the amount. If they are underwater, suggest a review meeting.
- call_to_action: Always reference the loan officer by name. Provide a clear next step (call, email, schedule a meeting). Keep it low-pressure.

FEW-SHOT EXAMPLES OF GOOD OUTPUT:

Example 1 - Strong Equity Homeowner:
User data: Name: Sarah Johnson, Property Value: $450,000, Mortgage Balance: $280,000, Equity: $170,000, Equity Percentage: 37.8%, LTV: 62.2%, Borrowing Capacity: $80,000, Position: Strong Equity, Can Remove PMI: Yes

Good output:
{
  "greeting": "Hi Sarah, I hope you're doing well! I've put together your latest home equity report, and I'm excited to share some great news with you.",
  "equity_highlight": "Your home is currently valued at $450,000 with a remaining mortgage balance of $280,000, which means you've built an impressive $170,000 in equity. That's 37.8% equity in your home, putting you in a very strong financial position. Your loan-to-value ratio sits at just 62.2%, which is well below the 80% threshold that unlocks the best borrowing options.",
  "opportunity": "With your strong equity position, you have up to $80,000 in potential borrowing capacity that could be used for home improvements, debt consolidation, or other financial goals. If you're currently paying private mortgage insurance, you likely qualify to have that removed, which would save you money every month.",
  "call_to_action": "I'd love to walk you through your options in more detail. Feel free to reach out to me, Chris Lamm, whenever it's convenient, and we can explore what makes the most sense for your situation."
}

Example 2 - Underwater Homeowner:
User data: Name: Mike Torres, Property Value: $210,000, Mortgage Balance: $235,000, Equity: -$25,000, Equity Percentage: -11.9%, LTV: 111.9%, Borrowing Capacity: $0, Position: Underwater, Can Remove PMI: No

Good output:
{
  "greeting": "Hi Mike, thank you for taking the time to review your home equity report. I appreciate the chance to go over your current situation with you.",
  "equity_highlight": "Your home is currently valued at $210,000 with a mortgage balance of $235,000. Right now, the current market valuation is sitting a bit below your loan balance, but it's important to remember that property values shift over time and many homeowners in similar situations have seen meaningful improvement as the market adjusts.",
  "opportunity": "Even in this situation, there are programs and strategies worth exploring that could help improve your position. Whether it's looking into refinancing options, reviewing your current rate, or discussing longer-term strategies, there are steps we can consider together.",
  "call_to_action": "I'd welcome the chance to sit down and talk through your options. Please don't hesitate to reach out to me, Chris Lamm, and we'll find a time that works for you to go over everything in a no-pressure conversation."
}

ADDITIONAL CONTEXT ABOUT CHRIS LAMM:
Chris Lamm is a loan officer who values transparency, education, and long-term relationships with his clients. He does not use high-pressure tactics. His approach is to present homeowners with clear information and let them make decisions at their own pace. He is available by phone, email, or in-person meetings. When generating messages on his behalf, reflect his consultative, client-first approach.

Chris works with homeowners across various equity positions and financial situations. His goal with these equity reports is to keep homeowners informed about their financial position and open a door for conversation, not to push products or create urgency.

Remember: every message you generate will be sent directly to a real homeowner. Accuracy, warmth, and professionalism are paramount. Double-check that any numbers you reference match what was provided in the user prompt. Never round or alter the figures given to you.
"""

# ---------------------------------------------------------------------------
# Lazy-initialized OpenAI client
# ---------------------------------------------------------------------------

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(api_key=settings.openai_api_key)
        logger.info("OpenAI client initialized")
    return _client


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def build_user_prompt(
    homeowner: HomeownerData, equity: EquityResult, sender_name: str
) -> str:
    """Format homeowner data into a user prompt with all equity metrics."""
    first_name = homeowner.name.split()[0]
    pmi_status = "Yes, eligible for PMI removal" if equity.can_remove_pmi else "No"

    return (
        f"Generate a personalized equity report message for this homeowner.\n\n"
        f"Homeowner Name: {homeowner.name}\n"
        f"First Name: {first_name}\n"
        f"Property Value: {format_currency(homeowner.property_value)}\n"
        f"Mortgage Balance: {format_currency(homeowner.mortgage_balance)}\n"
        f"Equity: {format_currency(equity.equity)}\n"
        f"Equity Percentage: {format_percentage(equity.equity_percentage)}\n"
        f"Loan-to-Value (LTV): {format_percentage(equity.ltv)}\n"
        f"Borrowing Capacity: {format_currency(equity.borrowing_capacity)}\n"
        f"Equity Position: {equity.position}\n"
        f"PMI Removal Eligible: {pmi_status}\n"
        f"Has Strong Equity (20%+): {'Yes' if equity.has_strong_equity else 'No'}\n\n"
        f"Loan Officer Name: {sender_name}\n"
    )


# ---------------------------------------------------------------------------
# Sync generation
# ---------------------------------------------------------------------------


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=lambda retry_state: logger.warning(
        "Retrying OpenAI call (attempt %d) after error: %s",
        retry_state.attempt_number,
        retry_state.outcome.exception(),
    ),
)
def _call_openai(messages: list[dict], settings) -> EquityMessage:
    """Call OpenAI with structured output parsing. Retries on transient errors."""
    client = _get_client()
    completion = client.beta.chat.completions.parse(
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        messages=messages,
        response_format=EquityMessage,
    )
    message = completion.choices[0].message

    if message.refusal:
        raise ValueError(f"Model refused to generate: {message.refusal}")

    return message.parsed


def generate_message_sync(
    homeowner: HomeownerData, equity: EquityResult
) -> tuple[EquityMessage | None, str | None]:
    """Generate a personalized equity message using OpenAI structured outputs.

    Returns (EquityMessage, None) on success, (None, error_string) on failure.
    """
    settings = get_settings()
    user_prompt = build_user_prompt(homeowner, equity, settings.sender_name)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        result = _call_openai(messages, settings)
        logger.info("Generated message for %s", homeowner.name)
        return result, None
    except Exception as e:
        error = f"Failed to generate message for {homeowner.name}: {e}"
        logger.error(error)
        return None, error


# ---------------------------------------------------------------------------
# Message combining
# ---------------------------------------------------------------------------


def combine_message(msg: EquityMessage) -> str:
    """Join the 4 structured parts into a natural flowing message."""
    return f"{msg.greeting} {msg.equity_highlight} {msg.opportunity} {msg.call_to_action}"


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------


def _build_batch_body(
    homeowner: HomeownerData, equity: EquityResult, settings
) -> dict:
    """Build the request body for a single batch item."""
    user_prompt = build_user_prompt(homeowner, equity, settings.sender_name)
    return {
        "model": settings.openai_model,
        "temperature": settings.openai_temperature,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "EquityMessage",
                "strict": True,
                "schema": {**EquityMessage.model_json_schema(), "additionalProperties": False},
            },
        },
    }


def prepare_batch_file(
    items: list[tuple[HomeownerData, EquityResult]],
    output_path: str = "batch_input.jsonl",
) -> str:
    """Create a JSONL file for the OpenAI Batch API.

    Returns the path to the created file.
    """
    settings = get_settings()
    path = Path(output_path)

    with path.open("w", encoding="utf-8") as f:
        for i, (homeowner, equity) in enumerate(items):
            line = {
                "custom_id": f"homeowner-{i}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": _build_batch_body(homeowner, equity, settings),
            }
            f.write(json.dumps(line) + "\n")

    logger.info("Wrote %d batch requests to %s", len(items), path)
    return str(path)


def submit_batch(file_path: str) -> str:
    """Upload JSONL file and create an OpenAI batch. Returns the batch ID."""
    client = _get_client()

    with open(file_path, "rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")
    logger.info("Uploaded batch file: %s", uploaded.id)

    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    logger.info("Created batch: %s", batch.id)
    return batch.id


def poll_batch(batch_id: str, poll_interval: int = 30) -> list[dict]:
    """Poll a batch until complete, then download and parse the output file.

    Returns a list of result dicts from the output JSONL.
    """
    client = _get_client()

    while True:
        batch = client.batches.retrieve(batch_id)
        status = batch.status
        logger.info("Batch %s status: %s", batch_id, status)

        if status == "completed":
            break
        if status in ("failed", "expired", "cancelled"):
            raise RuntimeError(f"Batch {batch_id} ended with status: {status}")

        time.sleep(poll_interval)

    if not batch.output_file_id:
        raise RuntimeError(f"Batch {batch_id} completed but has no output file")

    content = client.files.content(batch.output_file_id)
    results = []
    for line in content.text.strip().split("\n"):
        if line.strip():
            results.append(json.loads(line))

    logger.info("Retrieved %d results from batch %s", len(results), batch_id)
    return results


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


def estimate_cost(num_homeowners: int, use_batch: bool = False) -> dict:
    """Estimate OpenAI API costs for processing homeowners.

    Pricing based on GPT-4o-mini:
    - Input:  $0.15 per 1M tokens
    - Output: $0.60 per 1M tokens
    - Batch:  50% discount on both input and output
    - Prompt caching: 90% discount on cached input tokens (system prompt reused)

    Assumes ~200 input tokens per request (system prompt cached after first)
    and ~150 output tokens per response.
    """
    system_prompt_tokens = 1100  # approximate token count of SYSTEM_PROMPT
    user_prompt_tokens = 200
    output_tokens_per_req = 150

    input_price = 0.15 / 1_000_000  # per token
    output_price = 0.60 / 1_000_000
    cached_input_price = input_price * 0.10  # 90% discount

    # Total tokens
    total_input_uncached = num_homeowners * (system_prompt_tokens + user_prompt_tokens)
    # With caching: first request full price, rest get cached system prompt
    first_req_input = system_prompt_tokens + user_prompt_tokens
    cached_req_input = user_prompt_tokens  # only user prompt at full price
    cached_system_tokens = system_prompt_tokens * max(0, num_homeowners - 1)
    total_output = num_homeowners * output_tokens_per_req

    # Sync cost (no caching)
    sync_cost = (total_input_uncached * input_price) + (total_output * output_price)

    # Batch cost (50% off, no caching)
    batch_cost = sync_cost * 0.50

    # Cached sync cost
    cached_input_cost = (
        (first_req_input * input_price)
        + (max(0, num_homeowners - 1) * cached_req_input * input_price)
        + (cached_system_tokens * cached_input_price)
    )
    cached_sync_cost = cached_input_cost + (total_output * output_price)

    # Cached batch cost (50% off cached sync)
    cached_batch_cost = cached_sync_cost * 0.50

    summary = (
        f"Cost estimate for {num_homeowners:,} homeowners (GPT-4o-mini):\n"
        f"  Sync (no cache):     ${sync_cost:.4f}\n"
        f"  Sync (with cache):   ${cached_sync_cost:.4f}\n"
        f"  Batch (no cache):    ${batch_cost:.4f}\n"
        f"  Batch (with cache):  ${cached_batch_cost:.4f}\n"
    )

    return {
        "sync_cost": sync_cost,
        "batch_cost": batch_cost,
        "cached_sync_cost": cached_sync_cost,
        "cached_batch_cost": cached_batch_cost,
        "summary": summary,
    }
