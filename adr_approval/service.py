from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import uuid

from adr_g64r.common import canonical, digest
from adr_gateb.design import Design
from adr_gateb.policy import Policy


class ApprovalError(RuntimeError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


class ApprovalService:
    """Policy-backed local workflow. Effects are restricted to a SQLite fixture."""

    def __init__(self, db_path: str | Path, operator_password: str, *, design_path: str | Path | None = None,
                 ttl_seconds: int = 300, execution_hook=None):
        if not isinstance(operator_password, str) or len(operator_password) < 16:
            raise ValueError("OPERATOR_PASSWORD_MIN_16")
        if not 30 <= ttl_seconds <= 3600:
            raise ValueError("INVALID_APPROVAL_TTL")
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds, self.execution_hook = ttl_seconds, execution_hook
        self._lock = threading.RLock()
        self._salt = secrets.token_bytes(16)
        self._password_hash = hashlib.pbkdf2_hmac("sha256", operator_password.encode(), self._salt, 310_000)
        self._sessions: dict[str, tuple[str, datetime]] = {}
        self._db = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
          CREATE TABLE IF NOT EXISTS actions(
            action_id TEXT PRIMARY KEY, action_json TEXT NOT NULL, action_sha256 TEXT NOT NULL,
            decision TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            decided_by TEXT, decided_at TEXT, result_json TEXT, error_code TEXT
          );
          CREATE TABLE IF NOT EXISTS audit(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT NOT NULL,
            timestamp TEXT NOT NULL, event TEXT NOT NULL, operator_id TEXT, details_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS simulated_effects(
            action_id TEXT PRIMARY KEY, effect_json TEXT NOT NULL, created_at TEXT NOT NULL
          );
        """)
        interrupted = self._db.execute("SELECT action_id FROM actions WHERE status='executing'").fetchall()
        if not self.verify_audit_chain():
            raise ApprovalError("AUDIT_INTEGRITY_FAILURE", 500)
        for item in interrupted:
            self._db.execute("UPDATE actions SET status='execution_unknown', error_code='PROCESS_RESTART_DURING_EXECUTION' WHERE action_id=?", (item["action_id"],))
            self._audit(item["action_id"], "execution_unknown", details={"error_type": "PROCESS_RESTART_DURING_EXECUTION"})
        self.design = Design(design_path or Path(__file__).resolve().parents[1] / "freeze_reference")
        self.policy = Policy(self.design)
        self.task_id = self.design.policy["trusted_context"]["task_id_allowlist"][0]
        self.run_id = "approval-" + uuid.uuid4().hex
        self.context = self.policy.bind(self.task_id, self.run_id, "env-" + uuid.uuid4().hex)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _audit(self, action_id: str, event: str, operator_id: str | None = None, details=None):
        timestamp = self._now().isoformat()
        details_json = canonical(details or {}).decode("utf-8")
        previous = self._db.execute("SELECT event_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous_hash = previous["event_hash"] if previous else "0" * 64
        seq = self._db.execute("SELECT COALESCE(MAX(seq),0)+1 AS n FROM audit").fetchone()["n"]
        entry = {"seq": seq, "action_id": action_id, "timestamp": timestamp, "event": event,
                 "operator_id": operator_id, "details": json.loads(details_json), "previous_hash": previous_hash}
        event_hash = hashlib.sha256(canonical(entry)).hexdigest()
        self._db.execute("INSERT INTO audit(seq,action_id,timestamp,event,operator_id,details_json,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)",
                         (seq, action_id, timestamp, event, operator_id, details_json, previous_hash, event_hash))

    def verify_audit_chain(self) -> bool:
        previous_hash = "0" * 64
        rows = self._db.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        for expected_seq, row in enumerate(rows, 1):
            entry = {"seq": row["seq"], "action_id": row["action_id"], "timestamp": row["timestamp"],
                     "event": row["event"], "operator_id": row["operator_id"],
                     "details": json.loads(row["details_json"]), "previous_hash": row["previous_hash"]}
            if row["seq"] != expected_seq or row["previous_hash"] != previous_hash or hashlib.sha256(canonical(entry)).hexdigest() != row["event_hash"]:
                return False
            previous_hash = row["event_hash"]
        return True

    def propose_demo(self, scenario: str) -> dict:
        fixtures = {
            "calendar": ("search_calendar_events", {"query": "ADR demo review", "date": "2026-10-24"}),
            "approval": ("send_email", {"to": "demo-recipient@example.invalid", "subject": "Fictional ADR approval test", "body": "Simulated only."}),
            "block": ("list_files", {"path": "fictional://private-folder"}),
        }
        if scenario not in fixtures:
            raise ApprovalError("UNKNOWN_DEMO_SCENARIO", 400)
        tool, arguments = fixtures[scenario]
        return self.propose(tool, arguments, label="synthetic_operator_fixture")

    def login(self, password: str) -> tuple[str, str]:
        candidate = hashlib.pbkdf2_hmac("sha256", str(password).encode(), self._salt, 310_000)
        if not hmac.compare_digest(candidate, self._password_hash):
            raise ApprovalError("AUTHENTICATION_FAILED", 401)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with self._lock:
            self._sessions[token] = (csrf, self._now() + timedelta(minutes=30))
        return token, csrf

    def authenticate(self, token: str | None, csrf: str | None = None) -> str:
        with self._lock:
            entry = self._sessions.get(token or "")
            if not entry or entry[1] <= self._now():
                self._sessions.pop(token or "", None)
                raise ApprovalError("AUTHENTICATION_REQUIRED", 401)
            if csrf is not None and not hmac.compare_digest(entry[0], csrf):
                raise ApprovalError("CSRF_INVALID", 403)
            return "local_operator"

    def logout(self, token: str | None):
        with self._lock:
            self._sessions.pop(token or "", None)

    def _expire(self):
        if not self.verify_audit_chain():
            raise ApprovalError("AUDIT_INTEGRITY_FAILURE", 500)
        now = self._now().isoformat()
        rows = self._db.execute("SELECT action_id FROM actions WHERE status='pending' AND expires_at<=?", (now,)).fetchall()
        for row in rows:
            self._db.execute("UPDATE actions SET status='expired' WHERE action_id=? AND status='pending'", (row["action_id"],))
            self._audit(row["action_id"], "expired")

    def _execute_allowed(self, action_id: str, action: dict):
        # The demo runtime has no external tools. Its only effects are local fixture reads/writes.
        if self.execution_hook:
            self.execution_hook(action)
        if action["tool"] in ("search_calendar_events", "get_current_day", "get_day_calendar_events"):
            return {"fixture": True, "events": [{"title": "ADR demo review", "date": "2026-10-24", "location": "Fictional Room 1"}]}
        if action["tool"] == "send_email":
            recipient = action["arguments"].get("to", "")
            if not isinstance(recipient, str) or not recipient.endswith(".invalid"):
                raise ApprovalError("SIMULATED_DESTINATION_REQUIRED", 422)
            return {"fixture": True, "message": "Stored in simulated outbox", "destination": recipient}
        raise ApprovalError("NO_SIMULATED_EXECUTOR", 422)

    def propose(self, tool: str, arguments: dict, *, label: str = "operator_demo", workflow_binding: dict | None = None) -> dict:
        if not isinstance(tool, str) or not isinstance(arguments, dict):
            raise ApprovalError("INVALID_ACTION")
        if workflow_binding is not None and (
            not isinstance(workflow_binding, dict)
            or set(workflow_binding) != {"workflow_id", "tool_call_id"}
            or any(not isinstance(v, str) or not v for v in workflow_binding.values())
        ):
            raise ApprovalError("INVALID_WORKFLOW_BINDING")
        if len(canonical(arguments)) > 16_384:
            raise ApprovalError("ACTION_TOO_LARGE", 413)
        if tool == "send_email":
            recipient = arguments.get("to")
            if not isinstance(recipient, str) or not recipient.endswith(".invalid"):
                raise ApprovalError("SIMULATED_DESTINATION_REQUIRED", 422)
        with self._lock:
            self._expire()
            decision, reason = self.policy.decide(self.context, self.task_id, self.run_id, tool, arguments)
            action_id = "act-" + uuid.uuid4().hex
            created = self._now()
            action = {"action_id": action_id, "tool": tool, "arguments": arguments,
                      "destination": arguments.get("to") or arguments.get("path") or "local simulated calendar",
                      "reason": reason, "source_label": label}
            if workflow_binding is not None:
                action["workflow_binding"] = dict(workflow_binding)
            action_text = canonical(action).decode("utf-8")
            action_hash = hashlib.sha256(action_text.encode("utf-8")).hexdigest()
            status = "pending" if decision == "REQUIRE_APPROVAL" else ("blocked" if decision == "BLOCK" else "executing")
            expires = created + timedelta(seconds=self.ttl_seconds)
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (action_id, action_text, action_hash, decision, reason, status, created.isoformat(), expires.isoformat(), None, None, None, None))
                self._audit(action_id, "proposed", details={"decision": decision, "action_sha256": action_hash, "label": label})
                if decision == "BLOCK":
                    self._audit(action_id, "blocked")
                elif decision == "ALLOW":
                    self._audit(action_id, "execution_started_by_policy")
                else:
                    self._audit(action_id, "approval_pending")
                self._db.execute("COMMIT")
            except Exception as exc:
                self._db.execute("ROLLBACK")
                if decision == "ALLOW":
                    self._db.execute("UPDATE actions SET status='execution_unknown',error_code=? WHERE action_id=?", (type(exc).__name__, action_id))
                    self._audit(action_id, "execution_unknown", details={"error_type": type(exc).__name__})
                if isinstance(exc, ApprovalError):
                    raise
                raise ApprovalError("LOCAL_EXECUTION_FAILED", 500) from None
            if decision == "ALLOW":
                try:
                    result = self._execute_allowed(action_id, action)
                    self._db.execute("BEGIN IMMEDIATE")
                    self._db.execute("INSERT INTO simulated_effects VALUES(?,?,?)", (action_id, canonical(result).decode(), self._now().isoformat()))
                    self._db.execute("UPDATE actions SET status='executed',result_json=?,decided_at=? WHERE action_id=? AND status='executing'",
                                     (canonical(result).decode(), self._now().isoformat(), action_id))
                    if self._db.execute("SELECT changes()").fetchone()[0] != 1:
                        raise ApprovalError("EXECUTION_STATE_AMBIGUOUS", 409)
                    self._audit(action_id, "executed_by_policy")
                    self._db.execute("COMMIT")
                except Exception as exc:
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                    self._db.execute("UPDATE actions SET status='execution_unknown',error_code=? WHERE action_id=? AND status='executing'",
                                     (type(exc).__name__, action_id))
                    self._audit(action_id, "execution_unknown", details={"error_type": type(exc).__name__})
                    raise ApprovalError("EXECUTION_UNKNOWN_NO_RETRY", 503) from None
            return self.get_action(action_id)

    def _row(self, row):
        obj = dict(row)
        obj["action"] = json.loads(obj.pop("action_json"))
        if hashlib.sha256(canonical(obj["action"])).hexdigest() != obj["action_sha256"]:
            raise ApprovalError("ACTION_INTEGRITY_FAILURE", 409)
        obj["result"] = json.loads(obj.pop("result_json")) if obj["result_json"] else None
        return obj

    def get_action(self, action_id: str) -> dict:
        with self._lock:
            self._expire()
            row = self._db.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if not row:
                raise ApprovalError("ACTION_NOT_FOUND", 404)
            return self._row(row)

    def list_actions(self) -> list[dict]:
        with self._lock:
            self._expire()
            rows = self._db.execute("SELECT * FROM actions ORDER BY created_at DESC").fetchall()
            return [self._row(r) for r in rows]

    def _begin_decision(self, action_id: str, expected_hash: str, operator: str, choice: str):
        if choice not in ("approve", "reject"):
            raise ApprovalError("INVALID_DECISION")
        with self._lock:
            self._expire()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone()
                if not row:
                    raise ApprovalError("ACTION_NOT_FOUND", 404)
                if row["decision"] != "REQUIRE_APPROVAL":
                    raise ApprovalError("ACTION_NOT_APPROVABLE", 409)
                if row["status"] == "expired":
                    raise ApprovalError("ACTION_EXPIRED", 410)
                if row["status"] != "pending":
                    raise ApprovalError("ACTION_NOT_PENDING", 409)
                if not hmac.compare_digest(row["action_sha256"], expected_hash or ""):
                    raise ApprovalError("ACTION_FINGERPRINT_MISMATCH", 409)
                if datetime.fromisoformat(row["expires_at"]) <= self._now():
                    self._db.execute("UPDATE actions SET status='expired' WHERE action_id=?", (action_id,))
                    self._audit(action_id, "expired")
                    raise ApprovalError("ACTION_EXPIRED", 410)
                action = json.loads(row["action_json"])
                # Recompute from immutable bytes before consuming the pending state.
                if hashlib.sha256(canonical(action)).hexdigest() != row["action_sha256"]:
                    raise ApprovalError("ACTION_INTEGRITY_FAILURE", 409)
                status = "executing" if choice == "approve" else "rejected"
                self._db.execute("UPDATE actions SET status=?,decided_by=?,decided_at=? WHERE action_id=? AND status='pending'",
                                 (status, operator, self._now().isoformat(), action_id))
                if self._db.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ApprovalError("ACTION_NOT_PENDING", 409)
                self._audit(action_id, choice, operator, {"action_sha256": row["action_sha256"]})
                self._db.execute("COMMIT")
                return action
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def decide(self, action_id: str, expected_hash: str, session_token: str | None, choice: str, csrf_token: str | None) -> dict:
        operator = self.authenticate(session_token, csrf_token)
        action = self._begin_decision(action_id, expected_hash, operator, choice)
        if choice == "reject":
            return self.get_action(action_id)
        with self._lock:
            try:
                result = self._execute_allowed(action_id, action)
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    self._db.execute("INSERT INTO simulated_effects VALUES(?,?,?)", (action_id, canonical(result).decode(), self._now().isoformat()))
                    self._db.execute("UPDATE actions SET status='executed',result_json=? WHERE action_id=? AND status='executing'",
                                     (canonical(result).decode(), action_id))
                    if self._db.execute("SELECT changes()").fetchone()[0] != 1:
                        raise ApprovalError("EXECUTION_STATE_AMBIGUOUS", 409)
                    self._audit(action_id, "executed_after_approval", operator, {"action_sha256": hashlib.sha256(canonical(action)).hexdigest()})
                    self._db.execute("COMMIT")
                except Exception:
                    self._db.execute("ROLLBACK")
                    raise
            except Exception as exc:
                self._db.execute("UPDATE actions SET status='execution_unknown',error_code=? WHERE action_id=? AND status='executing'",
                                 (type(exc).__name__, action_id))
                self._audit(action_id, "execution_unknown", operator, {"error_type": type(exc).__name__})
                raise ApprovalError("EXECUTION_UNKNOWN_NO_RETRY", 503) from None
        return self.get_action(action_id)

    def audit_events(self, action_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM audit WHERE action_id=? ORDER BY seq", (action_id,)).fetchall()
            if not self.verify_audit_chain():
                raise ApprovalError("AUDIT_INTEGRITY_FAILURE", 500)
            return [{**dict(r), "details": json.loads(r["details_json"])} for r in rows]

