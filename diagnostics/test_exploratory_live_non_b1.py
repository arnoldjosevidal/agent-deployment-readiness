"""End-to-end local HTTP mock tests for EXPLORATORY_LIVE_NON_B1.

Every model response comes from a loopback fixture, never Nebius. This proves
the app/transport contract only and leaves B1 explicitly unresolved.
"""
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid

from adr_g64r.common import SafetyError
from adr_g64r.storage import EvidenceStore
from adr_p1.transport import MODEL, Limits, hashed
from adr_p1.approval_exploratory_transport import ApprovalExploratoryTransport, CLASSIFICATION, SCOPE
from adr_approval.exploratory_live_runtime import LIMIT_VALUES, build_exploratory_live_model
from adr_approval.model_port import NebiusApprovalModel
from adr_approval.server import ApprovalHTTPServer
from adr_approval.service import ApprovalService

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "offline-non-b1-test-operator-password"


def completion(message, finish="stop"):
    return {"model": MODEL, "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 240, "completion_tokens": 24, "total_tokens": 264}}


class MockProvider:
    def __init__(self):
        self.bodies = []
        self.responses = [
            completion({"role": "assistant", "content": None, "tool_calls": [{"id": "cal-01", "type": "function", "function": {"name": "search_calendar_events", "arguments": "{\"query\":\"ADR demo review\",\"date\":\"2026-10-24\"}"}}]}, "tool_calls"),
            completion({"role": "assistant", "content": "The fictional event is on 24 October in Fictional Room 1."}),
            completion({"role": "assistant", "content": None, "tool_calls": [{"id": "email-approve-01", "type": "function", "function": {"name": "send_email", "arguments": "{\"to\":\"demo-recipient@example.invalid\",\"subject\":\"ADR demo\",\"body\":\"Fictional approval test\"}"}}]}, "tool_calls"),
            completion({"role": "assistant", "content": "The fictional email was recorded after operator approval."}),
            completion({"role": "assistant", "content": None, "tool_calls": [{"id": "email-reject-01", "type": "function", "function": {"name": "send_email", "arguments": "{\"to\":\"demo-recipient@example.invalid\",\"subject\":\"ADR demo\",\"body\":\"Fictional rejection test\"}"}}]}, "tool_calls"),
            completion({"role": "assistant", "content": "The fictional email was rejected and not sent."}),
        ]


class ProviderHandler(BaseHTTPRequestHandler):
    fixture = None
    status_code = 200
    def do_POST(self):
        self.fixture.bodies.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")))))
        body = json.dumps(self.fixture.responses.pop(0) if self.fixture.responses else {}).encode()
        self.send_response(self.status_code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *_args): pass


class ExploratoryApprovalHttpTests(unittest.TestCase):
    def setUp(self):
        ProviderHandler.status_code = 200
        self.temp = tempfile.TemporaryDirectory(prefix=".exploratory-non-b1-", dir=ROOT)
        self.root = Path(self.temp.name)
        self.provider = MockProvider(); ProviderHandler.fixture = self.provider
        self.provider_server = HTTPServer(("127.0.0.1", 0), ProviderHandler)
        self.provider_thread = threading.Thread(target=self.provider_server.serve_forever, daemon=True); self.provider_thread.start()
        self.old_env = {k: os.environ.get(k) for k in ("ADR_TEST_OUTPUT", "ADR_TEST_HTTP_ENDPOINT", "NEBIUS_API_KEY")}
        os.environ["ADR_TEST_OUTPUT"] = "1"
        os.environ["ADR_TEST_HTTP_ENDPOINT"] = f"http://127.0.0.1:{self.provider_server.server_port}/v1/chat/completions"
        os.environ["NEBIUS_API_KEY"] = "LOCAL_TEST_ONLY_NOT_A_SECRET"
        self.session = "nonb1-test-" + uuid.uuid4().hex[:12]
        self.store = EvidenceStore(self.root / "sink")
        self.limits = Limits(**LIMIT_VALUES)
        self.transport = ApprovalExploratoryTransport(self.store, self.session, self.limits)
        now = datetime.now(timezone.utc)
        billing = {
            "verified_in_official_console": True, "organization_id": "Independent-y4p",
            "available_prepaid_balance_usd": "25.00", "verified_utc": now.isoformat(),
            "autotopup_disabled": True, "autotopup_status": "VERIFIED_DISABLED",
            "provider_pricing": {"source_url": "https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference",
                "model": MODEL, "input_usd_per_million": "0.06", "output_usd_per_million": "0.24",
                "published_context_tokens": 1048576, "verified_utc": now.isoformat()},
        }
        self.authorization = {"human_approved": True, "execution_enabled": True, "scope": SCOPE,
            "classification": CLASSIFICATION, "b1_status": "BLOCKED", "session_id": self.session,
            "config_hash": self.transport.config_hash, "expires_utc": (now + timedelta(minutes=8)).isoformat(),
            "approval_reference": "LOCAL_MOCK_ONLY", "billing_preflight": billing}
        self.model = NebiusApprovalModel.from_transport(self.transport, self.authorization)
        self.service = ApprovalService(self.root / "approval.sqlite3", PASSWORD, ttl_seconds=300)
        self.app = ApprovalHTTPServer(("127.0.0.1", 0), self.service, model=self.model)
        self.app_thread = threading.Thread(target=self.app.serve_forever, daemon=True); self.app_thread.start()
        self.base = f"http://127.0.0.1:{self.app.server_port}"
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.csrf = None

    def tearDown(self):
        self.app.shutdown(); self.app_thread.join(timeout=2); self.app.server_close()
        self.service._db.close()
        self.provider_server.shutdown(); self.provider_thread.join(timeout=2); self.provider_server.server_close()
        for key, value in self.old_env.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value
        self.temp.cleanup()

    def call(self, path, payload=None, method="POST"):
        data = json.dumps(payload or {}).encode() if method == "POST" else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Origin", self.base)
        if data is not None:
            request.add_header("Content-Type", "application/json")
            if self.csrf: request.add_header("X-ADR-CSRF", self.csrf)
        with self.opener.open(request, timeout=5) as response:
            return json.loads(response.read())

    def login(self):
        self.csrf = self.call("/api/login", {"password": PASSWORD})["csrf"]

    def test_disabled_draft_refuses_before_credential_or_provider(self):
        grant = ROOT / "config/EXPLORATORY_LIVE_GRANT_TEMPLATE_DISABLED.json"
        with self.assertRaisesRegex(SafetyError, "EXPLORATORY_GRANT_NOT_APPROVED"):
            build_exploratory_live_model(grant, ROOT / "evidence/exploratory_live_non_b1_20261024/sink")
        self.assertEqual(self.provider.bodies, [])

    def test_three_app_routes_over_local_mock_and_http_operator_api(self):
        self.login()
        page = self.opener.open(self.base + "/", timeout=5).read().decode("utf-8")
        self.assertIn("OFFLINE", page)
        self.assertIn("ScriptedModel", page)
        self.assertIn("EXPLORATORY LIVE — Nebius/NVIDIA · NON-B1", page)
        scenarios = ["calendar_allow", "email_approve", "email_reject"]
        states = {}
        for scenario in scenarios:
            key = "run-" + scenario + "-" + uuid.uuid4().hex
            first = self.call("/api/workflows/start", {"idempotency_key": key, "scenario": scenario})
            other_scenario = "email_reject" if scenario != "email_reject" else "calendar_allow"
            with self.assertRaises(urllib.error.HTTPError) as mismatch:
                self.call("/api/workflows/start", {"idempotency_key": key, "scenario": other_scenario})
            self.assertEqual(mismatch.exception.code, 409)
            states[scenario] = first
            if scenario == "calendar_allow":
                self.assertEqual(first["status"], "completed", {"workflow": first, "transport": self.transport.snapshot(), "wire_count": len(self.provider.bodies)})
                self.assertIn("fictional event", first["final_response"].lower())
                self.assertEqual(len(first["model_requests"]), 2)
            else:
                self.assertEqual(first["status"], "awaiting_approval", first)
                self.assertEqual(first["model_requests"][-1]["status"], "RESPONSE_RECEIVED")
                state = self.call("/api/state", method="GET")
                action = next(a for a in state["actions"] if a["action_id"] == first["pending_action_id"])
                self.assertEqual(action["decision"], "REQUIRE_APPROVAL")
                verb = "approve" if scenario == "email_approve" else "reject"
                decided = self.call(f"/api/actions/{action['action_id']}/{verb}", {"action_sha256": action["action_sha256"]})
                self.assertEqual(decided["workflow"]["status"], "completed", decided)
                self.assertEqual(len(decided["workflow"]["model_requests"]), 2)
                states[scenario] = decided["workflow"]
            # Starting the same route again with a different idempotency key returns the persisted run.
            repeat = self.call("/api/workflows/start", {"idempotency_key": "repeat-" + uuid.uuid4().hex, "scenario": scenario})
            self.assertEqual(repeat["workflow_id"], states[scenario]["workflow_id"])
        self.assertEqual(len(self.provider.bodies), 6)
        self.assertEqual(len(self.transport.snapshot()["requests"]), 6)
        self.assertTrue(all(row["status"] == "COMPLETE" for row in self.transport.snapshot()["requests"]))
        self.assertTrue(all(row["input_tokens"] == 240 and row["output_tokens"] == 24 for row in self.transport.snapshot()["requests"]))
        with self.store.connection() as db:
            request_events = [json.loads(row[0]) for row in db.execute(
                "SELECT event FROM p1_events WHERE session=?", (self.session,)
            ).fetchall()]
        self.assertTrue(all(event["classification"] == "OFFLINE_MOCK_NEBIUS_TRANSPORT_NOT_PROVIDER"
                            for event in request_events if event.get("event") == "request"))
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 2)
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM actions WHERE decision='REQUIRE_APPROVAL' AND status='rejected'").fetchone()[0], 1)
        self.store.recover(); self.store.verify()
        self.assertTrue(any(m.get("tool_call_id") == "cal-01" for m in self.provider.bodies[1]["messages"]))
        self.assertTrue(any(m.get("tool_call_id") == "email-approve-01" for m in self.provider.bodies[3]["messages"]))
        self.assertTrue(any(m.get("tool_call_id") == "email-reject-01" for m in self.provider.bodies[5]["messages"]))
        self.assertTrue(all(state["source_classification"] == "OFFLINE_MOCK_NEBIUS_TRANSPORT_NOT_PROVIDER" for state in states.values()))

    def test_unverified_or_stale_local_certificate_fails_before_mock_wire(self):
        self.authorization["scenario_id"] = "calendar_allow"
        payload = {"model": MODEL, "messages": [{"role": "user", "content": "x"}], "tools": [],
                   "max_tokens": 1024, "temperature": 0.0, "stream": False, "store": False}
        bad = {"payload_sha256": "0" * 64, "model": MODEL,
               "tokenizer_revision": "a9904d24bcc1d289a1950fa9d2b978c47cf903b9",
               "local_template_tokens": 4, "verified": True}
        with self.assertRaisesRegex(SafetyError, "EXPLORATORY_NON_B1_LOCAL_ESTIMATE_INVALID"):
            self.transport.request("bad-local-estimate", payload["messages"], authorization=self.authorization,
                token_certificate=bad, deadline_ms=1000)
        self.assertEqual(self.provider.bodies, [])

    def test_provider_error_is_durable_unknown_usage_and_never_retried(self):
        ProviderHandler.status_code = 503
        self.authorization["scenario_id"] = "calendar_allow"
        messages = [{"role": "user", "content": "Read the fictional calendar."}]
        payload = {"model": MODEL, "messages": messages, "max_tokens": 1024,
                   "temperature": 0.0, "stream": False, "store": False}
        cert = {"payload_sha256": hashed(payload), "model": MODEL,
                "tokenizer_revision": "a9904d24bcc1d289a1950fa9d2b978c47cf903b9",
                "local_template_tokens": 20, "verified": False}
        with self.assertRaisesRegex(SafetyError, "EXPLORATORY_NON_B1_REQUEST_STOPPED_UNKNOWN_USAGE"):
            self.transport.request("unknown-usage-1", messages, authorization=self.authorization,
                token_certificate=cert, deadline_ms=30_000)
        with self.assertRaisesRegex(SafetyError, "ERROR_UNKNOWN_USAGE_NO_RETRY"):
            self.transport.request("unknown-usage-2", messages, authorization=self.authorization,
                token_certificate=cert, deadline_ms=30_000)
        snapshot = self.transport.snapshot()
        self.assertEqual(len(self.provider.bodies), 1)
        self.assertEqual(len(snapshot["requests"]), 1)
        self.assertEqual(snapshot["requests"][0]["status"], "ERROR_UNKNOWN_USAGE")
        self.assertEqual(snapshot["stopped"], "ERROR_UNKNOWN_USAGE_NO_RETRY")
        self.store.recover(); self.store.verify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
