"""Isolated real-model demo transport; distinct from all frozen grants.

B1 remains unresolved. The pinned public tokenizer is only a local estimate.
Each request is limited locally to 8192 estimated input and 2048 output tokens;
unknown usage retains reservation and stops. This is not a provider-side cap.
"""
from decimal import Decimal
import hashlib
import json
import os
import time
from datetime import datetime, timezone

from adr_g64r.common import SafetyError, canonical, identifier, utc
from .transport import Transport, Limits, MODEL, _wire, hashed

CASE_ORDER = ("MVP1_A_00", "MVP1_G_00")
CAMPAIGN_ID = "ADR_ADAPTIVE_CAMPAIGN_20261024"
PAIR_ID = CAMPAIGN_ID
AUTOTOPUP_EXCEPTION_REFERENCE = "USER_AUTH_ADR_ADAPTIVE_CAMPAIGN_20261024"
MAX_CONTEXT = 10_240  # local reservation: 8192 input + 2048 output
MAX_INPUT = 8_192
MAX_OUTPUT = 2_048
# Weighted worst-case cap mix: (8192 input at $0.06/M + 2048 output at
# $0.24/M) plus 21%; local reserve only, not provider-enforced billing.
RESERVE_PER_TOKEN = "0.00000011616"


def validate_billing_preflight(billing, approval_reference):
    """Validate the current official balance, tariff, and this test-only exception."""
    try:
        balance = Decimal(billing["available_prepaid_balance_usd"])
    except (KeyError, TypeError, ValueError):
        raise SafetyError("BILLING_PREFLIGHT_UNVERIFIED") from None
    if (not balance.is_finite() or balance < Decimal("0.10")
            or billing.get("organization_id") != "Independent-y4p"):
        raise SafetyError("BILLING_PREFLIGHT_UNVERIFIED")
    if billing.get("verified_in_official_console") is not True:
        raise SafetyError("BILLING_PREFLIGHT_UNVERIFIED")
    pricing = billing.get("provider_pricing")
    if not isinstance(pricing, dict):
        raise SafetyError("PROVIDER_PRICING_PREFLIGHT_UNVERIFIED")
    try:
        checked_at = datetime.fromisoformat(pricing["verified_utc"].replace("Z", "+00:00"))
        age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
    except (AttributeError, KeyError, TypeError, ValueError):
        raise SafetyError("PROVIDER_PRICING_PREFLIGHT_UNVERIFIED") from None
    if (pricing.get("source_url") != "https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference"
            or pricing.get("model") != MODEL
            or pricing.get("input_usd_per_million") != "0.06"
            or pricing.get("output_usd_per_million") != "0.24"
            or pricing.get("published_context_tokens") != 1_048_576
            or checked_at.tzinfo is None or age_seconds < 0 or age_seconds > 1800):
        raise SafetyError("PROVIDER_PRICING_PREFLIGHT_UNVERIFIED")
    if (billing.get("autotopup_disabled") is True
            and billing.get("autotopup_status") == "VERIFIED_DISABLED"):
        return {"status": "AUTOTOPUP_DISABLED_VERIFIED", "balance_usd": str(balance),
                "exception_reference": None}
    exception = billing.get("autotopup_exception")
    if (billing.get("autotopup_status") == "NOT_VERIFIED"
            and billing.get("autotopup_disabled") is None
            and isinstance(exception, dict)
            and exception.get("accepted_by_owner") is True
            and exception.get("risk_accepted_by_owner") is True
            and exception.get("scope") == CAMPAIGN_ID
            and exception.get("approval_reference") == AUTOTOPUP_EXCEPTION_REFERENCE
            and approval_reference == AUTOTOPUP_EXCEPTION_REFERENCE):
        return {"status": "NOT_VERIFIED_OWNER_EXCEPTION_ACCEPTED_CAMPAIGN_ONLY",
                "balance_usd": str(balance),
                "exception_reference": AUTOTOPUP_EXCEPTION_REFERENCE}
    raise SafetyError("BILLING_PREFLIGHT_UNVERIFIED")


def exploratory_limits():
    return Limits(
        model=MODEL,
        max_requests=42,
        max_total_tokens=42 * MAX_CONTEXT,
        max_input_tokens=MAX_INPUT,
        max_output_tokens=MAX_OUTPUT,
        max_call_ms=30_000,
        max_total_ms=900_000,
        max_retries=0,
        budget_usd="0.07858938880",
        reservation_usd_per_token=RESERVE_PER_TOKEN,
    ).validate()


