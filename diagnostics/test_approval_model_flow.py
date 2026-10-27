"""Offline tests for generic model output routing in the human-approval flow."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from adr_gateb.runner import Frame
from adr_approval.service import ApprovalService
from adr_approval.workflow import ApprovalWorkflow, UNTRUSTED_CALENDAR_CONTENT


PASSWORD = "offline-model-flow-test-operator-password"


class SequenceModel:
    source_classification = "OFFLINE_TEST_SEQUENCE_NOT_NEBIUS"
    model_id = "offline-test-sequence"
    output_token_limit = 128
    is_live = False

    def __init__(self, frames):
        self.frames = tuple(frames)
        self.calls = []

    def complete(self, payload, *, request_id, remaining_ms, before_wire, sequence):
        self.calls.append({"payload": payload, "request_id": request_id, "sequence": sequence})
        if sequence >= len(self.frames):
            raise AssertionError("unexpected model invocation")
        return self.frames[sequence]


def call(call_id, tool, args):
    return Frame(calls=({"id": call_id, "name": tool, "arguments": json.dumps(args)},))


class ModelFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".adr-model-flow-", dir=Path(__file__).resolve().parents[1])
        self.db = Path(self.temp.name) / "approval.sqlite3"
        self.service = ApprovalService(self.db, PASSWORD, ttl_seconds=60)
        self.operator, self.csrf = self.service.login(PASSWORD)

    def tearDown(self):
        self.service._db.close()
        self.temp.cleanup()

    def run_model(self, frames, key=None):
        model = SequenceModel(frames)
        workflow = ApprovalWorkflow(self.service, model=model)
        return workflow, model, workflow.start(key or ("flow-" + uuid.uuid4().hex))

    def test_allow_tool_returns_result_and_completes(self):
        workflow, model, state = self.run_model([
            call("calendar-allow", "search_calendar_events", {"query": "ADR demo review", "date": "2026-10-24"}),
            Frame(content="Calendar result summarized."),
        ])
        self.assertEqual(state["status"], "completed")
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(state["source_classification"], model.source_classification)
        action = self.service.get_action(state["action_ids"][0])
        self.assertEqual((action["decision"], action["status"]), ("ALLOW", "executed"))
        self.assertTrue(any(m.get("role") == "tool" for m in state["messages"]))

    def test_blocked_tool_is_returned_to_model_and_never_executes(self):
        _, model, state = self.run_model([
            call("file-block", "list_files", {"path": "fictional://private-folder"}),
            Frame(content="I could not access that file path; the legitimate workflow is complete."),
        ])
        self.assertEqual(state["status"], "completed")
        action = self.service.get_action(state["action_ids"][0])
        self.assertEqual((action["decision"], action["status"]), ("BLOCK", "blocked"))
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 0)
        self.assertTrue(any("BLOCKED" in m.get("content", "") for m in state["messages"] if m.get("role") == "tool"))
        self.assertEqual(len(model.calls), 2)

    def test_untrusted_calendar_content_is_in_next_model_input(self):
        _, model, state = self.run_model([
            call("calendar-allow", "search_calendar_events", {"query": "ADR demo review", "date": "2026-10-24"}),
            Frame(content="The user task is complete."),
        ])
        self.assertEqual(state["status"], "completed")
        second_payload = model.calls[1]["payload"]
        self.assertIn(UNTRUSTED_CALENDAR_CONTENT,
                      "\n".join(str(m.get("content", "")) for m in second_payload["messages"]))
        self.assertTrue(state["model_requests"][1]["untrusted_calendar_content_present"])
        self.assertEqual(state["model_requests"][1]["request_delivery"], "LOCAL_SCRIPTED_MODEL_INPUT_ONLY")

    def test_multiple_or_invalid_tool_calls_fail_closed_before_execution(self):
        multi = Frame(calls=(
            {"id": "m1", "name": "search_calendar_events", "arguments": '{"query":"x","date":"2026-10-24"}'},
            {"id": "m2", "name": "send_email", "arguments": '{"to":"demo@example.invalid","subject":"x","body":"x"}'},
        ))
        _, _, state = self.run_model([multi])
        self.assertEqual((state["status"], state["error_code"]), ("stopped_error", "MULTIPLE_TOOL_CALLS_UNSUPPORTED"))
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 0)

    def test_duplicate_start_key_returns_same_workflow_without_duplicate_effect(self):
        key = "idempotent-" + uuid.uuid4().hex
        workflow, model, first = self.run_model([
            call("calendar-allow", "search_calendar_events", {"query": "ADR demo review", "date": "2026-10-24"}),
            Frame(content="Done."),
        ], key)
        second = workflow.start(key)
        self.assertEqual(first["workflow_id"], second["workflow_id"])
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects").fetchone()[0], 1)

    def test_restart_after_allow_action_commit_recovers_without_duplicate_execution(self):
        model = SequenceModel([
            call("calendar-recovery", "search_calendar_events", {"query": "ADR demo review", "date": "2026-10-24"}),
            Frame(content="Calendar result summarized after recovery."),
        ])
        workflow = ApprovalWorkflow(self.service, model=model)
        completed = workflow.start("recover-action-" + uuid.uuid4().hex)
        action = self.service.get_action(completed["action_ids"][0])
        self.assertEqual(action["status"], "executed")
        # Model a crash after the action transaction commits but before its tool
        # result is persisted to the workflow transcript.
        interrupted = dict(completed)
        interrupted["messages"] = completed["messages"][:3]
        interrupted["model_requests"] = completed["model_requests"][:1]
        interrupted["next_frame"] = 1
        interrupted["action_ids"] = []
        interrupted["pending_action_id"] = None
        interrupted["pending_call_id"] = "calendar-recovery"
        interrupted["status"] = "proposing_action"
        interrupted["final_response"] = None
        workflow._save(interrupted, event="test_interrupted_after_action_commit")
        self.service._db.close()
        self.service = ApprovalService(self.db, PASSWORD, ttl_seconds=60)
        recovered_model = SequenceModel([Frame(content="unused"), Frame(content="Recovered calendar result summarized.")])
        recovered = ApprovalWorkflow(self.service, model=recovered_model).get(interrupted["workflow_id"])
        self.assertEqual(recovered["status"], "completed")
        self.assertIn("recovered calendar", recovered["final_response"].lower())
        self.assertEqual(self.service._db.execute("SELECT COUNT(*) FROM simulated_effects WHERE action_id=?", (action["action_id"],)).fetchone()[0], 1)

    def test_provider_error_is_unknown_and_not_replayed_after_restart(self):
        class FailingModel(SequenceModel):
            source_classification = "TEST_PROVIDER_ERROR_NOT_NEBIUS"
            is_live = True
            def complete(self, payload, *, request_id, remaining_ms, before_wire, sequence):
                self.calls.append({"request_id": request_id})
                before_wire()
                raise TimeoutError("raw transport text must not be persisted")
        model = FailingModel([])
        workflow = ApprovalWorkflow(self.service, model=model)
        state = workflow.start("failure-" + uuid.uuid4().hex)
        self.assertEqual(state["status"], "interrupted_unknown")
        self.assertEqual(state["model_requests"][0]["status"], "ERROR_UNKNOWN_NO_RETRY")
        self.assertNotIn("raw transport text", json.dumps(state))
        self.service._db.close()
        self.service = ApprovalService(self.db, PASSWORD, ttl_seconds=60)
        recovered = ApprovalWorkflow(self.service, model=model).get(state["workflow_id"])
        self.assertEqual(recovered["status"], "interrupted_unknown")
        self.assertEqual(len(model.calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
