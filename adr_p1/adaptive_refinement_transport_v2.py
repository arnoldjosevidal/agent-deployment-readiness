"""R3 adapter limits; preserve the exact transport class identity required by NebiusModel."""
from .exploratory_transport import (
    ExploratoryTransport, validate_billing_preflight, AUTOTOPUP_EXCEPTION_REFERENCE,
    CAMPAIGN_ID, CASE_ORDER, PAIR_ID, MAX_CONTEXT, MAX_INPUT, MAX_OUTPUT, RESERVE_PER_TOKEN,
)
from .transport import Limits, MODEL

def exploratory_limits():
    return Limits(
        model=MODEL, max_requests=42, max_total_tokens=42 * MAX_CONTEXT,
        max_input_tokens=MAX_INPUT, max_output_tokens=MAX_OUTPUT,
        max_call_ms=30_000, max_total_ms=900_000, max_retries=0,
        budget_usd="0.07858938880", reservation_usd_per_token=RESERVE_PER_TOKEN,
    ).validate()
