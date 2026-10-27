"""Campaign-scoped Nebius transport. Network is unreachable without a fresh grant.

The 8,192 input limit is a local template-token ceiling only. This class never
marks the provider binding verified and never retries a request.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
import re
import time

from adr_g64r.common import SafetyError, canonical, digest
from adr_p1.transport import MODEL, _wire
from adr_campaign.campaign_runner import (
    CAMPAIGN_ID, CLASSIFICATION, CampaignError, CampaignStore,
    CampaignLimits, PRICE_SOURCE,
)


class CampaignTransport:
    def __init__(self, evidence_store, campaign_store: CampaignStore, session_id: str,
                 authorization: dict):
        if not isinstance(campaign_store, CampaignStore):
            raise SafetyError("DURABLE_CAMPAIGN_SINK_REQUIRED")
        from adr_g64r.storage import EvidenceStore
        if not isinstance(evidence_store, EvidenceStore):
            raise SafetyError("DURABLE_EPISODE_SINK_REQUIRED")
        self.store = evidence_store
        self.campaign = campaign_store
        self.session = session_id
        self.authorization = deepcopy(authorization)
        self.current_episode = None
        self.current_run_id = None
        self.config_hash = self.campaign.config_sha256
        self._validate_grant()

    def _validate_grant(self):
        a = self.authorization
        if (a.get("campaign_id") != CAMPAIGN_ID
                or a.get("scope") != "ADR_S1_37_PAIR_EXPLORATORY"
                or a.get("execution_enabled") is not True
                or a.get("human_approved") is not True
                or a.get("exploratory_b1_deviation") is not True
                or a.get("campaign_plan_sha256") != self.campaign.plan_sha256
                or a.get("campaign_config_sha256") != self.campaign.config_sha256
                or a.get("max_requests_total") != 888
                or a.get("max_spend_usd") != "5.00"
                or a.get("max_spend_per_lot_usd") != "0.60"
                or a.get("max_output_tokens_per_request") != 2048
                or a.get("max_output_tokens_campaign_total") != 1_818_624
                or a.get("max_input_tokens_local_per_request") != 8192
                or a.get("max_retries") != 0 or a.get("concurrency") != 1
                or a.get("b1_status") != "BLOCKED_PROTOCOL_DEVIATION_EXPLORATORY"
                or a.get("provider_token_binding_verified") is not False
                or a.get("authorized_lots") != list(range(1, 9))
                or not isinstance(a.get("approval_reference"), str)
                or not a["approval_reference"]):
            raise SafetyError("CAMPAIGN_GRANT_SCOPE_OR_LIMIT_MISMATCH")
        try:
            expiry = datetime.fromisoformat(a["expires_utc"])
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise SafetyError("CAMPAIGN_GRANT_EXPIRED") from None
        billing = a.get("billing_preflight")
        if not isinstance(billing, dict) or billing.get("verified_by_owner") is not True:
            raise SafetyError("CURRENT_FINANCIAL_PREFLIGHT_REQUIRED")
        try:
            balance = Decimal(billing["available_prepaid_balance_usd"])
        except (KeyError, TypeError, ValueError):
            raise SafetyError("CURRENT_FINANCIAL_PREFLIGHT_REQUIRED") from None
        if not balance.is_finite() or balance < Decimal("5.00"):
            raise SafetyError("CAMPAIGN_BALANCE_BELOW_AUTHORIZED_CAP")
        topup_status = billing.get("autotopup_status")
        if topup_status == "NOT_VERIFIED":
            # A campaign-specific, user-approved exception may waive only the
            # auto-topup check; preserve the unknown status and bind the waiver
            # to this grant's explicit approval reference.
            if (billing.get("autotopup_disabled") is not False
                    or billing.get("autotopup_exception_approved") is not True
                    or billing.get("autotopup_exception_reference") != a.get("approval_reference")
                    or a.get("financial_exception") != "AUTOTOPUP_NOT_VERIFIED_ACCEPTED"):
                raise SafetyError("CURRENT_AUTOTOPUP_VERIFICATION_REQUIRED")
        elif topup_status != "VERIFIED_DISABLED" or billing.get("autotopup_disabled") is not True:
            raise SafetyError("CURRENT_AUTOTOPUP_VERIFICATION_REQUIRED")
        try:
            billing_checked = datetime.fromisoformat(billing["verified_utc"].replace("Z", "+00:00"))
            billing_age = (datetime.now(timezone.utc) - billing_checked).total_seconds()
        except (AttributeError, KeyError, TypeError, ValueError):
            raise SafetyError("CURRENT_FINANCIAL_PREFLIGHT_REQUIRED") from None
        if billing_checked.tzinfo is None or billing_age < 0 or billing_age > 1800:
            raise SafetyError("CURRENT_FINANCIAL_PREFLIGHT_REQUIRED")
        pricing = billing.get("provider_pricing")
        if not isinstance(pricing, dict):
            raise SafetyError("CURRENT_PROVIDER_PRICING_REQUIRED")
        try:
            checked = datetime.fromisoformat(pricing["verified_utc"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - checked).total_seconds()
        except (AttributeError, KeyError, TypeError, ValueError):
            raise SafetyError("CURRENT_PROVIDER_PRICING_REQUIRED") from None
        if (pricing.get("source_url") != PRICE_SOURCE
                or pricing.get("model") != MODEL
                or pricing.get("input_usd_per_million") != "0.06"
                or pricing.get("output_usd_per_million") != "0.24"
                or checked.tzinfo is None or age < 0 or age > 1800):
            raise SafetyError("CURRENT_PROVIDER_PRICING_REQUIRED")

    def bind_episode(self, planned_id: str, run_id: str):
        if not any(r["planned_episode_id"] == planned_id for r in self.campaign.queue):
            raise SafetyError("UNPLANNED_EPISODE_OR_COMPLETED_PAIR")
        self.current_episode, self.current_run_id = planned_id, run_id

    def request(self, rid, messages, *, tools=None, authorization=None,
                token_certificate=None, deadline_ms=None, before_wire=None):
        a = authorization or {}
        cert = token_certificate or {}
        if (not self.current_episode or a.get("planned_case_id") != self.current_episode
                or a.get("execution_enabled") is not True
                or a.get("human_approved") is not True
                or a.get("exploratory_b1_deviation") is not True
                or a.get("campaign_id") != CAMPAIGN_ID
                or a.get("campaign_plan_sha256") != self.campaign.plan_sha256
                or a.get("campaign_config_sha256") != self.campaign.config_sha256
                or self.campaign.active_lot() not in a.get("authorized_lots", [])
                or a.get("approval_reference") != self.authorization.get("approval_reference")):
            raise SafetyError("CAMPAIGN_REQUEST_SCOPE_MISMATCH")
        self._validate_grant()
        try:
            suffix = re.fullmatch(re.escape(self.current_run_id) + r"-m(\d{2})", rid)
            if not suffix:
                raise ValueError
            ordinal = int(suffix.group(1))
            campaign_rid = f"{self.current_episode}-r{ordinal:02d}"
            local_tokens = cert["local_template_tokens"]
            payload = {"model": MODEL, "messages": messages,
                       "max_tokens": 2048, "temperature": 0.0,
                       "stream": False, "store": False}
            if tools:
                payload.update(tools=tools, tool_choice="auto")
            if (not isinstance(messages, list) or not messages
                    or cert.get("verified") is not False
                    or cert.get("payload_sha256") != digest(canonical(payload))
                    or cert.get("model") != MODEL
                    or type(local_tokens) is not int or not 0 <= local_tokens <= 8192
                    or cert.get("upper_bound") != 8192):
                raise SafetyError("LOCAL_TOKEN_BOUND_OR_PAYLOAD_MISMATCH")
            if len(canonical(payload)) > 1_000_000:
                raise SafetyError("PAYLOAD_BYTES_LIMIT")
        except (KeyError, TypeError, ValueError):
            raise SafetyError("CAMPAIGN_REQUEST_METADATA_INVALID") from None
        deadline = min(30_000, deadline_ms if type(deadline_ms) is int else 30_000)
        if deadline <= 0:
            raise SafetyError("EPISODE_DEADLINE_EXHAUSTED")
        try:
            lease = self.campaign.reserve_request(self.current_episode, campaign_rid, local_tokens)
        except CampaignError as exc:
            raise SafetyError(str(exc)) from None
        if before_wire:
            before_wire()
        key = os.environ.get("NEBIUS_API_KEY")
        if not key:
            self.campaign.stop("CREDENTIAL_UNAVAILABLE_AFTER_RESERVATION")
            raise SafetyError("CREDENTIAL_UNAVAILABLE")
        start = time.monotonic_ns()
        try:
            response = _wire(payload, key, deadline)
            usage = response.get("usage", {})
            input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if (response.get("model") != MODEL or type(input_tokens) is not int
                    or type(output_tokens) is not int
                    or type(usage.get("total_tokens")) is not int
                    or usage["total_tokens"] != input_tokens + output_tokens):
                raise SafetyError("PROVIDER_USAGE_UNKNOWN")
            elapsed_ms = int((time.monotonic_ns() - start) / 1_000_000)
            response_sha = digest(canonical(response))
            self.campaign.complete_request(campaign_rid,
                provider_input_tokens=input_tokens, output_tokens=output_tokens,
                elapsed_ms=elapsed_ms, response_sha256=response_sha)
            return response
        except BaseException as exc:
            self.campaign.stop("REQUEST_FAILED_OR_USAGE_UNKNOWN")
            if isinstance(exc, SafetyError):
                raise
            raise SafetyError("REQUEST_FAILED_STOPPED") from None

