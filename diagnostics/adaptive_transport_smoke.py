"""One-call localhost-only exercise of the isolated live transport boundary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import threading

from adr_g64r.common import SafetyError
from adr_g64r.storage import EvidenceStore
from adr_live.model import TokenCounter
from adr_p1.exploratory_transport import (
    AUTOTOPUP_EXCEPTION_REFERENCE, CAMPAIGN_ID, CASE_ORDER,
    ExploratoryTransport, exploratory_limits,
)
from adr_p1.transport import MODEL

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "evidence" / "adaptive_transport_smoke_v6"


class Handler(BaseHTTPRequestHandler):
    bodies: list[dict] = []
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.bodies.append(json.loads(raw))
        body = json.dumps({
            "model": MODEL,
            "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
            "choices": [{"message": {"role": "assistant", "content": "offline response"}, "finish_reason": "stop"}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_args):
        pass


def main():
    if OUT.exists():
        raise RuntimeError("REFUSE_TO_OVERWRITE_OFFLINE_SMOKE_EVIDENCE")
    OUT.mkdir(parents=True)
    limits = exploratory_limits()
    expected_reserve = limits.max_requests * limits.max_total_tokens // limits.max_requests
    assert limits.max_requests == 60
    assert limits.max_input_tokens == 8192 and limits.max_output_tokens == 2048
    assert limits.max_retries == 0 and limits.max_call_ms == 30_000 and limits.max_total_ms == 900_000
    assert limits.budget_usd == "0.10"

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    session = "offline-adaptive-transport-v1"
    store = EvidenceStore(OUT / "sink")
    transport = ExploratoryTransport(store, session, limits)
    now = datetime.now(timezone.utc)
    approval = AUTOTOPUP_EXCEPTION_REFERENCE
    billing = {
        "organization_id": "Independent-y4p",
        "available_prepaid_balance_usd": "25.00",
        "verified_in_official_console": True,
        "balance_source": "official-console-observation-2026-10-24",
        "autotopup_status": "NOT_VERIFIED",
        "autotopup_disabled": None,
        "autotopup_exception": {
            "accepted_by_owner": True, "risk_accepted_by_owner": True,
            "scope": CAMPAIGN_ID, "approval_reference": approval,
        },
        "provider_pricing": {
            "source_url": "https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference",
            "model": MODEL, "input_usd_per_million": "0.06", "output_usd_per_million": "0.24",
            "published_context_tokens": 1_048_576,
            "verified_utc": now.isoformat().replace("+00:00", "Z"),
        },
    }
    authorization = {
        "human_approved": True, "exploratory_b1_deviation": True, "execution_enabled": True,
        "scope": CAMPAIGN_ID, "case_ids": list(CASE_ORDER), "pair_id": CAMPAIGN_ID,
        "planned_case_id": "MVP1_A_00", "adaptive_scenario_id": "B_TOOL_OUTPUT_LAUNDERING",
        "session_id": session, "config_hash": transport.config_hash,
        "max_spend_usd": "0.10", "max_requests_total": 60, "max_requests_per_case": 12,
        "max_input_tokens_per_request": 8192, "max_output_tokens_per_request": 2048,
        "max_retries": 0, "concurrency": 1, "approval_reference": approval,
        "expires_utc": (now + timedelta(minutes=30)).isoformat(), "billing_preflight": billing,
    }
    messages = [{"role": "user", "content": "localhost-only transport smoke"}]
    tools = [{"type": "function", "function": {"name": "test_tool", "description": "fixture", "parameters": {"type": "object", "properties": {}}}}]
    request_payload = {"model": MODEL, "messages": messages, "tools": tools,
                       "max_tokens": 2048, "temperature": 0.0, "stream": False, "store": False,
                       "tool_choice": "auto"}
    cert = TokenCounter().certificate(request_payload)
    old = {key: os.environ.get(key) for key in ("ADR_TEST_OUTPUT", "ADR_TEST_HTTP_ENDPOINT", "NEBIUS_API_KEY")}
    try:
        os.environ["ADR_TEST_OUTPUT"] = "1"
        os.environ["ADR_TEST_HTTP_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        os.environ["NEBIUS_API_KEY"] = "LOCAL_TEST_ONLY_NOT_A_SECRET"
        response = transport.request("offline-request-001", messages, tools=tools,
                                     authorization=authorization, token_certificate=cert,
                                     deadline_ms=30_000)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    snapshot = transport.snapshot()
    assert response["choices"][0]["message"]["content"] == "offline response"
    assert len(Handler.bodies) == 1 and Handler.bodies[0]["model"] == MODEL
    assert len(snapshot["requests"]) == 1 and snapshot["requests"][0]["status"] == "COMPLETE"
    assert snapshot["stopped"] is None
    store.recover()
    store.verify()
    result = {
        "classification": "LOCALHOST_MOCK_HTTP_NOT_NEBIUS_OR_NEMOTRON",
        "requests_to_nebius": 0, "mock_http_requests": len(Handler.bodies), "cost_usd": "0",
        "limits": {"requests": limits.max_requests, "input": limits.max_input_tokens,
                   "output": limits.max_output_tokens, "retries": limits.max_retries,
                   "call_timeout_ms": limits.max_call_ms, "session_timeout_ms": limits.max_total_ms,
                   "budget_usd": limits.budget_usd},
        "reservation_per_request_usd": str(limits.reservation_usd_per_token and
            __import__('decimal').Decimal(limits.max_total_tokens // limits.max_requests) * __import__('decimal').Decimal(limits.reservation_usd_per_token)),
        "transport_status": snapshot["requests"][0]["status"], "store_verify": "PASS",
        "auto_topup": "NOT_VERIFIED_OWNER_EXCEPTION_ACCEPTED_CAMPAIGN_ONLY",
    }
    (OUT / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
