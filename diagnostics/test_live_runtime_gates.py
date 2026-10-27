"""No-call tests for live grant and B1 startup guards."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adr_g64r.common import SafetyError
from adr_approval.live_runtime import build_live_model, candidate_identity


class LiveRuntimeGateTests(unittest.TestCase):
    def test_disabled_template_cannot_construct_provider_model(self):
        with tempfile.TemporaryDirectory(prefix=".adr-live-gates-", dir=Path(__file__).resolve().parents[1]) as temp:
            grant = Path(temp) / "grant.json"
            grant.write_text(json.dumps({"execution_enabled": False, "human_approved": False}), encoding="utf-8")
            with self.assertRaisesRegex(SafetyError, "LIVE_GRANT_NOT_APPROVED"):
                build_live_model(grant, Path(temp) / "sink")

    def test_even_approved_grant_stops_at_current_unverified_b1_binding(self):
        self.assertTrue(candidate_identity()["sha256"])
        with tempfile.TemporaryDirectory(prefix=".adr-live-gates-", dir=Path(__file__).resolve().parents[1]) as temp:
            grant = Path(temp) / "grant.json"
            grant.write_text(json.dumps({"execution_enabled": True, "human_approved": True,
                "scope": "ADR_HUMAN_APPROVAL_DEMO", "b1_status": "VERIFIED",
                "candidate_sha256": candidate_identity()["sha256"]}), encoding="utf-8")
            with patch.dict(os.environ, {"NEBIUS_API_KEY": "LOCAL_TEST_ONLY_NOT_A_SECRET"}):
                with self.assertRaisesRegex(SafetyError, "PROVIDER_TOKEN_BINDING_UNVERIFIED_B1_BLOCKED"):
                    build_live_model(grant, Path(temp) / "sink")
            self.assertFalse((Path(temp) / "sink").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
