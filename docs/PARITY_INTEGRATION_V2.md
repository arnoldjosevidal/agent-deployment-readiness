# V2 runtime integration and parity boundary — 24 October 2026

## Disposition

V2 is a new distribution candidate copied from the reviewed V1 files, then extended with the isolated `EXPLORATORY_LIVE_NON_B1` approval route. V1, the original exploratory live bundle, Gate A, the canonical Runner, baseline, S2, B1 and historical evidence were not edited. B1 remains `BLOCKED`; `config/PROVIDER_TOKEN_BINDING.json` remains `verified:false`.

The V2 route is integrated and tested offline against loopback mocks. In addition, source commit `7b9a5067ab916d3f43045faf1114268a0d1a57f0` was used in a separate two-request real `calendar_allow` smoke on 27 October, summarized in `demo/V2_LIVE_SMOKE_SUMMARY.json`. The historical six-request result remains a separate, read-only evidence set from another isolated variant. The V2 smoke did not repeat or reproduce those six provider responses.

## Components brought together

- The exploratory durable transport and fresh-grant runtime are now included in the distribution.
- The approval model port, workflow, server route and `adr_live.NebiusModel` include the scenario-aware changes required to run the three bounded workflows through the same persisted approval UI.
- A separate launcher requires `--enable-exploratory-live`, fresh grant/sink paths, current preflight and the in-process credential. The default ScriptedModel entrypoint is unchanged.
- Policy files, the frozen Gate A manifest, profile and protocol-bound live entrypoint remain unchanged. No B1 state was relaxed.
- The offline mock is explicitly recorded as `OFFLINE_MOCK_NEBIUS_TRANSPORT_NOT_PROVIDER` in the workflow and request events. It cannot be reported as a live request. Historical evidence remains read-only and is not replayed by V2.

## Differences from the reviewed candidate and historical live source

The reviewed V1 candidate did not contain the two exploratory modules or the scenario-selectable workflow bridge. V2 adds `adr_approval/exploratory_live_runtime.py`, `adr_p1/approval_exploratory_transport.py`, a V2 plan, disabled-only grant template, launcher and focused mock tests.

The four runtime modules differ from V1 for bounded reasons: `adr_approval/model_port.py` identifies the exact exploratory transport and labels local mocks offline; `adr_approval/server.py` accepts a scenario field on the authenticated workflow start route; `adr_approval/workflow.py` supports the three fixed fictional scenarios only for the explicit exploratory adapter and rejects idempotency-key reuse with a different scenario; `adr_live/model.py` permits only the exact exploratory transport with scope `EXPLORATORY_LIVE_NON_B1` and B1 `BLOCKED`, and reports mock/live accounting separately. The UI distinguishes offline ScriptedModel, local provider mock and exploratory live. The launcher requires an explicit activation switch. The transport labels mock request events offline.

These changes integrate source-derived behavior but do not establish byte-for-byte or live behavioral parity with the 24 October run. Only a future separately authorized request from this V2 build could verify that exact question. The six historical requests stay attached to their original session and are not included in this candidate's raw evidence tree.

## Verification performed

- Python 3.12.10 syntax compilation passed for all integrated modules and the focused test.
- 21 offline tests passed across the exploratory HTTP-mock suite, approval end-to-end suite, model-flow suite and B1 live-runtime gates.
- The mock suite exercised calendar ALLOW, fictional email REQUIRE_APPROVAL approval and rejection, model continuation, durable usage and evidence checks, a disabled-grant stop, invalid local-certificate stop, provider-error unknown usage/no retry, and scenario/idempotency mismatch rejection. Six request bodies reached only the loopback fake provider in that test. They are synthetic fixtures, not six new Nebius calls.
- `pip check` passed in the already isolated Python 3.12.10 environment with all 72 pinned dependencies. V2 adds no dependency. The earlier fresh-install record remains the clean-install evidence; this turn did not redownload packages or create a second environment.
- Candidate checks confirmed the binding remains false and no active grant was added. V1 is a source directory without `.git` metadata in this recovery workspace, so its Git status is unavailable; this work wrote only to V2, and all 12 `freeze_reference` files compare byte-for-byte with V1. Final candidate hashes are in `HASH_MANIFEST_V2.sha256`.

## Distribution security exclusion

The V2 copy omits the obsolete standalone `run_exploratory_pair04.py`: it hard-coded a private Windows user-temp path and belonged to a closed Pair 04 execution, so it is not needed by the integrated product entrypoints. The source copy remains preserved in V1; no original or historical record was edited. The unified approval and exploratory runtime uses the V2 launcher and fresh disabled grant template.

## Remaining boundaries

No active grant, credential, billing preflight, provider evidence or private account data is included. The disabled template cannot run. A live run requires a separate explicit authorization, current preflight and a fresh grant bound to the final V2 hashes. The local budget is not a provider billing guarantee, and the local tokenizer estimate does not satisfy B1.

The Work browser did not provide a host-loopback visual preview in the prior review. The HTML and JavaScript logic are checked, but screenshot-level review remains for the owner's Windows browser. The public repository, free judge-accessible demo URL and public video are not published; Devpost remains a draft.