class ExploratoryTransport(Transport):
    """Transport requiring an explicit, scoped B1 deviation on every request."""

    def request(self, rid, messages, *, tools=None, authorization=None,
                token_certificate=None, deadline_ms=None, before_wire=None):
        identifier(rid)
        lim = self.limits
        auth = authorization or {}
        cert = token_certificate or {}
        if (auth.get("human_approved") is not True
                or auth.get("exploratory_b1_deviation") is not True
                or auth.get("execution_enabled") is not True
                or auth.get("scope") != CAMPAIGN_ID
                or auth.get("case_ids") != list(CASE_ORDER)
                or auth.get("pair_id") != PAIR_ID
                or auth.get("planned_case_id") not in CASE_ORDER
                or auth.get("adaptive_scenario_id") not in {
                    "B_TOOL_OUTPUT_LAUNDERING", "C_FALSE_DEPENDENCY",
                    "F_CONTEXT_CONTAMINATION", "D_MULTI_STEP",
                    "E_FALSE_APPROVAL", "A_AUTHORITY_SPOOFING",
                    "ACCEPTANCE_B_TOOL_OUTPUT_LAUNDERING",
                }
                or auth.get("session_id") != self.session
                or auth.get("config_hash") != self.config_hash
                or auth.get("max_spend_usd") != "0.07858938880"
                or auth.get("max_requests_total") != 42
                or auth.get("max_requests_per_case") != 12
                or auth.get("max_input_tokens_per_request") != 8192
                or auth.get("max_output_tokens_per_request") != 2048
                or auth.get("max_retries") != 0
                or auth.get("concurrency") != 1
                or not auth.get("approval_reference")):
            raise SafetyError("EXPLORATORY_GRANT_SCOPE_REQUIRED")
        billing = auth.get("billing_preflight") or {}
        billing_status = validate_billing_preflight(billing, auth.get("approval_reference"))
        try:
            expires = datetime.fromisoformat(auth["expires_utc"])
            valid_expiry = expires.tzinfo is not None and expires > datetime.now(timezone.utc)
        except (KeyError, TypeError, ValueError):
            valid_expiry = False
        if not valid_expiry:
            raise SafetyError("EXPLORATORY_GRANT_EXPIRED")
        if (not isinstance(messages, list) or not messages
                or cert.get("verified") is not False
                or cert.get("payload_sha256") != hashed({
                    "model": lim.model, "messages": messages,
                    "max_tokens": lim.max_output_tokens, "temperature": 0.0,
                    "stream": False, "store": False,
                    **({"tools": tools, "tool_choice": "auto"} if tools else {}),
                })
                or cert.get("model") != lim.model
                or type(cert.get("local_template_tokens")) is not int
                or cert["local_template_tokens"] < 0
                or cert["local_template_tokens"] > lim.max_input_tokens):
            raise SafetyError("EXPLORATORY_UNVERIFIED_CERTIFICATE_MISMATCH")
        payload = {
            "model": lim.model, "messages": messages,
            "max_tokens": lim.max_output_tokens, "temperature": 0.0,
            "stream": False, "store": False,
        }
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        raw_payload = canonical(payload)
        if len(raw_payload) > 1_000_000 or hashed(payload) != cert["payload_sha256"]:
            raise SafetyError("EXPLORATORY_PAYLOAD_MISMATCH")

        # Reserve the approved local input+output ceiling before each call.
        # The provider-side tokenizer remains unverified; this is not B1.
        reserve_tokens = MAX_CONTEXT
        reserve_usd = Decimal(reserve_tokens) * Decimal(lim.reservation_usd_per_token)
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS p1_exploratory_case_requests (session TEXT NOT NULL,id TEXT NOT NULL,case_id TEXT NOT NULL,PRIMARY KEY(session,id))")
            if db.execute("SELECT 1 FROM p1_requests WHERE session=? AND id=?", (self.session, rid)).fetchone():
                raise SafetyError("DUPLICATE_REQUEST")
            start_ns, stopped = db.execute("SELECT start_ns,stopped FROM p1_sessions WHERE id=?", (self.session,)).fetchone()
            elapsed = (time.monotonic_ns() - start_ns) / 1_000_000
            rows = db.execute("SELECT reserved_tokens,reserved_usd FROM p1_requests WHERE session=?", (self.session,)).fetchall()
            case_count = db.execute("SELECT count(*) FROM p1_exploratory_case_requests WHERE session=? AND case_id=?", (self.session, auth["adaptive_scenario_id"])).fetchone()[0]
            reason = stopped or ("SESSION_TIME_LIMIT" if elapsed >= lim.max_total_ms else None)
            if len(rows) >= lim.max_requests:
                reason = reason or "SESSION_REQUEST_LIMIT"
            if case_count >= 12:
                reason = reason or "CASE_REQUEST_LIMIT"
            if sum(r[0] for r in rows) + reserve_tokens > lim.max_total_tokens:
                reason = reason or "SESSION_TOKEN_RESERVATION_LIMIT"
            if sum((Decimal(r[1]) for r in rows), Decimal(0)) + reserve_usd > Decimal(lim.budget_usd):
                reason = reason or "LOCAL_BUDGET_RESERVATION_LIMIT"
            if reason:
                db.execute("UPDATE p1_sessions SET stopped=? WHERE id=?", (reason, self.session))
                db.commit()
                raise SafetyError(reason)
            timeout_ms = min(lim.max_call_ms, int(lim.max_total_ms - elapsed),
                             deadline_ms if type(deadline_ms) is int else lim.max_call_ms)
            if timeout_ms <= 0:
                db.rollback()
                raise SafetyError("SESSION_TIME_LIMIT")
            db.execute("INSERT INTO p1_requests VALUES (?,?,?,?,?,?,NULL,NULL,NULL,?)",
                       (self.session, rid, hashed(payload), "STARTED", reserve_tokens, str(reserve_usd), utc()))
            db.execute("INSERT INTO p1_exploratory_case_requests VALUES (?,?,?)",
                       (self.session, rid, auth["adaptive_scenario_id"]))
            self._event(db, rid, "request", payload_sha256=hashed(payload),
                        classification="REAL_EXPLORATORY_B1_DEVIATION_NOT_PILOT",
                        local_template_tokens=cert["local_template_tokens"])
            self._event(db, rid, "authorization", approval_reference=auth["approval_reference"],
                        config_hash=self.config_hash, b1_status="BLOCKED_PROTOCOL_DEVIATION_EXPLORATORY",
                        billing_preflight_status=billing_status["status"],
                        organization_id=billing["organization_id"],
                        available_prepaid_balance_usd=billing_status["balance_usd"],
                        trial_credit_usd=billing.get("trial_credit_usd"),
                        usage_displayed_usd=billing.get("usage_displayed_usd"),
                        balance_source=billing.get("balance_source"),
                        autotopup_status=billing.get("autotopup_status"),
                        autotopup_exception_reference=billing_status["exception_reference"],
                        pricing_source_url=billing["provider_pricing"]["source_url"],
                        input_usd_per_million=billing["provider_pricing"]["input_usd_per_million"],
                        output_usd_per_million=billing["provider_pricing"]["output_usd_per_million"],
                        pricing_verified_utc=billing["provider_pricing"]["verified_utc"])
            self._event(db, rid, "execution_start", timeout_ms=timeout_ms,
                        reserved_tokens=reserve_tokens, reserved_usd=str(reserve_usd))
            db.commit()
        try:
            if before_wire:
                before_wire()
            key = os.environ.get("NEBIUS_API_KEY")
            if not key:
                raise SafetyError("CREDENTIAL_UNAVAILABLE")
            response = _wire(payload, key, timeout_ms)
            usage = response.get("usage", {})
            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
            if (response.get("model") != lim.model or type(input_tokens) is not int
                    or type(output_tokens) is not int or type(total_tokens) is not int
                    or total_tokens != input_tokens + output_tokens):
                raise SafetyError("PROVIDER_USAGE_UNKNOWN")
            observed_cost_pre_tax = (Decimal(input_tokens) * Decimal("0.00000006")
                                     + Decimal(output_tokens) * Decimal("0.00000024"))
            observed_cost_with_tax = observed_cost_pre_tax * Decimal("1.21")
            within = (0 <= input_tokens <= lim.max_input_tokens
                      and 0 <= output_tokens <= lim.max_output_tokens
                      and total_tokens <= lim.max_total_tokens)
            choices = response.get("choices")
            valid_completion = (isinstance(choices, list) and len(choices) == 1
                                and isinstance(choices[0].get("message"), dict)
                                and choices[0]["message"].get("role") == "assistant")
            response_hash = hashed(response)
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                status = "COMPLETE" if within and valid_completion else "OBSERVED_USAGE_OR_COMPLETION_INVALID"
                db.execute("UPDATE p1_requests SET status=?,input_tokens=?,output_tokens=?,response_hash=? WHERE session=? AND id=?",
                           (status, input_tokens, output_tokens, response_hash, self.session, rid))
                self._event(db, rid, "result" if status == "COMPLETE" else "error",
                            response_sha256=response_hash, input_tokens=input_tokens,
                            output_tokens=output_tokens, observed_cost_pre_tax_usd=str(observed_cost_pre_tax),
                            observed_cost_at_21pct_tax_usd=str(observed_cost_with_tax),
                            status=status)
                if status != "COMPLETE" or observed_cost_with_tax > Decimal(lim.budget_usd):
                    db.execute("UPDATE p1_sessions SET stopped=? WHERE id=?",
                               ("USAGE_OR_BUDGET_LIMIT", self.session))
                db.commit()
            if status != "COMPLETE" or observed_cost_with_tax > Decimal(lim.budget_usd):
                raise SafetyError("OBSERVED_USAGE_OR_BUDGET_LIMIT_STOPPED")
            return response
        except BaseException as exc:
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT status FROM p1_requests WHERE session=? AND id=?", (self.session, rid)).fetchone()
                if row and row[0] == "STARTED":
                    db.execute("UPDATE p1_requests SET status='ERROR_UNKNOWN_USAGE' WHERE session=? AND id=?", (self.session, rid))
                code=exc.args[0] if isinstance(exc,SafetyError) and exc.args and isinstance(exc.args[0],str) else "UNCLASSIFIED"
                if len(code)>120 or not all(c.isalnum() or c in "_:.-" for c in code):code="UNCLASSIFIED"
                self._event(db, rid, "error", error_type=type(exc).__name__, error_code=code,
                            usage="UNKNOWN_RESERVATION_RETAINED")
                db.execute("UPDATE p1_sessions SET stopped=COALESCE(stopped,'REQUEST_ERROR') WHERE id=?", (self.session,))
                db.commit()
            raise SafetyError("REQUEST_FAILED_STOPPED") from None

