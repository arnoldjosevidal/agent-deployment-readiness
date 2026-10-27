"""Separate exploratory approval-demo transport. It explicitly does not satisfy B1."""
from datetime import datetime, timezone
from decimal import Decimal
import os
import time

from adr_g64r.common import SafetyError, canonical, identifier, utc
from .transport import Transport, hashed, _wire, MODEL


SCOPE = "EXPLORATORY_LIVE_NON_B1"
CLASSIFICATION = "EXPLORATORY_LIVE_NON_B1"
SCENARIOS = {"calendar_allow", "email_approve", "email_reject"}
MAX_REQUESTS = 6
MAX_INPUT = 8192
MAX_OUTPUT = 1024
MAX_REQUEST_MS = 30_000
MAX_SESSION_MS = 240_000
MAX_BUDGET_USD = Decimal("0.01")
RESERVE_TOKENS = MAX_INPUT + MAX_OUTPUT
RESERVE_USD_PER_TOKEN = Decimal("0.0000000968")


class ApprovalExploratoryTransport(Transport):
    """Uses a local estimate as a stop threshold; never claims provider token certification."""

    def request(self, rid, messages, *, tools=None, authorization=None,
                token_certificate=None, deadline_ms=None, before_wire=None):
        identifier(rid)
        lim, auth, cert = self.limits, authorization or {}, token_certificate or {}
        if (auth.get("human_approved") is not True or auth.get("execution_enabled") is not True
                or auth.get("scope") != SCOPE or auth.get("classification") != CLASSIFICATION
                or auth.get("b1_status") != "BLOCKED" or auth.get("session_id") != self.session
                or auth.get("config_hash") != self.config_hash
                or auth.get("scenario_id") not in SCENARIOS
                or not isinstance(auth.get("approval_reference"), str)
                or not auth.get("approval_reference")):
            raise SafetyError("EXPLORATORY_NON_B1_GRANT_SCOPE_REQUIRED")
        try:
            expiry = datetime.fromisoformat(auth["expires_utc"])
            expiry_ok = expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)
        except (KeyError, TypeError, ValueError):
            expiry_ok = False
        if not expiry_ok:
            raise SafetyError("EXPLORATORY_NON_B1_GRANT_EXPIRED")
        if (lim.model != MODEL or lim.max_requests != MAX_REQUESTS
                or lim.max_input_tokens != MAX_INPUT or lim.max_output_tokens != MAX_OUTPUT
                or lim.max_call_ms != MAX_REQUEST_MS or lim.max_total_ms != MAX_SESSION_MS
                or lim.max_retries != 0 or Decimal(lim.budget_usd) != MAX_BUDGET_USD
                or Decimal(lim.reservation_usd_per_token) != RESERVE_USD_PER_TOKEN
                or lim.max_total_tokens != MAX_REQUESTS * RESERVE_TOKENS):
            raise SafetyError("EXPLORATORY_NON_B1_LIMITS_INVALID")
        billing = auth.get("billing_preflight")
        if not isinstance(billing, dict) or billing.get("verified_in_official_console") is not True:
            raise SafetyError("EXPLORATORY_NON_B1_FINANCIAL_PREFLIGHT_REQUIRED")
        try:
            balance = Decimal(billing["available_prepaid_balance_usd"])
            checked = datetime.fromisoformat(billing["verified_utc"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - checked).total_seconds()
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise SafetyError("EXPLORATORY_NON_B1_FINANCIAL_PREFLIGHT_INVALID") from None
        if (billing.get("organization_id") != "Independent-y4p" or not balance.is_finite()
                or balance < MAX_BUDGET_USD or checked.tzinfo is None or age < 0 or age > 1800):
            raise SafetyError("EXPLORATORY_NON_B1_FINANCIAL_PREFLIGHT_INVALID")
        topup_ok = billing.get("autotopup_status") == "VERIFIED_DISABLED" and billing.get("autotopup_disabled") is True
        exception = billing.get("autotopup_exception")
        topup_exception_ok = (billing.get("autotopup_status") == "NOT_VERIFIED"
            and isinstance(exception, dict) and exception.get("accepted_by_owner") is True
            and exception.get("risk_accepted_by_owner") is True
            and exception.get("scope") == SCOPE
            and exception.get("approval_reference") == auth.get("approval_reference"))
        if not (topup_ok or topup_exception_ok):
            raise SafetyError("EXPLORATORY_NON_B1_AUTOTOPUP_PREFLIGHT_REQUIRED")
        pricing = billing.get("provider_pricing")
        if (not isinstance(pricing, dict) or pricing.get("model") != MODEL
                or pricing.get("input_usd_per_million") != "0.06"
                or pricing.get("output_usd_per_million") != "0.24"
                or pricing.get("source_url") != "https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference"):
            raise SafetyError("EXPLORATORY_NON_B1_TARIFF_PREFLIGHT_REQUIRED")
        try:
            price_checked = datetime.fromisoformat(pricing["verified_utc"].replace("Z", "+00:00"))
            price_age = (datetime.now(timezone.utc) - price_checked).total_seconds()
        except (AttributeError, KeyError, TypeError, ValueError):
            raise SafetyError("EXPLORATORY_NON_B1_TARIFF_PREFLIGHT_REQUIRED") from None
        if price_checked.tzinfo is None or price_age < 0 or price_age > 1800:
            raise SafetyError("EXPLORATORY_NON_B1_TARIFF_PREFLIGHT_STALE")

        payload = {"model": lim.model, "messages": messages, "max_tokens": lim.max_output_tokens,
                   "temperature": 0.0, "stream": False, "store": False}
        recorded_classification = "OFFLINE_MOCK_NEBIUS_TRANSPORT_NOT_PROVIDER" if os.environ.get("ADR_TEST_OUTPUT") else CLASSIFICATION
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        if not isinstance(messages, list) or not messages or len(canonical(payload)) > 1_000_000:
            raise SafetyError("EXPLORATORY_NON_B1_INVALID_REQUEST")
        if (cert.get("verified") is not False or cert.get("model") != lim.model
                or cert.get("payload_sha256") != hashed(payload)
                or cert.get("tokenizer_revision") != "a9904d24bcc1d289a1950fa9d2b978c47cf903b9"
                or type(cert.get("local_template_tokens")) is not int
                or not 0 <= cert["local_template_tokens"] <= MAX_INPUT):
            raise SafetyError("EXPLORATORY_NON_B1_LOCAL_ESTIMATE_INVALID")

        reserve_usd = RESERVE_TOKENS * RESERVE_USD_PER_TOKEN
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS approval_exploratory_requests (session TEXT NOT NULL,id TEXT NOT NULL,scenario TEXT NOT NULL,PRIMARY KEY(session,id))")
            if db.execute("SELECT 1 FROM p1_requests WHERE session=? AND id=?", (self.session, rid)).fetchone():
                raise SafetyError("DUPLICATE_REQUEST")
            started, stopped = db.execute("SELECT start_ns,stopped FROM p1_sessions WHERE id=?", (self.session,)).fetchone()
            elapsed = (time.monotonic_ns() - started) / 1_000_000
            rows = db.execute("SELECT reserved_tokens,reserved_usd FROM p1_requests WHERE session=?", (self.session,)).fetchall()
            count = db.execute("SELECT count(*) FROM approval_exploratory_requests WHERE session=? AND scenario=?", (self.session, auth["scenario_id"])).fetchone()[0]
            reason = stopped
            if elapsed < 0 or elapsed >= MAX_SESSION_MS: reason = reason or "SESSION_TIME_LIMIT"
            if len(rows) >= MAX_REQUESTS: reason = reason or "SESSION_REQUEST_LIMIT"
            if count >= 2: reason = reason or "SCENARIO_REQUEST_LIMIT"
            if sum(r[0] for r in rows) + RESERVE_TOKENS > lim.max_total_tokens: reason = reason or "SESSION_TOKEN_LIMIT"
            if sum((Decimal(r[1]) for r in rows), Decimal(0)) + reserve_usd > MAX_BUDGET_USD: reason = reason or "LOCAL_BUDGET_LIMIT"
            if reason:
                db.execute("UPDATE p1_sessions SET stopped=? WHERE id=?", (reason, self.session)); db.commit()
                raise SafetyError(reason)
            timeout = min(MAX_REQUEST_MS, int(MAX_SESSION_MS - elapsed), deadline_ms if type(deadline_ms) is int else MAX_REQUEST_MS)
            if timeout <= 0:
                db.rollback(); raise SafetyError("SESSION_TIME_LIMIT")
            db.execute("INSERT INTO p1_requests VALUES (?,?,?,?,?,?,NULL,NULL,NULL,?)",
                (self.session, rid, hashed(payload), "STARTED", RESERVE_TOKENS, str(reserve_usd), utc()))
            db.execute("INSERT INTO approval_exploratory_requests VALUES (?,?,?)", (self.session, rid, auth["scenario_id"]))
            self._event(db, rid, "request", payload_sha256=hashed(payload), classification=recorded_classification,
                        b1_status="BLOCKED_NOT_CLAIMED", local_template_tokens=cert["local_template_tokens"],
                        provider_token_bound_certified=False, scenario_id=auth["scenario_id"],
                        input_counter_version=cert.get("counter_version", "legacy-local-counter"),
                        input_counter_profile_id=cert.get("counter_profile_id", "legacy-local-profile"),
                        input_counter_tokenizer_sha256=cert.get("tokenizer_sha256"),
                        input_counter_template_sha256=cert.get("template_sha256"),
                        input_counter_rendered_sha256=cert.get("rendered_prompt_sha256"),
                        input_counter_limit=cert.get("input_limit", MAX_INPUT),
                        input_counter_admission=cert.get("within_input_limit", True),
                        input_counter_runtime_versions=cert.get("runtime_versions"))
            self._event(db, rid, "authorization", approval_reference=auth["approval_reference"],
                        config_hash=self.config_hash, organization_id=billing["organization_id"],
                        balance_usd=str(balance), autotopup_status=billing.get("autotopup_status"),
                        autotopup_exception_accepted=topup_exception_ok,
                        tariff_source=pricing["source_url"])
            self._event(db, rid, "reservation", timeout_ms=timeout, reserved_tokens=RESERVE_TOKENS,
                        reserved_usd=str(reserve_usd), cap_is_local_only=True)
            db.commit()
        try:
            if before_wire:
                before_wire()
            key = os.environ.get("NEBIUS_API_KEY")
            if not key:
                raise SafetyError("CREDENTIAL_UNAVAILABLE")
            response = _wire(payload, key, timeout)
        except BaseException as exc:
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE p1_requests SET status='ERROR_UNKNOWN_USAGE' WHERE session=? AND id=?", (self.session, rid))
                db.execute("UPDATE p1_sessions SET stopped='ERROR_UNKNOWN_USAGE_NO_RETRY' WHERE id=?", (self.session,))
                self._event(db, rid, "error", error_type=type(exc).__name__, usage="UNKNOWN_RESERVATION_RETAINED",
                            classification=recorded_classification)
                db.commit()
            raise SafetyError("EXPLORATORY_NON_B1_REQUEST_STOPPED_UNKNOWN_USAGE") from None
        usage = response.get("usage", {})
        input_tokens, output_tokens, total_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens")
        if (response.get("model") != MODEL or type(input_tokens) is not int or type(output_tokens) is not int
                or type(total_tokens) is not int or total_tokens != input_tokens + output_tokens):
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE p1_requests SET status='ERROR_UNKNOWN_USAGE',response_hash=? WHERE session=? AND id=?", (hashed(response), self.session, rid))
                db.execute("UPDATE p1_sessions SET stopped='PROVIDER_USAGE_UNKNOWN_NO_RETRY' WHERE id=?", (self.session,))
                self._event(db, rid, "error", error_type="PROVIDER_USAGE_UNKNOWN", usage="UNKNOWN_RESERVATION_RETAINED", response_sha256=hashed(response))
                db.commit()
            raise SafetyError("EXPLORATORY_NON_B1_PROVIDER_USAGE_UNKNOWN")
        observed = (Decimal(input_tokens) * Decimal("0.00000006") + Decimal(output_tokens) * Decimal("0.00000024")) * Decimal("1.21")
        choices = response.get("choices")
        valid = (0 <= input_tokens <= MAX_INPUT and 0 <= output_tokens <= MAX_OUTPUT
                 and isinstance(choices, list) and len(choices) == 1
                 and isinstance(choices[0].get("message"), dict)
                 and choices[0]["message"].get("role") == "assistant")
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            status = "COMPLETE" if valid else "OBSERVED_USAGE_OR_COMPLETION_INVALID"
            db.execute("UPDATE p1_requests SET status=?,input_tokens=?,output_tokens=?,response_hash=? WHERE session=? AND id=?",
                       (status, input_tokens, output_tokens, hashed(response), self.session, rid))
            self._event(db, rid, "result" if valid else "error", response_sha256=hashed(response),
                        input_tokens=input_tokens, output_tokens=output_tokens,
                        estimated_cost_with_21pct_usd=str(observed), cost_is_invoice=False, status=status)
            rows = db.execute("SELECT input_tokens,output_tokens FROM p1_requests WHERE session=? AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL", (self.session,)).fetchall()
            spent = sum(((Decimal(r[0]) * Decimal("0.00000006") + Decimal(r[1]) * Decimal("0.00000024")) * Decimal("1.21") for r in rows), Decimal(0))
            if not valid or spent > MAX_BUDGET_USD:
                db.execute("UPDATE p1_sessions SET stopped=? WHERE id=?", ("USAGE_OR_BUDGET_STOP", self.session))
            db.commit()
        if not valid:
            raise SafetyError("EXPLORATORY_NON_B1_USAGE_OR_COMPLETION_INVALID")
        if spent > MAX_BUDGET_USD:
            raise SafetyError("EXPLORATORY_NON_B1_BUDGET_STOP")
        return response
