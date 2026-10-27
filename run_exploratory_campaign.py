"""Campaign entry point. Preparation is offline; real mode requires a fresh grant."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from adr_g64r.common import SafetyError, canonical, digest
from adr_campaign.campaign_runner import (
    CAMPAIGN_ID, CLASSIFICATION, CampaignError, CampaignStore, CampaignLimits,
    canonical, load_frozen_queue, sha256,
)


def canonical_campaign_root():
    return (Path(os.environ.get("LOCALAPPDATA", "C:/Users/Default/AppData/Local"))
            / "Temp" / "ADR_S1_37_PAIR_EXPLORATORY_V1").resolve()


def runtime_manifest():
    ignored = {"__pycache__", "evidence", "revision_backups", ".git"}
    files = {}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        if path.name in {"CAMPAIGN_GRANT.json", "campaign.sqlite3"} or path.suffix not in {".py", ".json", ".jinja", ".txt"}:
            continue
        files[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
    return files


def validate_grant(grant, campaign_store):
    if (grant.get("grant_id") is None or grant.get("human_approved") is not True
            or grant.get("execution_enabled") is not True
            or grant.get("exploratory_b1_deviation") is not True
            or grant.get("scope") != "ADR_S1_37_PAIR_EXPLORATORY"
            or grant.get("campaign_id") != CAMPAIGN_ID
            or grant.get("authorized_lots") != list(range(1, 9))
            or grant.get("campaign_plan_sha256") != campaign_store.plan_sha256
            or grant.get("campaign_config_sha256") != campaign_store.config_sha256
            or grant.get("runtime_sha256") != digest(canonical(runtime_manifest()))
            or grant.get("max_requests_total") != 888
            or grant.get("max_requests_per_episode") != 12
            or grant.get("max_spend_usd") != "5.00"
            or grant.get("max_spend_per_lot_usd") != "0.60"
            or grant.get("max_input_tokens_local_per_request") != 8192
            or grant.get("max_output_tokens_per_request") != 2048
            or grant.get("max_output_tokens_campaign_total") != 1_818_624
            or grant.get("max_total_tokens") != 9_093_120
            or grant.get("request_timeout_ms") != 30_000
            or grant.get("episode_timeout_ms") != 120_000
            or grant.get("lot_timeout_ms") != 10_800_000
            or grant.get("campaign_timeout_ms") != 86_400_000
            or grant.get("max_retries") != 0 or grant.get("concurrency") != 1
            or grant.get("b1_status") != "BLOCKED_PROTOCOL_DEVIATION_EXPLORATORY"
            or grant.get("provider_token_binding_verified") is not False
            or not grant.get("approval_reference")):
        raise CampaignError("CAMPAIGN_GRANT_SCOPE_OR_HASH_MISMATCH")
    try:
        from datetime import datetime, timezone
        expiry = datetime.fromisoformat(grant["expires_utc"])
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc): raise ValueError
    except (KeyError, TypeError, ValueError):
        raise CampaignError("CAMPAIGN_GRANT_EXPIRED") from None
    output = Path(grant["output_dir"]).resolve()
    if output != canonical_campaign_root() or "OneDrive" in str(output):
        raise CampaignError("CAMPAIGN_SINK_MUST_BE_LOCAL_TEMP")
    if grant.get("current_authorized_spend_usd") != "5.00":
        raise CampaignError("CAMPAIGN_AUTHORIZED_BUDGET_MISMATCH")
    return output


def episode_manifest(store, out, run_id, planned_id, lot):
    with store.connection() as db:
        row = db.execute("SELECT payload,sha256 FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None or digest(row[0]) != row[1]:
        raise CampaignError("EPISODE_LEDGER_RECORD_INVALID")
    trace_path = out / "traces" / f"{run_id}.json"
    if not trace_path.is_file() or trace_path.read_bytes() != row[0]:
        raise CampaignError("EPISODE_TRACE_RECORD_INVALID")
    payload = json.loads(row[0])
    metrics = payload["metrics"]
    manifest = {
        "schema": "adr.exploratory_campaign_episode.v1",
        "classification": CLASSIFICATION,
        "b1": "BLOCKED_PROTOCOL_DEVIATION_EXPLORATORY",
        "planned_episode_id": planned_id,
        "pair_id": payload["events"][0]["pair_id"],
        "lot": lot,
        "run_id": run_id,
        "ledger_payload_sha256": row[1],
        "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
        "outcome": {k: metrics.get(k) for k in ("status", "utility", "attacker_success", "requests", "decisions", "execution_started", "tool_successes", "tool_errors")},
        "synthetic": False,
    }
    path = out / "episode_manifests" / f"{planned_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(manifest)
    with path.open("xb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    return path, manifest["outcome"]


def prepare(plan_path):
    queue, lots = load_frozen_queue(plan_path)
    limits = CampaignLimits().validate()
    plan_sha = sha256(Path(plan_path).read_bytes())
    config_sha = sha256(canonical({"limits": __import__("dataclasses").asdict(limits),
                                  "classification": CLASSIFICATION}))
    return {"status": "PREPARED_OFFLINE_NO_GRANT_NO_CREDENTIAL_READ",
            "campaign_id": CAMPAIGN_ID, "classification": CLASSIFICATION,
            "episodes": len(queue), "pairs": len(lots) and sum(len(l["pair_ids"]) for l in lots),
            "lots": lots, "frozen_plan_sha256": plan_sha,
            "campaign_config_sha256": config_sha,
            "max_requests": 888, "max_campaign_usd": "5.00",
            "max_lot_usd": "0.60", "max_input_tokens_local_per_request": 8192,
            "max_output_tokens_per_request": 2048,
            "max_output_tokens_campaign_total": 1_818_624,
            "max_total_tokens": 9_093_120,
            "request_timeout_ms": 30_000, "episode_timeout_ms": 120_000,
            "lot_timeout_ms": 10_800_000, "campaign_timeout_ms": 86_400_000,
            "max_retries": 0, "concurrency": 1,
            "reserve_usd_per_request": "0.00120",
            "b1": "BLOCKED", "provider_calls": 0}


def execute_next_lot(grant_path):
    grant = json.loads(Path(grant_path).read_text(encoding="utf-8"))
    plan_path = ROOT / "freeze_reference" / "PLAN_78_EPISODIOS_V1.json"
    output = Path(grant.get("output_dir", "")).resolve()
    if output != canonical_campaign_root() or "OneDrive" in str(output):
        raise CampaignError("CAMPAIGN_SINK_MUST_BE_LOCAL_TEMP")
    campaign_db = output / "campaign_state.sqlite3"
    if output.exists() and not campaign_db.exists():
        raise CampaignError("CAMPAIGN_STATE_MISSING_BUT_SINK_EXISTS")
    campaign = CampaignStore(campaign_db, plan_path)
    output = validate_grant(grant, campaign)
    if grant.get("session_id") != CAMPAIGN_ID:
        raise CampaignError("CAMPAIGN_SESSION_MISMATCH")
    snap = campaign.snapshot()
    grant_lot = snap["active_lot"]
    if grant_lot not in grant["authorized_lots"] or not 1 <= grant_lot <= 8:
        raise CampaignError("GRANT_ACTIVE_LOT_MISMATCH")

    # Grant validation precedes credential presence check; never reveal its value.
    if not os.environ.get("NEBIUS_API_KEY"):
        raise CampaignError("NEBIUS_API_KEY_NOT_CONFIGURED")
    from adr_gateb.import_boundary import install
    install()
    from adr_gateb.design import Design
    from adr_gateb.candidate_s1 import CandidateS1
    from adr_gateb.evidence import Store
    from adr_gateb.runner import Runner
    from adr_live.model import NebiusModel
    from adr_p1.campaign_transport import CampaignTransport

    evidence_root = output / "evidence"
    evidence_store = Store(evidence_root)
    if evidence_store.interrupted():
        campaign.stop("EVIDENCE_STORE_HAS_UNSEALED_RUN")
        raise CampaignError("EVIDENCE_STORE_HAS_UNSEALED_RUN")
    existing = evidence_store.recover() if not (evidence_root / "runs.csv").exists() else evidence_store.verify()
    design = Design(ROOT / "freeze_reference")
    s1 = CandidateS1(design)
    transport = CampaignTransport(evidence_store, campaign, grant["session_id"], grant)
    runner = Runner(design, s1, evidence_store)
    finished = []
    while (episode := campaign.next_episode()) is not None:
        planned = episode["planned_episode_id"]
        seq = episode["seq"]
        run_id = f"adrx-l{grant_lot}-e{seq:03d}"
        case_auth = {**grant, "planned_case_id": planned}
        campaign.start_episode(planned)
        model = NebiusModel(transport, case_auth)
        episode_start_ns = time.monotonic_ns()
        result = runner.run(planned, run_id, model)
        actual_ms = max(0, (time.monotonic_ns() - episode_start_ns) // 1_000_000)
        evidence_store.verify()
        if result["error"]:
            campaign.stop("EPISODE_RUNNER_ERROR")
            break
        manifest_path, outcome = episode_manifest(evidence_store, evidence_root, run_id, planned, grant_lot)
        with evidence_store.connection() as db:
            raw, = db.execute("SELECT payload FROM runs WHERE run_id=?", (run_id,)).fetchone()
        payload = json.loads(raw)
        campaign.finish_episode(planned, elapsed_ms=actual_ms,
            evidence_manifest=manifest_path, attribution=CLASSIFICATION,
            outcome=outcome,
            valid=(payload["classification"] == CLASSIFICATION
                   and payload["metrics"]["status"] == "VALID_REAL_EXPLORATORY_NOT_PILOT"))
        finished.append(planned)
    if campaign.snapshot()["status"] == "STOPPED":
        return {"status": "STOPPED", "finished_in_this_lot": finished,
                "campaign": campaign.snapshot(), "evidence_verification": existing}
    checkpoint = campaign.checkpoint_lot()
    return {"status": "LOT_CHECKPOINTED", "checkpoint": checkpoint,
            "finished_in_this_lot": finished,
            "campaign": campaign.snapshot(), "evidence_verification": evidence_store.verify(),
            "classification": CLASSIFICATION, "b1": "BLOCKED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true", help="Offline; does not read grants or credentials")
    parser.add_argument("--run-next-lot", action="store_true", help="Requires a fresh, explicit campaign grant")
    parser.add_argument("--grant", help="Path to a separately approved campaign grant")
    args = parser.parse_args()
    if args.prepare_only or not args.run_next_lot:
        print(json.dumps(prepare(ROOT / "freeze_reference" / "PLAN_78_EPISODIOS_V1.json"), sort_keys=True))
        return 0
    if not args.grant:
        raise CampaignError("CAMPAIGN_GRANT_REQUIRED")
    result = execute_next_lot(args.grant)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "LOT_CHECKPOINTED" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        code = str(exc) if isinstance(exc, (CampaignError, SafetyError)) else "UNEXPECTED_ERROR"
        print(json.dumps({"status": "STOPPED", "error_code": code,
                          "error_type": type(exc).__name__, "credential_value_read": False}, sort_keys=True))
        sys.exit(2)
