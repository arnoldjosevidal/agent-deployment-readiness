"""End-to-end approval workflow over the real ADR transport and localhost HTTP mock.

This is a wire/contract test only: the test server is bound to loopback, the
credential is a dummy test value, and the test counter is injected only under
ADR_TEST_OUTPUT. It does not certify provider tokenization or B1.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

from adr_g64r.common import canonical, digest
from adr_g64r.common import SafetyError
from adr_g64r.storage import EvidenceStore
from adr_live.model import NebiusModel, REVISION
from adr_p1.transport import Limits, MODEL, Transport
from adr_approval.model_port import NebiusApprovalModel
from adr_approval.service import ApprovalService
from adr_approval.workflow import ApprovalWorkflow


PASSWORD = "offline-bridge-test-operator-password"
ATTACK_MARKER = "[UNTRUSTED EVENT DESCRIPTION — FICTIONAL RED-TEAM FIXTURE]"


class FixedTestCounter:
    """Permitted only in transport test mode; not a provider-bound certificate."""
    def certificate(self, payload):
        return {"payload_sha256": digest(canonical(payload)), "model": MODEL,
                "tokenizer_revision": REVISION, "upper_bound": 256,
                "verified": True, "provider_binding": "TEST_FIXTURE_ONLY"}


class UnverifiedTestCounter(FixedTestCounter):
    def certificate(self, payload):
        result = super().certificate(payload)
        result["verified"] = False
        result["provider_binding"] = "UNVERIFIED_TEST_FIXTURE"
        return result


class ResponseSequence:
    def __init__(self):
        self.bodies = []
        self.next_response = 0

    def respond(self, handler):
        raw = handler.rfile.read(int(handler.headers.get("Content-Length", "0")))
        self.bodies.append(json.loads(raw))
        turns = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "live-calendar-1", "type": "function", "function": {"name": "search_calendar_events", "arguments": json.dumps({"query": "ADR demo review", "date": "2026-10-24"})}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "live-email-2", "type": "function", "function": {"name": "send_email", "arguments": json.dumps({"to": "demo-recipient@example.invalid", "subject": "Fictional approval test", "body": "Fictional only."})}}]},
            {"role": "assistant", "content": "The fictional calendar lookup is complete. The email action outcome was recorded."},
        ]
        message = turns[self.next_response % len(turns)]
        self.next_response += 1
        finish = "tool_calls" if message.get("tool_calls") else "stop"
        body = json.dumps({"model": MODEL,
            "usage": {"prompt_tokens": 80, "completion_tokens": 9, "total_tokens": 89},
            "choices": [{"message": message, "finish_reason": finish}]}).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)


class BridgeHandler(BaseHTTPRequestHandler):
    sequence = None
    def do_POST(self):
        self.sequence.respond(self)
    def log_message(self, *_args):
        pass


class NebiusApprovalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="adr-nebius-approval-bridge-")
        self.root = Path(self.temp.name)
        self.sequence = ResponseSequence()
        self.server = HTTPServer(("127.0.0.1", 0), BridgeHandler)
        self.server.RequestHandlerClass.sequence = self.sequence
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.old_env = {key: os.environ.get(key) for key in ("ADR_TEST_OUTPUT", "ADR_TEST_HTTP_ENDPOINT", "NEBIUS_API_KEY")}
        os.environ["ADR_TEST_OUTPUT"] = "1"
        os.environ["ADR_TEST_HTTP_ENDPOINT"] = f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions"
        os.environ["NEBIUS_API_KEY"] = "LOCAL_TEST_ONLY_NOT_A_SECRET"
        self.session = "approval-mock-" + uuid.uuid4().hex[:12]
        self.sink = EvidenceStore(self.root / "provider-evidence")
        self.limits = Limits(max_requests=6, max_total_tokens=4096, max_input_tokens=8192,
            max_output_tokens=256, max_call_ms=5000, max_total_ms=20000, max_retries=0,
            budget_usd="0.01", reservation_usd_per_token="0.00000030")
        self.transport = Transport(self.sink, self.session, self.limits)
        now = datetime.now(timezone.utc)
        self.authorization = {"human_approved": True, "scope": "ADR_S1_MVP",
            "session_id": self.session, "config_hash": self.transport.config_hash,
            "expires_utc": (now + timedelta(minutes=5)).isoformat(),
            "approval_reference": "LOCAL_HTTP_MOCK_TEST_ONLY"}
        self.model = NebiusApprovalModel.from_transport(self.transport, self.authorization, counter=FixedTestCounter())
        self.service = ApprovalService(self.root / "approval.sqlite3", PASSWORD, ttl_seconds=60)
        self.operator, self.csrf = self.service.login(PASSWORD)
        self.workflow = ApprovalWorkflow(self.service, model=self.model)

    def tearDown(self):
        if getattr(self, "service", None) and self.service._db:
            self.service._db.close()
        self.server.shutdown(); self.thread.join(timeout=2); self.server.server_close()
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()

    def test_live_model_bridge_approval_and_rejection_are_end_to_end_on_local_mock(self):
        for decision in ("approve", "reject"):
            with self.subTest(decision=decision):
                start = len(self.sequence.bodies)
                state = self.workflow.start("bridge-" + decision + "-" + uuid.uuid4().hex)
                self.assertEqual(state["status"], "awaiting_approval", state)
                self.assertEqual(state["source_classification"], "NEBIUS_NVIDIA_MODEL_VIA_DURABLE_ADR_TRANSPORT")
                self.assertEqual(len(self.sequence.bodies) - start, 2)
                second = self.sequence.bodies[start + 1]
                self.assertEqual(second["model"], MODEL)
                self.assertEqual(second["max_tokens"], 256)
                self.assertFalse(second["store"])
                self.assertEqual(second["tool_choice"], "auto")
                self.assertTrue(any(ATTACK_MARKER in str(message.get("content", "")) for message in second["messages"]))
                self.assertTrue(state["model_requests"][1]["untrusted_calendar_content_present"])
                email_id = state["pending_action_id"]
                email = self.service.get_action(email_id)
                decided = self.service.decide(email_id, email["action_sha256"], self.operator, decision, self.csrf)
                resumed = self.workflow.resume_after_decision(email_id)
                self.assertEqual(decided["status"], "executed" if decision == "approve" else "rejected")
                self.assertEqual(resumed["status"], "completed")
                self.assertIn("fictional calendar lookup is complete", resumed["final_response"].lower())
                self.assertEqual(len(self.sequence.bodies) - start, 3)
        self.assertTrue(all(row["status"] == "COMPLETE" for row in self.transport.snapshot()["requests"]))
        self.assertTrue(all(row["input_tokens"] == 80 and row["output_tokens"] == 9 for row in self.transport.snapshot()["requests"]))
        self.sink.recover(); self.sink.verify()
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id IN (SELECT action_id FROM actions WHERE decision='REQUIRE_APPROVAL')").fetchone()[0], 1)
        self.assertNotIn("LOCAL_TEST_ONLY_NOT_A_SECRET", self.transport.store.db.read_bytes().decode("latin-1", "ignore"))

    def test_model_bridge_fails_closed_when_binding_is_unverified_without_call(self):
        # An unverified binding certificate must stop before the transport
        # opens a request or contacts even our mock.
        guarded = NebiusApprovalModel.from_transport(self.transport, self.authorization, counter=UnverifiedTestCounter())
        payload = {"model": MODEL, "messages": [{"role": "user", "content": "offline binding gate"}],
                   "tools": [], "temperature": 0.0, "max_tokens": 256,
                   "stream": False, "store": False, "tool_choice": "auto"}
        with self.assertRaisesRegex(SafetyError, "VERIFIED_INPUT_TOKEN_BOUND_REQUIRED"):
            guarded.complete(payload, request_id="binding-gate-" + uuid.uuid4().hex[:8],
                             remaining_ms=1000, before_wire=lambda: self.fail("wire boundary reached"), sequence=0)
        self.assertFalse(self.sequence.bodies)


if __name__ == "__main__":
    unittest.main(verbosity=2)
