"""Fail-closed composition for a separately authorized live approval demo."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from adr_g64r.common import SafetyError, canonical, digest
from adr_g64r.storage import EvidenceStore
from adr_p1.transport import Limits, MODEL, Transport

from .model_port import NebiusApprovalModel


ROOT = Path(__file__).resolve().parents[1]
BOUND_FILES = (
    "adr_approval/model_port.py", "adr_approval/workflow.py", "adr_approval/service.py",
    "adr_approval/server.py", "adr_approval/live_runtime.py", "run_approval_live.py",
    "adr_live/model.py", "adr_p1/transport.py", "wire_worker.py",
    "adr_gateb/design.py", "adr_gateb/policy.py", "freeze_reference/MANIFEST_SHA256.json",
)


def candidate_identity(root: Path = ROOT) -> dict:
    files = {}
    for relative in BOUND_FILES:
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise SafetyError("LIVE_CANDIDATE_FILE_MISSING")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": files, "sha256": digest(canonical(files))}


def build_live_model(grant_path: str | Path, evidence_root: str | Path):
    """Construct the live model only from a new approved, hash-bound grant.

    Provider-binding proof is required before a request can be made. The current
    candidate intentionally remains blocked while B1 is unresolved.
    """
    grant_path = Path(grant_path).resolve()
    evidence_root = Path(evidence_root).resolve()
    try:
        grant = json.loads(grant_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise SafetyError("LIVE_GRANT_UNREADABLE") from None
    if not isinstance(grant, dict) or any(str(k).lower() in {"api_key", "apikey", "token", "secret", "credential"} for k in grant):
        raise SafetyError("LIVE_GRANT_INVALID_OR_CONTAINS_SECRET")
    if grant.get("execution_enabled") is not True or grant.get("human_approved") is not True:
        raise SafetyError("LIVE_GRANT_NOT_APPROVED")
    if grant.get("scope") != "ADR_HUMAN_APPROVAL_DEMO" or grant.get("b1_status") != "VERIFIED":
        raise SafetyError("LIVE_SCOPE_OR_B1_NOT_VERIFIED")
    if grant.get("candidate_sha256") != candidate_identity()["sha256"]:
        raise SafetyError("LIVE_CANDIDATE_HASH_MISMATCH")
    binding = json.loads((ROOT / "config/PROVIDER_TOKEN_BINDING.json").read_text(encoding="utf-8"))
    if binding.get("verified") is not True:
        raise SafetyError("PROVIDER_TOKEN_BINDING_UNVERIFIED_B1_BLOCKED")
    if not os.environ.get("NEBIUS_API_KEY"):
        raise SafetyError("CREDENTIAL_UNAVAILABLE")

    raw_limits = grant.get("limits")
    if not isinstance(raw_limits, dict):
        raise SafetyError("LIVE_LIMITS_REQUIRED")
    allowed = set(Limits.__dataclass_fields__)
    if set(raw_limits) != allowed:
        raise SafetyError("LIVE_LIMIT_FIELDS_INVALID")
    try:
        limits = Limits(**raw_limits).validate()
        budget = Decimal(limits.budget_usd)
    except (TypeError, ValueError, InvalidOperation):
        raise SafetyError("LIVE_LIMITS_INVALID") from None
    if (limits.model != MODEL or limits.max_requests > 6 or limits.max_output_tokens > 1024
            or limits.max_input_tokens > 8192 or limits.max_call_ms > 30_000
            or limits.max_total_ms > 240_000 or limits.max_retries != 0 or budget > Decimal("0.01")):
        raise SafetyError("LIVE_LIMITS_EXCEED_PROPOSED_AUTHORIZATION")
    if limits.max_requests < 1 or limits.max_total_tokens < 1 or limits.max_input_tokens < 1 or limits.max_output_tokens < 1:
        raise SafetyError("LIVE_LIMITS_ZERO")

    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise SafetyError("LIVE_EVIDENCE_ROOT_MUST_BE_FRESH")
    evidence_root.mkdir(parents=True, exist_ok=True)
    session = grant.get("session_id")
    auth = grant.get("authorization")
    if not isinstance(session, str) or not isinstance(auth, dict) or auth.get("session_id") != session:
        raise SafetyError("LIVE_AUTHORIZATION_INVALID")
    try:
        expires = datetime.fromisoformat(auth["expires_utc"])
        auth_time_valid = expires.tzinfo is not None and expires > datetime.now(timezone.utc)
    except (KeyError, TypeError, ValueError):
        auth_time_valid = False
    if (auth.get("human_approved") is not True or auth.get("scope") != "ADR_S1_MVP"
            or not auth_time_valid or not isinstance(auth.get("config_hash"), str)):
        raise SafetyError("LIVE_AUTHORIZATION_INVALID")
    if auth.get("approval_reference") != grant.get("approval_reference"):
        raise SafetyError("LIVE_AUTHORIZATION_REFERENCE_MISMATCH")
    store = EvidenceStore(evidence_root)
    transport = Transport(store, session, limits)
    if auth.get("config_hash") != transport.config_hash:
        raise SafetyError("LIVE_CONFIG_HASH_MISMATCH")
    return NebiusApprovalModel.from_transport(transport, auth)
