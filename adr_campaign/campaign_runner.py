"""Offline-first, durable controller for the 37-pair ADR exploratory queue.

This module contains no Nebius client and makes no network calls. A future
integration must pass the per-request lease returned by CampaignStore before
any wire operation and must persist the episode evidence before marking it
complete. Limits are local guards, not provider billing guarantees. The local
8,192-token input estimate does not resolve B1 or certify serving tokenization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Callable, Iterable


CAMPAIGN_ID = "ADR_S1_37_PAIR_EXPLORATORY_V1"
CLASSIFICATION = "REAL_EXPLORATORY_B1_DEVIATION_NOT_PILOT"
PRICE_SOURCE = "https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference"
EXCLUDED_PAIR_IDS = {"MVP1_PAIR_03", "MVP1_PAIR_04"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


class CampaignError(RuntimeError):
    """Fail-closed campaign validation error with a stable, non-secret code."""


def check_budget(current_estimate: Decimal, held_reservations: Decimal,
                 next_reservation: Decimal, cap: Decimal, stop_code: str) -> None:
    """Use money decimals and count outstanding reservations once."""
    if current_estimate + held_reservations + next_reservation > cap:
        raise CampaignError(stop_code)


def check_ceiling(current: int, increment: int, cap: int, stop_code: str) -> None:
    if any(type(v) is not int or v < 0 for v in (current, increment, cap)) or current + increment > cap:
        raise CampaignError(stop_code)


@dataclass(frozen=True)
class CampaignLimits:
    max_requests: int = 888
    max_spend_usd: str = "5.00"
    max_lot_spend_usd: str = "0.60"
    max_requests_per_episode: int = 12
    max_input_tokens_per_request: int = 8192  # local estimate only; B1 remains blocked
    max_output_tokens_per_request: int = 2048
    max_total_output_tokens: int = 1_818_624
    max_total_tokens: int = 9_093_120
    max_call_ms: int = 30_000
    max_episode_ms: int = 120_000
    max_lot_ms: int = 10_800_000
    max_campaign_ms: int = 86_400_000
    max_retries: int = 0
    concurrency: int = 1
    # Conservative local reservation including output and tax headroom.
    reserve_usd_per_request: str = "0.00120"
    input_usd_per_million: str = "0.06"
    output_usd_per_million: str = "0.24"
    tax_multiplier: str = "1.21"

    def validate(self) -> "CampaignLimits":
        if (self.max_requests != 888 or self.max_requests_per_episode != 12
                or self.max_input_tokens_per_request != 8192
                or self.max_output_tokens_per_request != 2048
                or self.max_total_output_tokens != 1_818_624
                or self.max_total_tokens != 9_093_120
                or self.max_call_ms != 30_000 or self.max_episode_ms != 120_000
                or self.max_lot_ms != 10_800_000 or self.max_campaign_ms != 86_400_000
                or self.max_retries != 0 or self.concurrency != 1):
            raise CampaignError("CAMPAIGN_LIMIT_DRIFT")
        for value in (self.max_spend_usd, self.max_lot_spend_usd,
                      self.reserve_usd_per_request, self.input_usd_per_million,
                      self.output_usd_per_million, self.tax_multiplier):
            try:
                parsed = Decimal(value)
            except Exception:
                raise CampaignError("INVALID_CAMPAIGN_MONEY") from None
            if not parsed.is_finite() or parsed <= 0:
                raise CampaignError("INVALID_CAMPAIGN_MONEY")
        if Decimal(self.max_spend_usd) != Decimal("5.00") or Decimal(self.max_lot_spend_usd) != Decimal("0.60"):
            raise CampaignError("CAMPAIGN_BUDGET_DRIFT")
        if (Decimal(self.reserve_usd_per_request) != Decimal("0.00120")
                or Decimal(self.input_usd_per_million) != Decimal("0.06")
                or Decimal(self.output_usd_per_million) != Decimal("0.24")
                or Decimal(self.tax_multiplier) != Decimal("1.21")):
            raise CampaignError("CAMPAIGN_RESERVATION_OR_PRICE_DRIFT")
        return self


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_frozen_queue(plan_path: str | Path) -> tuple[list[dict], list[dict]]:
    """Read frozen episode order; exclude completed exploratory pairs 03/04."""
    try:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        episodes = plan["episodes"]
    except (OSError, ValueError, KeyError, TypeError):
        raise CampaignError("FROZEN_PLAN_UNREADABLE") from None
    if plan.get("classification") != "FROZEN_PLAN_NOT_EXPERIMENTAL_RESULTS":
        raise CampaignError("FROZEN_PLAN_CLASSIFICATION_MISMATCH")
    ordered = sorted(episodes, key=lambda row: row["sequence"])
    pending = [dict(row) for row in ordered if row.get("pair_id") not in EXCLUDED_PAIR_IDS]
    pairs: dict[str, list[dict]] = {}
    for row in pending:
        pairs.setdefault(row["pair_id"], []).append(row)
    if len(pairs) != 37 or len(pending) != 74:
        raise CampaignError("FROZEN_QUEUE_COUNT_MISMATCH")
    for pair_id, rows in pairs.items():
        ids = {row["planned_episode_id"] for row in rows}
        if len(rows) != 2 or len(ids) != 2 or not any(x.startswith("MVP1_A_") for x in ids) or not any(x.startswith("MVP1_G_") for x in ids):
            raise CampaignError("FROZEN_PAIR_MEMBERSHIP_MISMATCH")
        if pair_id in EXCLUDED_PAIR_IDS:
            raise CampaignError("COMPLETED_PAIR_IN_PENDING_QUEUE")
    pair_order = []
    seen = set()
    for row in pending:
        if row["pair_id"] not in seen:
            seen.add(row["pair_id"])
            pair_order.append(row["pair_id"])
    if [len(pair_order[i:i + 5]) for i in range(0, len(pair_order), 5)] != [5, 5, 5, 5, 5, 5, 5, 2]:
        raise CampaignError("FROZEN_LOT_SHAPE_MISMATCH")
    queue, lots = [], []
    for lot_no, start in enumerate(range(0, len(pair_order), 5), 1):
        lot_pairs = pair_order[start:start + 5]
        lot_items = [row for row in pending if row["pair_id"] in lot_pairs]
        for row in lot_items:
            row["lot"] = lot_no
            row["classification"] = CLASSIFICATION
            row["sequence_in_campaign"] = len(queue) + 1
            queue.append(row)
        lots.append({"lot": lot_no, "pair_ids": lot_pairs,
                     "episode_ids": [row["planned_episode_id"] for row in lot_items],
                     "max_requests": len(lot_items) * 12,
                     "max_reserved_usd": str((Decimal("0.00120") * len(lot_items) * 12).quantize(Decimal("0.00000001")))})
    # The frozen sequence within each pair is retained verbatim (A/G or G/A).
    return queue, lots


class CampaignStore:
    """SQLite durable cursor, request/cost counters and tamper-evident events."""
    def __init__(self, path: str | Path, plan_path: str | Path,
                 limits: CampaignLimits | None = None, *, now_ns: Callable[[], int] = time.time_ns,
                 classification: str = CLASSIFICATION):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.limits = (limits or CampaignLimits()).validate()
        self.now_ns = now_ns
        if classification not in (CLASSIFICATION, "OFFLINE_SYNTHETIC_TEST_ONLY"):
            raise CampaignError("CAMPAIGN_CLASSIFICATION_INVALID")
        self.classification = classification
        self.queue, self.lots = load_frozen_queue(plan_path)
        self.plan_sha256 = sha256(Path(plan_path).read_bytes())
        self.config_sha256 = sha256(canonical({"limits": asdict(self.limits), "classification": self.classification}))
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None,
                             factory=_ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _initialize(self):
        existed = self.path.exists() and self.path.stat().st_size > 0
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS campaign(
                    id TEXT PRIMARY KEY, plan_sha TEXT NOT NULL, config_sha TEXT NOT NULL,
                    status TEXT NOT NULL, active_lot INTEGER NOT NULL,
                    started_ns INTEGER NOT NULL, last_clock_ns INTEGER NOT NULL,
                    stopped_reason TEXT);
                CREATE TABLE IF NOT EXISTS episodes(
                    planned_id TEXT PRIMARY KEY, pair_id TEXT NOT NULL, lot INTEGER NOT NULL,
                    seq INTEGER NOT NULL UNIQUE, status TEXT NOT NULL,
                    started_ns INTEGER, finished_ns INTEGER, evidence_path TEXT,
                    evidence_sha TEXT, attribution TEXT, outcome_sha TEXT);
                CREATE TABLE IF NOT EXISTS requests(
                    request_id TEXT PRIMARY KEY, planned_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, status TEXT NOT NULL,
                    local_input_tokens INTEGER NOT NULL, reserved_tokens INTEGER NOT NULL,
                    reserve_usd TEXT NOT NULL, started_ns INTEGER NOT NULL,
                    finished_ns INTEGER, provider_input_tokens INTEGER,
                    output_tokens INTEGER, elapsed_ms INTEGER, observed_cost_usd TEXT,
                    response_sha TEXT, UNIQUE(planned_id, ordinal),
                    FOREIGN KEY(planned_id) REFERENCES episodes(planned_id));
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY, body BLOB NOT NULL,
                    prev_sha TEXT NOT NULL, event_sha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lot_checkpoints(
                    lot INTEGER PRIMARY KEY, status TEXT NOT NULL,
                    completed_episodes INTEGER NOT NULL, requests INTEGER NOT NULL,
                    tokens INTEGER NOT NULL, cost_usd TEXT NOT NULL,
                    evidence_sha TEXT NOT NULL, completed_ns INTEGER NOT NULL);
            """)
            row = db.execute("SELECT * FROM campaign WHERE id=?", (CAMPAIGN_ID,)).fetchone()
            if row is None:
                if existed:
                    raise CampaignError("UNRECOGNIZED_OR_AMBIGUOUS_CAMPAIGN_DB")
                now = self.now_ns()
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO campaign VALUES (?,?,?,?,?,?,?,NULL)",
                           (CAMPAIGN_ID, self.plan_sha256, self.config_sha256, "READY", 1, now, now))
                for e in self.queue:
                    db.execute("INSERT INTO episodes VALUES (?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,NULL)",
                               (e["planned_episode_id"], e["pair_id"], e["lot"], e["sequence_in_campaign"], "PENDING"))
                db.commit()
                self._event("CAMPAIGN_CREATED", plan_sha256=self.plan_sha256,
                            config_sha256=self.config_sha256, queue_sha256=sha256(canonical(self.queue)))
                return
            if row["plan_sha"] != self.plan_sha256 or row["config_sha"] != self.config_sha256:
                raise CampaignError("CAMPAIGN_PLAN_OR_CONFIG_DRIFT")
            self.verify()
            now = self.now_ns()
            if now < row["last_clock_ns"]:
                self.stop("CLOCK_ROLLBACK")
                raise CampaignError("CLOCK_ROLLBACK")
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                active_req = db.execute("SELECT request_id FROM requests WHERE status='STARTED'").fetchone()
                active_ep = db.execute("SELECT planned_id FROM episodes WHERE status='STARTED'").fetchone()
                if active_req or active_ep:
                    unknown_requests = [r[0] for r in db.execute("SELECT request_id FROM requests WHERE status='STARTED'")]
                    unknown_episodes = [r[0] for r in db.execute("SELECT planned_id FROM episodes WHERE status='STARTED'")]
                    db.execute("UPDATE requests SET status='UNKNOWN_AFTER_INTERRUPTION' WHERE status='STARTED'")
                    db.execute("UPDATE episodes SET status='UNKNOWN_AFTER_INTERRUPTION' WHERE status='STARTED'")
                    db.execute("UPDATE campaign SET status='STOPPED', stopped_reason='AMBIGUOUS_INTERRUPTION', last_clock_ns=? WHERE id=?", (now, CAMPAIGN_ID))
                    db.commit()
                    for request_id in unknown_requests:
                        self._event("REQUEST_INTERRUPTED_UNKNOWN", request_id=request_id)
                    for planned_id in unknown_episodes:
                        self._event("EPISODE_INTERRUPTED_UNKNOWN", planned_episode_id=planned_id)
                    self._event("CAMPAIGN_STOPPED", reason="AMBIGUOUS_INTERRUPTION")
                    raise CampaignError("AMBIGUOUS_INTERRUPTION_FAIL_CLOSED")
                db.execute("UPDATE campaign SET last_clock_ns=? WHERE id=?", (now, CAMPAIGN_ID))
                db.commit()
            self._check_elapsed()

    def _event(self, name: str, **fields):
        body = canonical({"campaign_id": CAMPAIGN_ID, "event": name,
                          "timestamp_ns": self.now_ns(), **fields})
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            last = db.execute("SELECT event_sha FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            prev = last[0] if last else "0" * 64
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events").fetchone()[0]
            digest = sha256(prev.encode() + body)
            db.execute("INSERT INTO events VALUES (?,?,?,?)", (seq, body, prev, digest))
            db.commit()

    def verify(self) -> dict:
        with self._connect() as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CampaignError("CAMPAIGN_DATABASE_CORRUPTION")
            prev = "0" * 64
            event_objects = []
            for row in db.execute("SELECT seq,body,prev_sha,event_sha FROM events ORDER BY seq"):
                if row["prev_sha"] != prev or sha256(prev.encode() + row["body"]) != row["event_sha"]:
                    raise CampaignError("CAMPAIGN_EVENT_CHAIN_INTEGRITY")
                prev = row["event_sha"]
                try: event_objects.append(json.loads(row["body"]))
                except (ValueError, UnicodeError): raise CampaignError("CAMPAIGN_EVENT_ENCODING") from None
            campaign = db.execute("SELECT * FROM campaign WHERE id=?", (CAMPAIGN_ID,)).fetchone()
            if campaign is None or campaign["plan_sha"] != self.plan_sha256 or campaign["config_sha"] != self.config_sha256:
                raise CampaignError("CAMPAIGN_HEADER_INTEGRITY")
            actual = db.execute("SELECT COUNT(*) n FROM episodes").fetchone()["n"]
            if actual != 74:
                raise CampaignError("CAMPAIGN_QUEUE_INTEGRITY")
            expected_queue = [(r["planned_episode_id"], r["pair_id"], r["lot"], r["sequence_in_campaign"]) for r in self.queue]
            actual_queue = [(r["planned_id"], r["pair_id"], r["lot"], r["seq"]) for r in db.execute("SELECT planned_id,pair_id,lot,seq FROM episodes ORDER BY seq")]
            if actual_queue != expected_queue:
                raise CampaignError("CAMPAIGN_FROZEN_ORDER_OR_ATTRIBUTION_DRIFT")
            request_rows = db.execute("SELECT * FROM requests ORDER BY planned_id,ordinal").fetchall()
            if len(request_rows) > self.limits.max_requests:
                raise CampaignError("CAMPAIGN_REQUEST_LIMIT_INTEGRITY")
            if sum(r["reserved_tokens"] for r in request_rows) > self.limits.max_total_tokens:
                raise CampaignError("CAMPAIGN_TOKEN_LIMIT_INTEGRITY")
            output_tokens_reserved = sum(
                r["output_tokens"] if r["output_tokens"] is not None
                else self.limits.max_output_tokens_per_request
                for r in request_rows)
            if output_tokens_reserved > self.limits.max_total_output_tokens:
                raise CampaignError("CAMPAIGN_OUTPUT_TOKEN_LIMIT_INTEGRITY")
            episode_counts, lot_costs = {}, {}
            total_spent = Decimal(0); total_held = Decimal(0)
            for req in request_rows:
                episode_counts[req["planned_id"]] = episode_counts.get(req["planned_id"], 0) + 1
                if (req["ordinal"] != episode_counts[req["planned_id"]]
                        or req["ordinal"] > self.limits.max_requests_per_episode
                        or req["local_input_tokens"] > self.limits.max_input_tokens_per_request
                        or req["reserved_tokens"] != self.limits.max_input_tokens_per_request + self.limits.max_output_tokens_per_request
                        or Decimal(req["reserve_usd"]) != Decimal(self.limits.reserve_usd_per_request)):
                    raise CampaignError("CAMPAIGN_REQUEST_LIMIT_INTEGRITY")
                if req["observed_cost_usd"] is not None:
                    total_spent += Decimal(req["observed_cost_usd"])
                    lot_no = next(e["lot"] for e in self.queue if e["planned_episode_id"] == req["planned_id"])
                    lot_costs[lot_no] = lot_costs.get(lot_no, Decimal(0)) + Decimal(req["observed_cost_usd"])
                if req["status"] in ("STARTED", "UNKNOWN_AFTER_INTERRUPTION", "UNKNOWN_USAGE"):
                    total_held += Decimal(req["reserve_usd"])
                    lot_no = next(e["lot"] for e in self.queue if e["planned_episode_id"] == req["planned_id"])
                    lot_costs[lot_no] = lot_costs.get(lot_no, Decimal(0)) + Decimal(req["reserve_usd"])
            over_budget = (total_spent + total_held > Decimal(self.limits.max_spend_usd)
                           or any(cost > Decimal(self.limits.max_lot_spend_usd) for cost in lot_costs.values()))
            if over_budget and not (campaign["status"] == "STOPPED"
                                    and campaign["stopped_reason"] in ("REQUEST_COST_RESERVE_BREACH", "OBSERVED_REQUEST_LIMIT_BREACH")):
                raise CampaignError("CAMPAIGN_BUDGET_INTEGRITY")
            for ep in db.execute("SELECT planned_id,evidence_path,evidence_sha FROM episodes WHERE status='COMPLETE'"):
                if not ep["evidence_path"] or not ep["evidence_sha"]:
                    raise CampaignError("EPISODE_EVIDENCE_REFERENCE_MISSING")
                path = (self.path.parent / ep["evidence_path"]).resolve()
                if not path.is_relative_to(self.path.parent) or not path.is_file() or sha256(path.read_bytes()) != ep["evidence_sha"]:
                    raise CampaignError("EPISODE_EVIDENCE_INTEGRITY")
            by_type = {}
            for e in event_objects:
                by_type.setdefault(e.get("event"), []).append(e)
            reserved_events = {e.get("request_id"): e for e in by_type.get("REQUEST_RESERVED", [])}
            completed_events = {e.get("request_id"): e for e in by_type.get("REQUEST_COMPLETE", [])}
            interrupted_request_events = {e.get("request_id") for e in by_type.get("REQUEST_INTERRUPTED_UNKNOWN", [])}
            episode_started_events = {e.get("planned_episode_id") for e in by_type.get("EPISODE_STARTED", [])}
            episode_completed_events = {e.get("planned_episode_id"): e for e in by_type.get("EPISODE_COMPLETE", [])}
            episode_unknown_events = {e.get("planned_episode_id") for e in by_type.get("EPISODE_INTERRUPTED_UNKNOWN", [])}
            for req in db.execute("SELECT * FROM requests"):
                reservation = reserved_events.get(req["request_id"])
                if (reservation is None or reservation.get("planned_episode_id") != req["planned_id"]
                        or reservation.get("ordinal") != req["ordinal"]
                        or reservation.get("local_input_tokens") != req["local_input_tokens"]
                        or reservation.get("reserved_tokens") != req["reserved_tokens"]
                        or reservation.get("reserve_usd") != req["reserve_usd"]):
                    raise CampaignError("CAMPAIGN_REQUEST_EVENT_MISMATCH")
                completed = completed_events.get(req["request_id"])
                if req["status"] == "COMPLETE":
                    if (completed is None or completed.get("provider_input_tokens") != req["provider_input_tokens"]
                            or completed.get("output_tokens") != req["output_tokens"]
                            or completed.get("elapsed_ms") != req["elapsed_ms"]
                            or completed.get("response_sha256") != req["response_sha"]):
                        raise CampaignError("CAMPAIGN_REQUEST_RESULT_EVENT_MISMATCH")
                elif req["status"] == "UNKNOWN_AFTER_INTERRUPTION" and req["request_id"] not in interrupted_request_events:
                    raise CampaignError("CAMPAIGN_REQUEST_INTERRUPTION_EVENT_MISSING")
                elif req["status"] in ("LIMIT_BREACH", "COST_RESERVE_BREACH"):
                    expected_reason = "OBSERVED_REQUEST_LIMIT_BREACH" if req["status"] == "LIMIT_BREACH" else "REQUEST_COST_RESERVE_BREACH"
                    if not any(e.get("request_id") == req["request_id"] and e.get("reason") == expected_reason
                               for e in by_type.get("CAMPAIGN_STOPPED", [])):
                        raise CampaignError("CAMPAIGN_REQUEST_LIMIT_EVENT_MISSING")
            for ep in db.execute("SELECT * FROM episodes"):
                pid = ep["planned_id"]
                if ep["status"] in ("STARTED", "COMPLETE", "ERROR_STOPPED", "UNKNOWN_AFTER_INTERRUPTION") and pid not in episode_started_events:
                    raise CampaignError("CAMPAIGN_EPISODE_START_EVENT_MISSING")
                if ep["status"] == "COMPLETE":
                    complete = episode_completed_events.get(pid)
                    if (complete is None or complete.get("evidence_sha256") != ep["evidence_sha"]
                            or complete.get("outcome_sha256") != ep["outcome_sha"]
                            or complete.get("attribution") != ep["attribution"]):
                        raise CampaignError("CAMPAIGN_EPISODE_RESULT_EVENT_MISMATCH")
                if ep["status"] == "UNKNOWN_AFTER_INTERRUPTION" and pid not in episode_unknown_events:
                    raise CampaignError("CAMPAIGN_EPISODE_INTERRUPTION_EVENT_MISSING")
            for checkpoint in db.execute("SELECT lot,evidence_sha FROM lot_checkpoints"):
                if not any(e.get("lot") == checkpoint["lot"] and e.get("evidence_sha256") == checkpoint["evidence_sha"]
                           for e in by_type.get("LOT_CHECKPOINT_VERIFIED", [])):
                    raise CampaignError("CAMPAIGN_CHECKPOINT_EVENT_MISMATCH")
        return {"status": "VERIFIED", "event_count": seq if "seq" in locals() else 0,
                "queue_episodes": actual, "plan_sha256": self.plan_sha256,
                "config_sha256": self.config_sha256}

    def _check_elapsed(self):
        now = self.now_ns()
        with self._connect() as db:
            row = db.execute("SELECT started_ns,last_clock_ns,active_lot,status,stopped_reason FROM campaign WHERE id=?", (CAMPAIGN_ID,)).fetchone()
            if now < row["last_clock_ns"]:
                self.stop("CLOCK_ROLLBACK")
                raise CampaignError("CLOCK_ROLLBACK")
            elapsed = (now - row["started_ns"]) // 1_000_000
            lot_row = db.execute("SELECT MIN(started_ns) FROM episodes WHERE lot=? AND started_ns IS NOT NULL", (row["active_lot"],)).fetchone()
            lot_elapsed = 0 if lot_row[0] is None else (now - lot_row[0]) // 1_000_000
            if row["stopped_reason"] or row["status"] == "STOPPED":
                raise CampaignError("CAMPAIGN_STOPPED")
            if elapsed >= self.limits.max_campaign_ms:
                self.stop("CAMPAIGN_TIME_LIMIT"); raise CampaignError("CAMPAIGN_TIME_LIMIT")
            if lot_elapsed >= self.limits.max_lot_ms:
                self.stop("LOT_TIME_LIMIT"); raise CampaignError("LOT_TIME_LIMIT")
            db.execute("UPDATE campaign SET last_clock_ns=? WHERE id=?", (now, CAMPAIGN_ID))

    def snapshot(self) -> dict:
        self.verify()
        with self._connect() as db:
            row = db.execute("SELECT * FROM campaign WHERE id=?", (CAMPAIGN_ID,)).fetchone()
            request_rows = db.execute("SELECT reserved_tokens,reserve_usd,observed_cost_usd,status FROM requests").fetchall()
            states = {r["status"]: r["n"] for r in db.execute("SELECT status,COUNT(*) n FROM episodes GROUP BY status")}
        spent = sum((Decimal(r["observed_cost_usd"]) for r in request_rows if r["observed_cost_usd"] is not None), Decimal(0))
        reserved = sum((Decimal(r["reserve_usd"]) for r in request_rows if r["status"] in ("STARTED", "UNKNOWN_AFTER_INTERRUPTION", "UNKNOWN_USAGE")), Decimal(0))
        return {"status": row["status"], "active_lot": row["active_lot"],
                "requests": len(request_rows), "reserved_tokens": sum(r["reserved_tokens"] for r in request_rows),
                "observed_cost_usd": f"{spent:.8f}",
                "held_reservations_usd": f"{Decimal(str(reserved)):.8f}",
                "episode_states": states, "classification": self.classification}

    def active_lot(self) -> int:
        with self._connect() as db:
            row = db.execute("SELECT active_lot FROM campaign WHERE id=?", (CAMPAIGN_ID,)).fetchone()
        if row is None:
            raise CampaignError("CAMPAIGN_HEADER_MISSING")
        return row[0]

    def request_snapshot(self, planned_id: str) -> list[tuple]:
        with self._connect() as db:
            return [tuple(row) for row in db.execute(
                "SELECT request_id,status,reserved_tokens,reserve_usd,provider_input_tokens,output_tokens,observed_cost_usd "
                ",response_sha "
                "FROM requests WHERE planned_id=? ORDER BY ordinal", (planned_id,))]

    def episode_for_run(self, run_id: str) -> str | None:
        # Runner IDs are campaign-scoped and generated as campaign-<seq>.
        match = re.fullmatch(r"adrx-l\d+-e(\d{3})", run_id)
        if not match:
            return None
        seq = int(match.group(1))
        with self._connect() as db:
            row = db.execute("SELECT planned_id FROM episodes WHERE seq=?", (seq,)).fetchone()
        return row[0] if row else None

    def next_episode(self) -> dict | None:
        self._check_elapsed()
        with self._connect() as db:
            c = db.execute("SELECT active_lot,status FROM campaign WHERE id=?", (CAMPAIGN_ID,)).fetchone()
            if c["status"] not in ("READY", "RUNNING"):
                raise CampaignError("CAMPAIGN_NOT_RUNNABLE")
            row = db.execute("SELECT * FROM episodes WHERE lot=? AND status='PENDING' ORDER BY seq LIMIT 1", (c["active_lot"],)).fetchone()
            if row is None:
                return None
            earlier = db.execute("SELECT 1 FROM episodes WHERE seq<? AND status!='COMPLETE' LIMIT 1", (row["seq"],)).fetchone()
            if earlier:
                raise CampaignError("QUEUE_ORDER_OR_PRIOR_STATE_INVALID")
            result = dict(row)
            result["planned_episode_id"] = result["planned_id"]
            return result

    def start_episode(self, planned_id: str) -> None:
        self._check_elapsed()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM episodes WHERE planned_id=?", (planned_id,)).fetchone()
            nxt = db.execute("SELECT planned_id FROM episodes WHERE lot=(SELECT active_lot FROM campaign WHERE id=?) AND status='PENDING' ORDER BY seq LIMIT 1", (CAMPAIGN_ID,)).fetchone()
            if row is None or row["status"] != "PENDING" or nxt is None or nxt[0] != planned_id:
                db.rollback(); self.stop("EPISODE_ORDER_OR_DUPLICATE"); raise CampaignError("EPISODE_ORDER_OR_DUPLICATE")
            now = self.now_ns()
            db.execute("UPDATE episodes SET status='STARTED',started_ns=? WHERE planned_id=?", (now, planned_id))
            db.execute("UPDATE campaign SET status='RUNNING',last_clock_ns=? WHERE id=?", (now, CAMPAIGN_ID))
            db.commit()
        self._event("EPISODE_STARTED", planned_episode_id=planned_id)

    def reserve_request(self, planned_id: str, request_id: str, local_input_tokens: int) -> dict:
        self._check_elapsed()
        if type(local_input_tokens) is not int or not 0 <= local_input_tokens <= self.limits.max_input_tokens_per_request:
            self.stop("LOCAL_INPUT_TOKEN_LIMIT"); raise CampaignError("LOCAL_INPUT_TOKEN_LIMIT")
        if not re.fullmatch(re.escape(planned_id) + r"-r\d{2}", request_id):
            self.stop("REQUEST_ID_ATTRIBUTION_INVALID"); raise CampaignError("REQUEST_ID_ATTRIBUTION_INVALID")
        reserve_cost = Decimal(self.limits.reserve_usd_per_request)
        reserved_tokens = self.limits.max_input_tokens_per_request + self.limits.max_output_tokens_per_request
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            ep = db.execute("SELECT * FROM episodes WHERE planned_id=?", (planned_id,)).fetchone()
            if ep is None or ep["status"] != "STARTED":
                db.rollback(); self.stop("REQUEST_WITHOUT_ACTIVE_EPISODE"); raise CampaignError("REQUEST_WITHOUT_ACTIVE_EPISODE")
            count = db.execute("SELECT COUNT(*) FROM requests WHERE planned_id=?", (planned_id,)).fetchone()[0]
            ordinal = count + 1
            if ordinal > self.limits.max_requests_per_episode or request_id != f"{planned_id}-r{ordinal:02d}":
                db.rollback(); self.stop("RETRY_OR_EPISODE_REQUEST_LIMIT"); raise CampaignError("RETRY_OR_EPISODE_REQUEST_LIMIT")
            camp_rows = db.execute("SELECT status,reserve_usd,observed_cost_usd FROM requests").fetchall()
            lot_rows = db.execute("SELECT r.status,r.reserve_usd,r.observed_cost_usd FROM requests r JOIN episodes e USING(planned_id) WHERE e.lot=?", (ep["lot"],)).fetchall()
            campaign_count = len(camp_rows)
            camp_spent = sum((Decimal(r["observed_cost_usd"]) for r in camp_rows if r["observed_cost_usd"] is not None), Decimal(0))
            camp_held = sum((Decimal(r["reserve_usd"]) for r in camp_rows if r["status"] in ('STARTED','UNKNOWN_AFTER_INTERRUPTION','UNKNOWN_USAGE')), Decimal(0))
            lot_spent = sum((Decimal(r["observed_cost_usd"]) for r in lot_rows if r["observed_cost_usd"] is not None), Decimal(0))
            lot_held = sum((Decimal(r["reserve_usd"]) for r in lot_rows if r["status"] in ('STARTED','UNKNOWN_AFTER_INTERRUPTION','UNKNOWN_USAGE')), Decimal(0))
            try:
                check_ceiling(campaign_count, 1, self.limits.max_requests, "CAMPAIGN_REQUEST_LIMIT")
            except CampaignError:
                db.rollback(); self.stop("CAMPAIGN_REQUEST_LIMIT"); raise CampaignError("CAMPAIGN_REQUEST_LIMIT")
            try:
                check_budget(camp_spent, camp_held, reserve_cost,
                             Decimal(self.limits.max_spend_usd), "CAMPAIGN_BUDGET_LIMIT")
            except CampaignError:
                db.rollback(); self.stop("CAMPAIGN_BUDGET_LIMIT"); raise
            try:
                check_budget(lot_spent, lot_held, reserve_cost,
                             Decimal(self.limits.max_lot_spend_usd), "LOT_BUDGET_LIMIT")
            except CampaignError:
                db.rollback(); self.stop("LOT_BUDGET_LIMIT"); raise
            used_tokens = db.execute("SELECT COALESCE(SUM(reserved_tokens),0) FROM requests").fetchone()[0]
            try:
                check_ceiling(used_tokens, reserved_tokens, self.limits.max_total_tokens, "CAMPAIGN_TOKEN_LIMIT")
            except CampaignError:
                db.rollback(); self.stop("CAMPAIGN_TOKEN_LIMIT"); raise
            used_output = sum(
                r[0] if r[0] is not None else self.limits.max_output_tokens_per_request
                for r in db.execute("SELECT output_tokens FROM requests").fetchall())
            try:
                check_ceiling(used_output, self.limits.max_output_tokens_per_request,
                              self.limits.max_total_output_tokens, "CAMPAIGN_OUTPUT_TOKEN_LIMIT")
            except CampaignError:
                db.rollback(); self.stop("CAMPAIGN_OUTPUT_TOKEN_LIMIT"); raise
            now = self.now_ns()
            db.execute("INSERT INTO requests(request_id,planned_id,ordinal,status,local_input_tokens,reserved_tokens,reserve_usd,started_ns) VALUES (?,?,?,?,?,?,?,?)",
                       (request_id, planned_id, ordinal, "STARTED", local_input_tokens, reserved_tokens, str(reserve_cost), now))
            db.execute("UPDATE campaign SET last_clock_ns=? WHERE id=?", (now, CAMPAIGN_ID))
            db.commit()
        self._event("REQUEST_RESERVED", planned_episode_id=planned_id,
                    request_id=request_id, ordinal=ordinal,
                    local_input_tokens=local_input_tokens,
                    local_token_estimate_is_provider_certified=False,
                    reserved_tokens=reserved_tokens, reserve_usd=str(reserve_cost))
        return {"request_id": request_id, "max_output_tokens": self.limits.max_output_tokens_per_request,
                "timeout_ms": self.limits.max_call_ms, "retry_allowed": False,
                "classification": self.classification, "b1": "BLOCKED"}

    def complete_request(self, request_id: str, *, provider_input_tokens: int,
                         output_tokens: int, elapsed_ms: int, response_sha256: str) -> None:
        self._check_elapsed()
        if (type(provider_input_tokens) is not int or provider_input_tokens < 0
                or type(output_tokens) is not int or output_tokens < 0
                or type(elapsed_ms) is not int or elapsed_ms < 0
                or not _SHA256.fullmatch(response_sha256)):
            self.stop("REQUEST_RESULT_INVALID"); raise CampaignError("REQUEST_RESULT_INVALID")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row["status"] != "STARTED":
                db.rollback(); self.stop("REQUEST_RESULT_AMBIGUOUS"); raise CampaignError("REQUEST_RESULT_AMBIGUOUS")
            actual_elapsed = max(0, (self.now_ns() - row["started_ns"]) // 1_000_000)
            cost = ((Decimal(provider_input_tokens) * Decimal(self.limits.input_usd_per_million)
                     + Decimal(output_tokens) * Decimal(self.limits.output_usd_per_million))
                    / Decimal(1_000_000) * Decimal(self.limits.tax_multiplier))
            if (provider_input_tokens > self.limits.max_input_tokens_per_request
                    or output_tokens > self.limits.max_output_tokens_per_request
                    or elapsed_ms > self.limits.max_call_ms
                    or actual_elapsed > self.limits.max_call_ms):
                db.execute("UPDATE requests SET status='LIMIT_BREACH',finished_ns=?,provider_input_tokens=?,output_tokens=?,elapsed_ms=?,observed_cost_usd=?,response_sha=? WHERE request_id=?",
                           (self.now_ns(), provider_input_tokens, output_tokens, elapsed_ms, str(cost), response_sha256, request_id))
                db.execute("UPDATE campaign SET status='STOPPED',stopped_reason='OBSERVED_REQUEST_LIMIT_BREACH' WHERE id=?", (CAMPAIGN_ID,))
                db.commit(); self._event("CAMPAIGN_STOPPED", reason="OBSERVED_REQUEST_LIMIT_BREACH", request_id=request_id)
                raise CampaignError("OBSERVED_REQUEST_LIMIT_BREACH")
            if cost > Decimal(row["reserve_usd"]):
                db.execute("UPDATE requests SET status='COST_RESERVE_BREACH',finished_ns=?,provider_input_tokens=?,output_tokens=?,elapsed_ms=?,observed_cost_usd=?,response_sha=? WHERE request_id=?",
                           (self.now_ns(), provider_input_tokens, output_tokens, elapsed_ms, str(cost), response_sha256, request_id))
                db.execute("UPDATE campaign SET status='STOPPED',stopped_reason='REQUEST_COST_RESERVE_BREACH' WHERE id=?", (CAMPAIGN_ID,))
                db.commit(); self._event("CAMPAIGN_STOPPED", reason="REQUEST_COST_RESERVE_BREACH", request_id=request_id)
                raise CampaignError("REQUEST_COST_RESERVE_BREACH")
            db.execute("UPDATE requests SET status='COMPLETE',finished_ns=?,provider_input_tokens=?,output_tokens=?,elapsed_ms=?,observed_cost_usd=?,response_sha=? WHERE request_id=?",
                       (self.now_ns(), provider_input_tokens, output_tokens, elapsed_ms, str(cost), response_sha256, request_id))
            db.execute("UPDATE campaign SET last_clock_ns=? WHERE id=?", (self.now_ns(), CAMPAIGN_ID))
            db.commit()
        self._event("REQUEST_COMPLETE", request_id=request_id, provider_input_tokens=provider_input_tokens,
                    output_tokens=output_tokens, elapsed_ms=elapsed_ms,
                    estimated_cost_usd=str(cost), cost_is_invoice=False,
                    response_sha256=response_sha256)

    def finish_episode(self, planned_id: str, *, elapsed_ms: int, evidence_manifest: str | Path,
                       attribution: str, outcome: dict, valid: bool = True) -> None:
        self._check_elapsed()
        manifest_path = Path(evidence_manifest).resolve()
        if not manifest_path.is_relative_to(self.path.parent) or not manifest_path.is_file():
            self.stop("EPISODE_EVIDENCE_MANIFEST_INVALID"); raise CampaignError("EPISODE_EVIDENCE_MANIFEST_INVALID")
        evidence_sha256 = sha256(manifest_path.read_bytes())
        outcome_sha256 = sha256(canonical(outcome))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM episodes WHERE planned_id=?", (planned_id,)).fetchone()
            pending_req = db.execute("SELECT COUNT(*) FROM requests WHERE planned_id=? AND status!='COMPLETE'", (planned_id,)).fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM requests WHERE planned_id=?", (planned_id,)).fetchone()[0]
            actual_elapsed = -1 if row is None or row["started_ns"] is None else max(0, (self.now_ns() - row["started_ns"]) // 1_000_000)
            if (row is None or row["status"] != "STARTED" or pending_req or count == 0
                    or elapsed_ms > self.limits.max_episode_ms or actual_elapsed > self.limits.max_episode_ms or not valid
                    or attribution != self.classification or not _SHA256.fullmatch(evidence_sha256)
                    or not _SHA256.fullmatch(outcome_sha256)):
                db.execute("UPDATE episodes SET status='ERROR_STOPPED' WHERE planned_id=? AND status='STARTED'", (planned_id,))
                db.execute("UPDATE campaign SET status='STOPPED',stopped_reason='EPISODE_INVALID_OR_LIMIT' WHERE id=?", (CAMPAIGN_ID,))
                db.commit(); self._event("CAMPAIGN_STOPPED", reason="EPISODE_INVALID_OR_LIMIT", planned_episode_id=planned_id)
                raise CampaignError("EPISODE_INVALID_OR_LIMIT")
            now = self.now_ns()
            db.execute("UPDATE episodes SET status='COMPLETE',finished_ns=?,evidence_path=?,evidence_sha=?,attribution=?,outcome_sha=? WHERE planned_id=?",
                       (now, str(manifest_path.relative_to(self.path.parent)), evidence_sha256, attribution, outcome_sha256, planned_id))
            db.execute("UPDATE campaign SET last_clock_ns=? WHERE id=?", (now, CAMPAIGN_ID))
            db.commit()
        self._event("EPISODE_COMPLETE", planned_episode_id=planned_id,
                    evidence_sha256=evidence_sha256, outcome_sha256=outcome_sha256,
                    attribution=attribution, elapsed_ms=elapsed_ms)

    def checkpoint_lot(self) -> dict:
        self.verify(); self._check_elapsed()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            camp = db.execute("SELECT active_lot,status FROM campaign WHERE id=?", (CAMPAIGN_ID,)).fetchone()
            lot = camp["active_lot"]
            statuses = db.execute("SELECT status,COUNT(*) n FROM episodes WHERE lot=? GROUP BY status", (lot,)).fetchall()
            if any(r["status"] != "COMPLETE" for r in statuses) or sum(r["n"] for r in statuses) != len(self.lots[lot-1]["episode_ids"]):
                db.rollback(); raise CampaignError("LOT_NOT_COMPLETE_OR_HAS_INVALID_EPISODES")
            req_rows = db.execute("SELECT provider_input_tokens,output_tokens,observed_cost_usd FROM requests r JOIN episodes e USING(planned_id) WHERE e.lot=?", (lot,)).fetchall()
            req_count = len(req_rows)
            req_tokens = sum((r[0] or 0) + (r[1] or 0) for r in req_rows)
            req_cost = sum((Decimal(r[2]) for r in req_rows if r[2] is not None), Decimal(0))
            payload = {"lot": lot, "episodes": [dict(r) for r in db.execute("SELECT planned_id,evidence_sha,outcome_sha,attribution FROM episodes WHERE lot=? ORDER BY seq", (lot,))],
                       "requests": req_count, "tokens": req_tokens, "cost_usd": f"{req_cost:.8f}"}
            evidence = sha256(canonical(payload))
            db.execute("INSERT INTO lot_checkpoints VALUES (?,?,?,?,?,?,?,?)",
                       (lot, "COMPLETE_VERIFIED", len(payload["episodes"]), req_count, req_tokens, payload["cost_usd"], evidence, self.now_ns()))
            next_lot = lot + 1
            status = "COMPLETE" if next_lot > 8 else "READY"
            db.execute("UPDATE campaign SET active_lot=?,status=?,last_clock_ns=? WHERE id=?", (next_lot if next_lot <= 8 else lot, status, self.now_ns(), CAMPAIGN_ID))
            db.commit()
        self._event("LOT_CHECKPOINT_VERIFIED", lot=lot, evidence_sha256=evidence,
                    requests=req_count, tokens=req_tokens, observed_cost_estimate_usd=payload["cost_usd"])
        return {"lot": lot, "status": "COMPLETE_VERIFIED", "checkpoint_sha256": evidence,
                "requests": req_count, "tokens": req_tokens, "estimated_cost_usd": payload["cost_usd"]}

    def stop(self, reason: str):
        with self._connect() as db:
            db.execute("UPDATE campaign SET status='STOPPED',stopped_reason=? WHERE id=? AND status!='STOPPED'", (reason, CAMPAIGN_ID))
        self._event("CAMPAIGN_STOPPED", reason=reason)

    def resume_allowed(self) -> dict:
        """Permit only clean durable states; ambiguous calls are never replayed."""
        self.verify()
        snap = self.snapshot()
        if snap["status"] in ("STOPPED", "COMPLETE") or snap["episode_states"].get("STARTED", 0):
            raise CampaignError("CAMPAIGN_RESUME_NOT_SAFE")
        return {"status": "SAFE_TO_RESUME_NEXT_PENDING_ONLY", **snap}

