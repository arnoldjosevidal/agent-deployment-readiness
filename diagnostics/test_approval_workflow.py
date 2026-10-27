"""Focused local-only regression suite for the human approval candidate."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from adr_approval.server import ApprovalHTTPServer
from adr_approval.service import ApprovalError, ApprovalService


PASSWORD = "local-operator-demo-password"


class ApprovalServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".adr-approval-test-", dir=Path(__file__).resolve().parents[1])
        self.db = Path(self.temp.name) / "approval.sqlite3"
        self.service = ApprovalService(self.db, PASSWORD, ttl_seconds=60)
        self.operator, self.csrf = self.service.login(PASSWORD)

    def tearDown(self):
        self.service._db.close()
        self.temp.cleanup()

    def propose_email(self):
        return self.service.propose("send_email", {"to": "review@example.invalid", "subject": "Test", "body": "Fictional"})

    def decide(self, action, choice="approve"):
        return self.service.decide(action["action_id"], action["action_sha256"], self.operator, choice, self.csrf)

    def test_allow_executes_and_records_effect(self):
        row = self.service.propose("search_calendar_events", {"query": "ADR", "date": "2026-10-24"})
        self.assertEqual((row["decision"], row["status"]), ("ALLOW", "executed"))
        self.assertTrue(row["result"]["fixture"])
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 1)

    def test_block_is_not_approvable(self):
        row = self.service.propose("list_files", {"path": "fictional://private"})
        self.assertEqual((row["decision"], row["status"]), ("BLOCK", "blocked"))
        with self.assertRaisesRegex(ApprovalError, "ACTION_NOT_APPROVABLE"):
            self.decide(row)
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 0)

    def test_require_approval_is_pending_without_effect(self):
        row = self.propose_email()
        self.assertEqual((row["decision"], row["status"]), ("REQUIRE_APPROVAL", "pending"))
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 0)

    def test_authenticated_approval_executes_exact_action_once(self):
        row = self.propose_email()
        result = self.decide(row)
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["action_sha256"], row["action_sha256"])
        self.assertEqual(result["result"]["destination"], "review@example.invalid")
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (row["action_id"],)).fetchone()[0], 1)
        with self.assertRaisesRegex(ApprovalError, "ACTION_NOT_PENDING"):
            self.decide(row)

    def test_rejection_has_no_effect(self):
        row = self.propose_email()
        self.assertEqual(self.decide(row, "reject")["status"], "rejected")
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 0)

    def test_unauthenticated_operator_is_rejected(self):
        with self.assertRaisesRegex(ApprovalError, "AUTHENTICATION_REQUIRED"):
            self.service.authenticate("forged-session", "csrf")
        with self.assertRaisesRegex(ApprovalError, "AUTHENTICATION_FAILED"):
            self.service.login("wrong password long enough")

    def test_service_decision_requires_an_authenticated_session(self):
        row = self.propose_email()
        with self.assertRaisesRegex(ApprovalError, "AUTHENTICATION_REQUIRED"):
            self.service.decide(row["action_id"], row["action_sha256"], "forged-session", "approve", self.csrf)
        self.assertEqual(self.service.get_action(row["action_id"])["status"], "pending")

    def test_restart_marks_inflight_execution_unknown(self):
        row = self.propose_email()
        self.service._db.execute("UPDATE actions SET status='executing' WHERE action_id=?", (row["action_id"],))
        resumed = ApprovalService(self.db, PASSWORD, ttl_seconds=60)
        try:
            recovered = resumed.get_action(row["action_id"])
            self.assertEqual(recovered["status"], "execution_unknown")
            self.assertEqual(recovered["error_code"], "PROCESS_RESTART_DURING_EXECUTION")
            self.assertTrue(resumed.verify_audit_chain())
            token, csrf = resumed.login(PASSWORD)
            with self.assertRaisesRegex(ApprovalError, "ACTION_NOT_PENDING"):
                resumed.decide(row["action_id"], row["action_sha256"], token, "approve", csrf)
        finally:
            resumed._db.close()

    def test_modified_fingerprint_is_rejected(self):
        row = self.propose_email()
        with self.assertRaisesRegex(ApprovalError, "ACTION_FINGERPRINT_MISMATCH"):
            self.service.decide(row["action_id"], "0" * 64, self.operator, "approve", self.csrf)
        self.assertEqual(self.service.get_action(row["action_id"])["status"], "pending")

    def test_corrupt_stored_action_is_rejected(self):
        row = self.propose_email()
        self.service._db.execute("UPDATE actions SET action_json=? WHERE action_id=?", ('{"tool":"send_email","arguments":{}}', row["action_id"]))
        with self.assertRaisesRegex(ApprovalError, "ACTION_INTEGRITY_FAILURE"):
            self.decide(row)
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 0)

    def test_expired_action_cannot_execute(self):
        row = self.propose_email()
        future = self.service._now() + __import__("datetime").timedelta(seconds=120)
        with patch.object(self.service, "_now", return_value=future):
            with self.assertRaisesRegex(ApprovalError, "ACTION_EXPIRED"):
                self.decide(row)
        self.assertEqual(self.service.get_action(row["action_id"])["status"], "expired")

    def test_execution_failure_is_unknown_and_never_retried(self):
        self.service.execution_hook = lambda _action: (_ for _ in ()).throw(TimeoutError("injected local fault"))
        row = self.propose_email()
        with self.assertRaisesRegex(ApprovalError, "EXECUTION_UNKNOWN_NO_RETRY"):
            self.decide(row)
        state = self.service.get_action(row["action_id"])
        self.assertEqual(state["status"], "execution_unknown")
        with self.assertRaisesRegex(ApprovalError, "ACTION_NOT_PENDING"):
            self.decide(row)
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 0)

    def test_pending_action_does_not_stop_legitimate_calendar_task(self):
        email = self.propose_email()
        calendar = self.service.propose("search_calendar_events", {"query": "ADR", "date": "2026-10-24"})
        self.assertEqual(email["status"], "pending")
        self.assertEqual(calendar["status"], "executed")
        self.assertTrue(calendar["result"]["events"])

    def test_audit_records_authenticated_operator_and_terminal_state(self):
        row = self.propose_email()
        result = self.decide(row)
        audit = self.service.audit_events(row["action_id"])
        self.assertEqual([x["event"] for x in audit], ["proposed", "approval_pending", "approve", "executed_after_approval"])
        self.assertTrue(all(x["operator_id"] == "local_operator" for x in audit[-2:]))
        self.assertTrue(self.service.verify_audit_chain())
        self.assertEqual(result["status"], "executed")

    def test_audit_chain_detects_edit(self):
        row = self.propose_email()
        self.service._db.execute("UPDATE audit SET event='tampered' WHERE action_id=? AND event='approval_pending'", (row["action_id"],))
        self.assertFalse(self.service.verify_audit_chain())
        with self.assertRaisesRegex(ApprovalError, "AUDIT_INTEGRITY_FAILURE"):
            self.service.audit_events(row["action_id"])
        with self.assertRaisesRegex(ApprovalError, "AUDIT_INTEGRITY_FAILURE"):
            self.decide(row)


class ApprovalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".adr-approval-http-test-", dir=Path(__file__).resolve().parents[1])
        self.db = Path(self.temp.name) / "http.sqlite3"
        self.service = ApprovalService(self.db, PASSWORD)
        self.server = ApprovalHTTPServer(("127.0.0.1", 0), self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.service._db.close(); self.temp.cleanup()

    def request(self, method, path, payload=None, *, cookie=None, csrf=None, origin=True, host=None):
        if path == "/api/workflows/start" and payload is not None:
            payload = {**payload, "idempotency_key": payload.get("idempotency_key") or uuid.uuid4().hex}
        conn = http.client.HTTPConnection(self.host, self.port, timeout=3)
        headers = {"Host": host or f"{self.host}:{self.port}"}
        if origin:
            headers["Origin"] = f"http://{headers['Host']}"
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body.encode()))
        else:
            body = None
        if cookie: headers["Cookie"] = cookie
        if csrf: headers["X-ADR-CSRF"] = csrf
        conn.request(method, path, body, headers)
        response = conn.getresponse(); raw = response.read(); status = response.status
        parsed = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw.decode()
        result = status, parsed, response.getheader("Set-Cookie")
        conn.close(); return result

    def test_http_enforces_login_csrf_and_serves_backend_state(self):
        status, denied, _ = self.request("GET", "/api/state")
        self.assertEqual((status, denied["error"]), (401, "AUTHENTICATION_REQUIRED"))
        status, _, _ = self.request("POST", "/api/login", {"password": PASSWORD}, origin=False)
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/login", {"password": PASSWORD}, host="attacker.example:8765")
        self.assertEqual(status, 403)
        status, login, set_cookie = self.request("POST", "/api/login", {"password": PASSWORD})
        self.assertEqual(status, 200)
        cookie = set_cookie.split(";", 1)[0]
        status, _, _ = self.request("POST", "/api/propose", {"scenario": "approval"}, cookie=cookie)
        self.assertEqual(status, 403)  # CSRF token missing
        status, action, _ = self.request("POST", "/api/propose", {"scenario": "approval"}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status, action["decision"], action["status"]), (201, "REQUIRE_APPROVAL", "pending"))
        status, state, _ = self.request("GET", "/api/state", cookie=cookie)
        self.assertEqual((status, state["actions"][0]["action_id"]), (200, action["action_id"]))
        status, blocked, _ = self.request("POST", "/api/propose", {"scenario": "block"}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status, blocked["decision"], blocked["status"]), (201, "BLOCK", "blocked"))
        status, page, _ = self.request("GET", "/")
        self.assertEqual(status, 200); self.assertIn("Human approval console", page); self.assertIn("Start integrated agent", page)
        status, rejected, _ = self.request("POST", "/api/propose", {"scenario": "arbitrary"}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status, rejected["error"]), (400, "UNKNOWN_DEMO_SCENARIO"))

    def test_http_integrated_workflow_pauses_and_resumes_after_authenticated_approval(self):
        status, login, set_cookie = self.request("POST", "/api/login", {"password": PASSWORD})
        self.assertEqual(status, 200)
        cookie = set_cookie.split(";", 1)[0]
        status, started, _ = self.request("POST", "/api/workflows/start", {}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status, started["status"], started["task_status"]), (201, "awaiting_approval", "calendar_completed_email_pending"))
        self.assertTrue(started["model_requests"][1]["untrusted_calendar_content_present"])
        status, current, _ = self.request("GET", "/api/state", cookie=cookie)
        self.assertEqual(status, 200)
        pending = next(a for a in current["actions"] if a["decision"] == "REQUIRE_APPROVAL")
        status, approved, _ = self.request("POST", f"/api/actions/{pending['action_id']}/approve",
            {"action_sha256": pending["action_sha256"]}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status, approved["status"], approved["workflow"]["status"]), (200, "executed", "completed"))
        self.assertIn("calendar lookup is complete", approved["workflow"]["final_response"].lower())
        self.assertEqual(approved["workflow"]["source_classification"], "OFFLINE_SCRIPTED_FIXTURE_NOT_NEBIUS")
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (pending["action_id"],)).fetchone()[0], 1)
        status, rejected, _ = self.request("POST", "/api/propose", {"scenario": "arbitrary"}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status, rejected["error"]), (400, "UNKNOWN_DEMO_SCENARIO"))

    def test_http_rejection_resumes_and_finishes_without_effect(self):
        status, login, set_cookie = self.request("POST", "/api/login", {"password": PASSWORD})
        self.assertEqual(status, 200); cookie = set_cookie.split(";", 1)[0]
        status, started, _ = self.request("POST", "/api/workflows/start", {}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status, started["status"]), (201, "awaiting_approval"))
        status, state, _ = self.request("GET", "/api/state", cookie=cookie)
        pending = next(a for a in state["actions"] if a["decision"] == "REQUIRE_APPROVAL")
        status, rejected, _ = self.request("POST", f"/api/actions/{pending['action_id']}/reject",
            {"action_sha256": pending["action_sha256"]}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status, rejected["status"], rejected["workflow"]["status"]), (200, "rejected", "completed"))
        self.assertIn("calendar lookup is complete", rejected["workflow"]["final_response"].lower())
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (pending["action_id"],)).fetchone()[0], 0)
        tool_results = [json.loads(m["content"]) for m in rejected["workflow"]["messages"] if m.get("role") == "tool"]
        self.assertTrue(any(item.get("status") == "REJECTED" and item.get("executed") is False for item in tool_results))

    def test_http_state_recovers_decision_after_server_restart_without_duplicate_effect(self):
        status, login, set_cookie = self.request("POST", "/api/login", {"password": PASSWORD})
        self.assertEqual(status, 200); cookie = set_cookie.split(";", 1)[0]
        status, started, _ = self.request("POST", "/api/workflows/start", {}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual(status, 201)
        status, state, _ = self.request("GET", "/api/state", cookie=cookie)
        pending = next(a for a in state["actions"] if a["decision"] == "REQUIRE_APPROVAL")
        # Simulate a process interruption after the decision is durable but before HTTP continuation.
        old_operator, old_csrf = self.service.login(PASSWORD)
        decided = self.service.decide(pending["action_id"], pending["action_sha256"], old_operator, "approve", old_csrf)
        self.assertEqual(decided["status"], "executed")
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2); self.service._db.close()
        self.service = ApprovalService(self.db, PASSWORD)
        self.server = ApprovalHTTPServer(("127.0.0.1", 0), self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.host, self.port = self.server.server_address
        status, login2, set_cookie2 = self.request("POST", "/api/login", {"password": PASSWORD})
        self.assertEqual(status, 200); cookie2 = set_cookie2.split(";", 1)[0]
        status, recovered, _ = self.request("GET", "/api/state", cookie=cookie2)
        workflow = next(w for w in recovered["workflows"] if w["workflow_id"] == started["workflow_id"])
        self.assertEqual((status, workflow["status"]), (200, "completed"))
        self.assertTrue(workflow["final_response"])
        self.assertEqual(len(workflow["model_requests"]), 3)
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (pending["action_id"],)).fetchone()[0], 1)

    def test_page_exposes_integrated_task_status_and_scripted_final_response(self):
        status, page, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Integrated agent task: not started.", page)
        self.assertIn("function renderWorkflows(items)", page)
        self.assertIn("live?'Nebius/NVIDIA model':'ScriptedModel'", page)
        self.assertIn("The agent workflow completed and produced a final response.", page)

    def test_workflow_start_idempotency_key_returns_same_run(self):
        status, login, set_cookie = self.request("POST", "/api/login", {"password": PASSWORD})
        cookie = set_cookie.split(";", 1)[0]
        key = uuid.uuid4().hex
        status1, first, _ = self.request("POST", "/api/workflows/start", {"idempotency_key": key}, cookie=cookie, csrf=login["csrf"])
        status2, second, _ = self.request("POST", "/api/workflows/start", {"idempotency_key": key}, cookie=cookie, csrf=login["csrf"])
        self.assertEqual((status1, status2, first["workflow_id"], second["workflow_id"]), (201, 201, first["workflow_id"], first["workflow_id"]))
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
