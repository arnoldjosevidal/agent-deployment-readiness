"""Fresh-grant composition for EXPLORATORY_LIVE_NON_B1 only."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

from adr_g64r.common import SafetyError, canonical, digest
from adr_g64r.storage import EvidenceStore
from adr_p1.transport import Limits, MODEL
from adr_p1.approval_exploratory_transport import ApprovalExploratoryTransport, SCOPE, CLASSIFICATION
from .model_port import NebiusApprovalModel

ROOT = Path(__file__).resolve().parents[1]
PLAN_REL = "config/EXPLORATORY_LIVE_NON_B1_PLAN_V2.json"
BOUND_FILES = (
    "adr_approval/exploratory_live_runtime.py", "adr_approval/model_port.py",
    "adr_approval/workflow.py", "adr_approval/service.py", "adr_approval/server.py",
    "adr_approval/index.html",
    "adr_p1/approval_exploratory_transport.py", "adr_p1/transport.py",
    "adr_live/model.py", "adr_live/counter_v031.py", "adr_live/counter_worker_v031.py",
    "scripts/install_counter_v031.ps1", "diagnostics/test_counter_v031_integration.py",
    "run_approval_exploratory_live.py", "wire_worker.py",
    "adr_gateb/design.py", "adr_gateb/policy.py", "freeze_reference/MANIFEST_SHA256.json",
    "diagnostics/test_exploratory_live_non_b1.py",
    "config/PROVIDER_TOKEN_BINDING.json", "assets/nemotron_tokenizer/tokenizer.json",
    "assets/nemotron_tokenizer/tokenizer_config.json", "assets/nemotron_tokenizer/chat_template.jinja",
    "assets/nemotron_tokenizer/special_tokens_map.json",
    "vendor/nemotron-input-counter-v0.3.1/README.md",
    "vendor/nemotron-input-counter-v0.3.1/request-contract.md",
    "vendor/nemotron-input-counter-v0.3.1/NOTICE.txt",
    "vendor/nemotron-input-counter-v0.3.1/LICENSE.NVIDIA",
    "vendor/nemotron-input-counter-v0.3.1/requirements.txt",
    "vendor/nemotron-input-counter-v0.3.1/count_request.py",
    "vendor/nemotron-input-counter-v0.3.1/count_chat.py",
    "vendor/nemotron-input-counter-v0.3.1/serving_profile.py",
    "vendor/nemotron-input-counter-v0.3.1/renderer.py",
    "vendor/nemotron-input-counter-v0.3.1/served_template.jinja",
    "vendor/nemotron-input-counter-v0.3.1/manifest.json",
    "vendor/nemotron-input-counter-v0.3.1/SHA256SUMS",
    "vendor/nemotron-input-counter-v0.3.1/tokenizer/tokenizer.json",
    "vendor/nemotron-input-counter-v0.3.1/tokenizer/tokenizer_config.json",
    "vendor/nemotron-input-counter-v0.3.1/tokenizer/special_tokens_map.json",
    PLAN_REL,
)
LIMIT_VALUES = {
    "model": MODEL, "max_requests": 6, "max_total_tokens": 55_296,
    "max_input_tokens": 8_192, "max_output_tokens": 1_024,
    "max_call_ms": 30_000, "max_total_ms": 240_000,
    "max_retries": 0, "budget_usd": "0.01",
    "reservation_usd_per_token": "0.0000000968",
}


def candidate_identity(root: Path = ROOT) -> dict:
    files = {}
    for relative in BOUND_FILES:
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise SafetyError("EXPLORATORY_CANDIDATE_FILE_MISSING")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": files, "sha256": digest(canonical(files))}


def _contains_secret_key(obj):
    if isinstance(obj, dict):
        return any(str(k).lower() in {"api_key", "apikey", "token", "secret", "credential"}
                   or _contains_secret_key(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_contains_secret_key(v) for v in obj)
    return False


def _check_billing(billing: dict, approval_reference: str):
    if not isinstance(billing, dict) or billing.get("verified_in_official_console") is not True:
        raise SafetyError("EXPLORATORY_FINANCIAL_PREFLIGHT_REQUIRED")
    try:
        balance = Decimal(billing["available_prepaid_balance_usd"])
        checked = datetime.fromisoformat(billing["verified_utc"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - checked).total_seconds()
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise SafetyError("EXPLORATORY_FINANCIAL_PREFLIGHT_INVALID") from None
    if (billing.get("organization_id") != "Independent-y4p" or not balance.is_finite()
            or balance < Decimal("0.01") or checked.tzinfo is None or age < 0 or age > 1800):
        raise SafetyError("EXPLORATORY_FINANCIAL_PREFLIGHT_INVALID")
    price = billing.get("provider_pricing")
    if not isinstance(price, dict):
        raise SafetyError("EXPLORATORY_TARIFF_PREFLIGHT_REQUIRED")
    try:
        price_time = datetime.fromisoformat(price["verified_utc"].replace("Z", "+00:00"))
        price_age = (datetime.now(timezone.utc) - price_time).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise SafetyError("EXPLORATORY_TARIFF_PREFLIGHT_INVALID") from None
    if (price.get("source_url") != "https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference"
            or price.get("model") != MODEL or price.get("input_usd_per_million") != "0.06"
            or price.get("output_usd_per_million") != "0.24"
            or price.get("published_context_tokens") != 1_048_576
            or price_time.tzinfo is None or price_age < 0 or price_age > 1800):
        raise SafetyError("EXPLORATORY_TARIFF_PREFLIGHT_INVALID")
    off = billing.get("autotopup_status") == "VERIFIED_DISABLED" and billing.get("autotopup_disabled") is True
    exception = billing.get("autotopup_exception")
    accepted = (billing.get("autotopup_status") == "NOT_VERIFIED" and isinstance(exception, dict)
        and exception.get("accepted_by_owner") is True and exception.get("risk_accepted_by_owner") is True
        and exception.get("scope") == SCOPE and exception.get("approval_reference") == approval_reference)
    if not (off or accepted):
        raise SafetyError("EXPLORATORY_AUTOTOPUP_PREFLIGHT_REQUIRED")
    return {"balance_usd": str(balance), "autotopup": "VERIFIED_DISABLED" if off else "NOT_VERIFIED_OWNER_EXCEPTION", "tariff_verified_utc": price_time.isoformat()}


def build_exploratory_live_model(grant_path: str | Path, evidence_root: str | Path):
    grant_path, evidence_root = Path(grant_path).resolve(), Path(evidence_root).resolve()
    try:
        grant = json.loads(grant_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise SafetyError("EXPLORATORY_GRANT_UNREADABLE") from None
    if not isinstance(grant, dict) or _contains_secret_key(grant):
        raise SafetyError("EXPLORATORY_GRANT_INVALID_OR_HAS_SECRET_FIELD")
    if (grant.get("schema") != "ADR_EXPLORATORY_LIVE_NON_B1_GRANT_V1"
            or grant.get("scope") != SCOPE or grant.get("classification") != CLASSIFICATION
            or grant.get("b1_status") != "BLOCKED"):
        raise SafetyError("EXPLORATORY_SCOPE_OR_B1_LABEL_INVALID")
    if grant.get("execution_enabled") is not True or grant.get("human_approved") is not True:
        raise SafetyError("EXPLORATORY_GRANT_NOT_APPROVED")
    if grant.get("candidate_sha256") != candidate_identity()["sha256"]:
        raise SafetyError("EXPLORATORY_CANDIDATE_HASH_MISMATCH")
    plan = (ROOT / PLAN_REL).resolve()
    if not plan.is_relative_to(ROOT) or grant.get("plan_sha256") != hashlib.sha256(plan.read_bytes()).hexdigest():
        raise SafetyError("EXPLORATORY_PLAN_HASH_MISMATCH")
    binding = json.loads((ROOT / "config/PROVIDER_TOKEN_BINDING.json").read_text(encoding="utf-8"))
    if binding.get("verified") is not False:
        raise SafetyError("EXPLORATORY_B1_STATE_NOT_EXPLICITLY_BLOCKED")
    # Each live session gets a fresh, non-reusable evidence store. A previous
    # startup may leave a valid SQLite ledger without any completed request;
    # never reuse that store or overwrite it on a later authorized run.
    expected_sink = (ROOT / "evidence/exploratory_live_non_b1_v2/sessions"
                     / grant["session_id"] / "sink").resolve()
    if evidence_root != expected_sink:
        raise SafetyError("EXPLORATORY_SINK_PATH_INVALID")
    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise SafetyError("EXPLORATORY_SINK_NOT_FRESH")

    raw_limits = grant.get("limits")
    if not isinstance(raw_limits, dict) or raw_limits != LIMIT_VALUES:
        raise SafetyError("EXPLORATORY_LIMITS_NOT_EXACT")
    limits = Limits(**raw_limits).validate()
    approval_reference = grant.get("approval_reference")
    auth = grant.get("authorization")
    if not isinstance(approval_reference, str) or not isinstance(auth, dict):
        raise SafetyError("EXPLORATORY_AUTHORIZATION_REQUIRED")
    if (auth.get("human_approved") is not True or auth.get("execution_enabled") is not True
            or auth.get("scope") != SCOPE or auth.get("classification") != CLASSIFICATION
            or auth.get("b1_status") != "BLOCKED" or auth.get("approval_reference") != approval_reference
            or auth.get("session_id") != grant.get("session_id")):
        raise SafetyError("EXPLORATORY_AUTHORIZATION_INVALID")
    if not isinstance(grant.get("session_id"), str) or len(grant["session_id"]) < 16:
        raise SafetyError("EXPLORATORY_SESSION_INVALID")
    try:
        expiry = datetime.fromisoformat(auth["expires_utc"])
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise SafetyError("EXPLORATORY_AUTHORIZATION_EXPIRED") from None
    auth["config_hash"] = __import__("adr_p1.transport", fromlist=["hashed"]).hashed(raw_limits)
    auth["approval_reference"] = approval_reference
    auth["session_id"] = grant["session_id"]
    auth["billing_preflight"] = grant.get("billing_preflight")
    _check_billing(auth["billing_preflight"], approval_reference)
    if not os.environ.get("NEBIUS_API_KEY"):
        raise SafetyError("CREDENTIAL_UNAVAILABLE")
    evidence_root.mkdir(parents=True, exist_ok=True)
    store = EvidenceStore(evidence_root)
    transport = ApprovalExploratoryTransport(store, grant["session_id"], limits)
    if auth["config_hash"] != transport.config_hash:
        raise SafetyError("EXPLORATORY_CONFIG_HASH_MISMATCH")
    return NebiusApprovalModel.from_transport(transport, auth)
