"""End-to-end offline agent -> ADR policy -> authenticated decision regressions."""
import json
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

from adr_approval.service import ApprovalError, ApprovalService
from adr_approval.workflow import ApprovalWorkflow, UNTRUSTED_CALENDAR_CONTENT


PASSWORD = "local-operator-demo-password"


class EndToEndWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".adr-approval-e2e-", dir=Path(__file__).resolve().parents[1])
        self.db = Path(self.temp.name) / "workflow.sqlite3"
        self.service = ApprovalService(self.db, PASSWORD, ttl_seconds=60)
        self.workflow = ApprovalWorkflow(self.service)
        self.operator, self.csrf = self.service.login(PASSWORD)

    def tearDown(self):
        if self.service._db is not None:
            self.service._db.close()
        self.temp.cleanup()

    def start_pending(self):
        state = self.workflow.start()
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertEqual(state["task_status"], "calendar_completed_email_pending")
        self.assertEqual(len(state["model_requests"]), 2)
        self.assertFalse(state["model_requests"][0]["untrusted_calendar_content_present"])
        self.assertTrue(state["model_requests"][1]["untrusted_calendar_content_present"])
        self.assertTrue(any(m.get("role") == "tool" and UNTRUSTED_CALENDAR_CONTENT in m.get("content", "") for m in state["messages"]))
        calendar, email = [self.service.get_action(action_id) for action_id in state["action_ids"]]
        self.assertEqual((calendar["decision"], calendar["status"]), ("ALLOW", "executed"))
        self.assertEqual((email["decision"], email["status"]), ("REQUIRE_APPROVAL", "pending"))
        self.assertEqual(email["action"]["workflow_binding"]["workflow_id"], state["workflow_id"])
        return state, email

    def test_integrated_approval_executes_exact_action_then_resumes(self):
        state, email = self.start_pending()
        result = self.service.decide(email["action_id"], email["action_sha256"], self.operator, "approve", self.csrf)
        self.assertEqual(result["status"], "executed")
        resumed = self.workflow.resume_after_decision(email["action_id"])
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(resumed["task_status"], "completed_with_recorded_action_outcome")
        self.assertIn("calendar lookup is complete", resumed["final_response"].lower())
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 2)
        self.assertTrue(self.service.verify_audit_chain())

    def test_integrated_rejection_resumes_task_without_message_effect(self):
        state, email = self.start_pending()
        result = self.service.decide(email["action_id"], email["action_sha256"], self.operator, "reject", self.csrf)
        self.assertEqual(result["status"], "rejected")
        resumed = self.workflow.resume_after_decision(email["action_id"])
        self.assertEqual(resumed["status"], "completed")
        tool_results = [json.loads(m["content"]) for m in resumed["messages"] if m.get("role") == "tool"]
        self.assertTrue(any(x.get("status") == "REJECTED" and x.get("executed") is False for x in tool_results))
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 1)

    def test_duplicate_resume_is_idempotent_and_does_not_repeat_effect(self):
        _, email = self.start_pending()
        self.service.decide(email["action_id"], email["action_sha256"], self.operator, "approve", self.csrf)
        first = self.workflow.resume_after_decision(email["action_id"])
        second = self.workflow.resume_after_decision(email["action_id"])
        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (email["action_id"],)).fetchone()[0], 1)

    def test_pending_workflow_survives_process_restart_and_resumes(self):
        state, email = self.start_pending()
        self.service._db.close()
        restarted = ApprovalService(self.db, PASSWORD, ttl_seconds=60)
        try:
            resumed_workflow = ApprovalWorkflow(restarted)
            saved = resumed_workflow.get(state["workflow_id"])
            self.assertEqual((saved["status"], saved["pending_action_id"]), ("awaiting_approval", email["action_id"]))
            operator, csrf = restarted.login(PASSWORD)
            restarted.decide(email["action_id"], email["action_sha256"], operator, "reject", csrf)
            final = resumed_workflow.resume_after_decision(email["action_id"])
            self.assertEqual(final["status"], "completed")
            self.assertTrue(restarted.verify_audit_chain())
        finally:
            restarted._db.close()
            self.service._db = None

    def test_restart_after_decision_recovers_saved_continuation_without_reexecution(self):
        state, email = self.start_pending()
        self.service.decide(email["action_id"], email["action_sha256"], self.operator, "approve", self.csrf)
        decided = self.service.get_action(email["action_id"])
        call_id = decided["action"]["workflow_binding"]["tool_call_id"]
        self.workflow._append_tool_result(state, call_id, {"status": "EXECUTED", "executed": True, "result": decided["result"]})
        state["pending_action_id"] = None
        state["status"] = "continuing"
        self.workflow._save(state, event="test_saved_continuation")
        self.service._db.close()
        self.service._db = None
        restarted = ApprovalService(self.db, PASSWORD, ttl_seconds=60)
        try:
            recovered = ApprovalWorkflow(restarted).get(state["workflow_id"])
            self.assertEqual(recovered["status"], "completed")
            self.assertEqual(len(recovered["model_requests"]), 3)
            self.assertEqual(restarted._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (email["action_id"],)).fetchone()[0], 1)
        finally:
            restarted._db.close()

    def test_state_digest_detects_transcript_tampering(self):
        state, _ = self.start_pending()
        self.service._db.execute("UPDATE workflow_runs SET state_json=? WHERE workflow_id=?", ('{"workflow_id":"tampered"}', state["workflow_id"]))
        with self.assertRaisesRegex(ApprovalError, "WORKFLOW_INTEGRITY_FAILURE"):
            self.workflow.get(state["workflow_id"])

    def test_unknown_execution_is_not_retried_and_task_is_marked_interrupted(self):
        state, email = self.start_pending()
        self.service.execution_hook = lambda _action: (_ for _ in ()).throw(TimeoutError("simulated ambiguous effect"))
        with self.assertRaisesRegex(ApprovalError, "EXECUTION_UNKNOWN_NO_RETRY"):
            self.service.decide(email["action_id"], email["action_sha256"], self.operator, "approve", self.csrf)
        recovered = self.workflow.resume_after_decision(email["action_id"])
        self.assertEqual(recovered["status"], "interrupted_unknown")
        self.assertEqual(recovered["task_status"], "message_action_not_retried")
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (email["action_id"],)).fetchone()[0], 0)

    def test_expired_pending_action_is_not_executed_and_legitimate_flow_finishes(self):
        state, email = self.start_pending()
        future = self.service._now() + timedelta(seconds=120)
        with patch.object(self.service, "_now", return_value=future):
            expired = self.service.get_action(email["action_id"])
            self.assertEqual(expired["status"], "expired")
            resumed = self.workflow.resume_after_decision(email["action_id"])
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(resumed["task_status"], "completed_with_recorded_action_outcome")
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (email["action_id"],)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
