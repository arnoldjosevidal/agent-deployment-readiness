"""Model adapters for the isolated human-approval workflow.

The scripted adapter is the default. The Nebius adapter only delegates to the
existing durable ADR live model/transport; it does not add a network client or
weaken the provider-binding checks.
"""
from __future__ import annotations

import os

from adr_gateb.runner import Frame, ScriptedModel


class ScriptedApprovalModel:
    source_classification = "OFFLINE_SCRIPTED_FIXTURE_NOT_NEBIUS"
    model_id = "scripted-offline-fixture"
    output_token_limit = 256
    is_live = False

    def __init__(self, frames):
        self.frames = tuple(frames)

    def complete(self, payload, *, request_id, remaining_ms, before_wire, sequence):
        model = ScriptedModel(self.frames)
        model.index = sequence
        return model.complete(payload)


class NebiusApprovalModel:
    """Bridge the approval workflow to the already guarded NebiusModel adapter."""
    source_classification = "NEBIUS_NVIDIA_MODEL_VIA_DURABLE_ADR_TRANSPORT"
    is_live = True

    def __init__(self, model):
        if not callable(getattr(model, "complete", None)) or not callable(getattr(model, "wire_payload", None)):
            raise TypeError("NEBIUS_MODEL_ADAPTER_REQUIRED")
        transport = getattr(model, "transport", None)
        limits = getattr(transport, "limits", None)
        if limits is None or not getattr(transport, "store", None):
            raise TypeError("DURABLE_PROVIDER_TRANSPORT_REQUIRED")
        self.model = model
        self.model_id = limits.model
        self.output_token_limit = limits.max_output_tokens
        from adr_p1.approval_exploratory_transport import ApprovalExploratoryTransport
        self.exploratory_scenarios_enabled = type(transport) is ApprovalExploratoryTransport
        if type(transport) is ApprovalExploratoryTransport:
            self.source_classification = (
                "OFFLINE_MOCK_NEBIUS_TRANSPORT_NOT_PROVIDER"
                if os.environ.get("ADR_TEST_OUTPUT")
                else "EXPLORATORY_LIVE_NON_B1"
            )

    @classmethod
    def from_transport(cls, transport, authorization, counter=None):
        # Import lazily: the offline approval console does not load provider code.
        from adr_live.model import NebiusModel
        return cls(NebiusModel(transport, authorization, counter=counter))

    def complete(self, payload, *, request_id, remaining_ms, before_wire, sequence):
        return self.model.complete(payload, request_id, remaining_ms, before_wire)
