from __future__ import annotations

import json
import os
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from adr_g64r.common import SafetyError
from adr_live.counter_v031 import NebiusInputCounterV031, TOKENIZER_SHA256, TEMPLATE_SHA256
from adr_p1.transport import MODEL
from adr_p1.approval_exploratory_transport import ApprovalExploratoryTransport
from adr_live.model import NebiusModel

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "vendor" / "nemotron-input-counter-v0.3.1"


class CounterV031IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.counter = NebiusInputCounterV031()
        cls.fixture = json.loads((BUNDLE / "example-tool-history.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.counter.close()

    def test_fixture_count_is_local_experimental_and_summary_only(self):
        cert = self.counter.certificate(self.fixture)
        self.assertEqual(cert["local_template_tokens"], 431)
        self.assertEqual(cert["model"], MODEL)
        self.assertEqual(cert["counter_version"], "0.3.1")
        self.assertEqual(cert["tokenizer_sha256"], TOKENIZER_SHA256)
        self.assertEqual(cert["template_sha256"], TEMPLATE_SHA256)
        self.assertEqual(cert["runtime_versions"], {"python": "3.12.10", "transformers": "5.14.1", "tokenizers": "0.22.2", "jinja2": "3.1.6", "huggingface-hub": "1.24.0", "minijinja": "2.18.0"})
        self.assertIs(cert["verified"], False)
        self.assertEqual(cert["provider_binding"], "EXPERIMENTAL_LOCAL_V0_3_1_NOT_PROVIDER_CERTIFIED")
        self.assertEqual(set(cert), {
            "payload_sha256", "model", "tokenizer_revision", "local_template_tokens",
            "upper_bound", "headroom_tokens", "verified", "provider_binding",
            "counter_version", "runtime_versions", "counter_profile_id", "tokenizer_sha256", "template_sha256",
            "rendered_prompt_sha256", "input_limit", "within_input_limit",
        })

    def test_over_limit_is_rejected_before_a_certificate_can_reach_transport(self):
        payload = json.loads(json.dumps(self.fixture))
        payload["messages"][1]["content"] += " oversize-probe " * 12_000
        with self.assertRaisesRegex(SafetyError, "INPUT_LIMIT_EXCEEDED_NO_DISPATCH"):
            self.counter.certificate(payload)

    def test_model_does_not_dispatch_when_input_counter_refuses(self):
        payload = json.loads(json.dumps(self.fixture))
        payload["messages"][1]["content"] += " oversize-probe " * 12_000
        transport = object.__new__(ApprovalExploratoryTransport)
        transport.request = Mock()
        authorization = {"scope": "EXPLORATORY_LIVE_NON_B1", "b1_status": "BLOCKED"}
        with patch.dict(os.environ, {"ADR_TEST_OUTPUT": "1"}):
            model = NebiusModel(transport, authorization, counter=self.counter)
            with self.assertRaisesRegex(SafetyError, "INPUT_LIMIT_EXCEEDED_NO_DISPATCH"):
                model.complete(payload, "counter-refused", 30_000, lambda: None)
        transport.request.assert_not_called()
    def test_worker_reuse_does_not_change_count_or_payload_binding(self):
        first = self.counter.certificate(self.fixture)
        second = self.counter.certificate(self.fixture)
        self.assertEqual(first["payload_sha256"], second["payload_sha256"])
        self.assertEqual(first["rendered_prompt_sha256"], second["rendered_prompt_sha256"])
        self.assertEqual(first["local_template_tokens"], second["local_template_tokens"])

    def test_bundle_assets_match_pinned_profile_hashes(self):
        from hashlib import sha256
        self.assertEqual(sha256((BUNDLE / "tokenizer" / "tokenizer.json").read_bytes()).hexdigest(), TOKENIZER_SHA256)
        self.assertEqual(sha256((BUNDLE / "served_template.jinja").read_bytes()).hexdigest(), TEMPLATE_SHA256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
