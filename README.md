# Agent Deployment Readiness (ADR)

ADR is a Windows-first local workflow for inspecting an agent's proposed tool actions, applying an independent deterministic gate, and retaining evidence for a matched evaluation.

**The product flow:** the agent proposes an action → ADR evaluates it → a human approves or rejects a held action → the agent continues. The public walkthrough below is a static offline fixture; it does not call Nebius or claim to be a live run.

**Private review candidate — not published. The owner-approved MIT license applies to original ADR code and materials only; third-party components retain their own terms.** The offline integration is accepted. A separate exploratory 39-pair Nemotron/Nebius campaign has real evidence; B1 remains blocked for the original protocol, so no protocol-confirming result is claimed.

## Show the existing product without inference

Open `demo/index.html` directly in a desktop browser. No account, dependency installation, server, credentials or external request is required. Click the seven workflow steps:

**Inspect → Threat Model → Attack → Measure → Harden → Re-attack → Decide**

The tool-action scenario is explicitly **synthetic** and backed by a persisted local fixture. A separate 12-run offline replay through the actual Runner uses `ScriptedModel`; its A/G trace summary and provenance are shown in the demo. It is evidence of policy routing only, not model behavior. A separate read-only panel summarizes six historical real Nebius/Nemotron requests through the isolated `EXPLORATORY_LIVE_NON_B1` workflow; the panel makes no calls and the raw evidence is not included in this repository. The historical G6.3 panel describes oracle-policy development observations. The G6.4-R 67/67 panel is historical infrastructure evidence; Stage 1 34/34 is accepted offline integration evidence. None is a Nemotron effectiveness result. The protocol-confirming A/G comparison remains **NOT RUN**. The separate 39-pair campaign is exploratory and is not represented as confirmatory; no scores or improvements are invented. The teaching fixture policy is distinct from the frozen independent G policy.

## Windows installation for the full source

Python **3.12.10** and Windows were used for the accepted integration. The browser demo needs neither Python nor Node. The full integration uses AgentDojo 0.1.35, tokenizers 0.23.2 and the version-pinned dependency closure in `requirements-windows-py312.lock.txt`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows-py312.lock.txt
```

A fresh isolated Windows installation was completed on **18 October 2026**: all 72 pinned versions matched, pip check passed, and six minimal offline startup checks passed. See `docs/INSTALLATION_VERIFIED.md` and `docs/CLEAN_INSTALL_EVIDENCE.json`. Installation downloads open-source dependencies; it does not call a model. No wheel-hash lock or bundled Python runtime is claimed. Local tokenizer assets and pure-Python Jinja2/MarkupSafe are included with their licenses. Do not install model weights.


The bundled offline Runner replay can be reproduced after installing the pinned dependencies. It uses six predeclared fictional payloads, the frozen S1 setup and `ScriptedModel`; the harness denies socket access and creates a fresh local evidence sink. No API key is read and no model is called:

```powershell
$out = Join-Path $env:TEMP ("adr-offline-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -B .\run_offline_abg_replay.py $out
```

Use a new output directory for each run. Expected summaries cover two distinct 12-run fixture replays. The retained negative-utility replay scores utility false in both arms. The later utility-preserving replay scores the fictional calendar task true in A 6/6 and G 6/6; A executes the scripted synthetic email action in the Inbox fixture, while G records `REQUIRE_APPROVAL` and does not execute. Neither replay is Nemotron behavior or evidence of model exposure or comparative efficacy. Provenance and hashes are in `demo/OFFLINE_REPLAY_PROVENANCE.json` and `demo/UTILITY_REPLAY_PROVENANCE.json`. Internal raw evidence and grant records are excluded from a Git publication by `.gitignore`; regenerate fresh results in a temporary output folder when reproducing tests.
## Offline verification commands

The accepted 34/34 tests were not repeated for this presentation package. To reproduce them later with permission, use a fresh output directory outside this source tree:

```powershell
.\.venv\Scripts\python.exe -B run_offline.py --output "$env:TEMP\adr-offline-review-new" --pattern "test_stage1.py,test_p1_transport.py"
```

The existing harness denies Python socket operations and restricts child workers. It is not a universal OS sandbox. Fixtures and mocks are not model episodes. Optional existing demo logic check: `node demo/test_logic.cjs` (Node 18+); this checks navigation/fixture logic, not screenshot quality.

## Local simulated transport integration

The copied Runner and transport worker test branch were exercised against a fake HTTP server bound only to `127.0.0.1`. The subprocess worker sent the A/G calendar flow over local HTTP, verified durable Store output, and stopped on a malformed response. Its raw report is preserved internally and excluded from this source distribution. No model-generated behavior is included; the live Nebius HTTPS/TLS path was not exercised. To repeat, use a fresh output directory under the temporary folder:

```powershell
.\.venv\Scripts\python.exe -B .\diagnostics\local_transport_integration.py ..\evidence\local_transport_integration_review
```

The endpoint override is accepted only with ADR_TEST_OUTPUT enabled, and the child worker restricts it to the exact configured 127.0.0.1 host and port. A fixture token certificate is used. This is not a live execution entrypoint, does not certify B1, and cannot enable the disabled grant.

## Live runtime: exploratory route and B1 boundary

This candidate includes two intentionally separate launch paths. The default `run_approval_demo.py` uses `ScriptedModel` offline. `run_approval_live.py` remains the protocol-bound route and fails closed while `config/PROVIDER_TOKEN_BINDING.json` is `verified:false`; do not change that value. B1 remains BLOCKED.

A separate `run_approval_exploratory_live.py` is available for a future, separately authorized `EXPLORATORY_LIVE_NON_B1` run. It requires the explicit `--enable-exploratory-live` switch, a fresh reviewed grant bound to this V2 candidate and plan, current financial preflight, credential in the process environment, an empty per-session sink, and the fixed 6-request / 2-per-workflow / 8,192 locally estimated input / 1,024 output / 30-second request / 240-second session / USD 0.01 local reservation limits. The grant template is disabled; never edit it in place. The route cannot turn B1 verified and does not certify provider-side tokenization. Historical grants and evidence roots are not accepted for this candidate.

For a Windows operator, provide `NEBIUS_API_KEY` through the Windows user-environment settings or an approved local secrets manager, then open a new terminal so the process can read it. Never put the key in a command transcript, `.env` file committed to Git, grant, screenshot, or evidence log. The model is `nvidia/Nemotron-3_5-Lightning`; endpoint and tariff must be confirmed in the fresh preflight. The connected launcher and its exact arguments are in `docs/APPROVAL_WORKFLOW.md`. This path is operator-run and requires a fresh owner-reviewed grant; it is not enabled by the public static demo and is not a judge-ready hosted inference service.

Only fictional calendar and `.invalid` email tools are enabled; their effects are local fixtures. A provider response can propose a tool, but every proposal goes through the existing ADR policy and authenticated approval backend. The runtime binds only to `127.0.0.1`. The local reservation is not a provider invoice guarantee. The code at source commit `7b9a5067ab916d3f43045faf1114268a0d1a57f0` completed a separate two-request real `calendar_allow` smoke on 27 October; its bounded, read-only summary is `demo/V2_LIVE_SMOKE_SUMMARY.json`. That smoke verifies only a fictional calendar tool round trip and continuation, not calendar-query accuracy, prompt-injection resistance, B1, or production readiness. Local HTTP-mock tests are separate and are not provider requests. Installation, the offline demo, and tests do not make inferences.

## What the comparison will mean

The declared protocol pilot is **39 episodes per arm, 78 total**: 3 benign + 36 attacked per arm (3 user tasks × 6 injection tasks × 2 attack methods). A separate real 39-pair campaign is classified exploratory because B1 remains blocked; it does not close the original protocol. Neither campaign is executed by opening this demo or installing dependencies. B/C/E, non-inferiority and S2 are optional and not MVP requirements.

Utility, attacker-goal success, tool requests, execution starts and successful effects are different quantities. Indeterminate evaluation is ERROR/null and excluded from valid denominators. Native evaluator diagnostics remain separate from EV11/EV12 V2. REQUIRE_APPROVAL never implies human approval or execution. No deployment certification, causal ASR improvement or efficacy of Nemotron is claimed.

## Local human approval demo

The isolated candidate routes a replaceable model interface through the existing ADR policy and local authenticated approval service. `ScriptedModel` remains the default offline demo. A separate Nebius adapter is wired to the existing guarded `NebiusModel` and durable ADR transport; its request schema, tool history, calendar result, approval/rejection feedback and final turn were exercised only against a loopback HTTP mock. This proves the local bridge contract, not a Nebius call or Nemotron behavior. Tool effects remain simulated. Workflow turns have durable request IDs/hashes, no-retry handling for ambiguous outcomes, start idempotency and recovery bound to the exact tool call. See `docs/APPROVAL_WORKFLOW.md` for startup and tests.

In the default offline flow the adversarial tool call is predetermined, not a Nemotron-generated proposal or proof of prompt-injection success. Its payload-presence record applies only to the local scripted model input. Authentication is a single local demo password, and the service is loopback-only; this is not production identity or remote deployment.

## Historical integrated live workflow (exploratory, read-only)

On 24 October 2026, the separate isolated variant `ADR_EXPLORATORY_LIVE_NON_B1_20261024` completed six real Nebius Token Factory requests with `nvidia/Nemotron-3_5-Lightning`: fictional calendar lookup/`ALLOW`, fictional email/`REQUIRE_APPROVAL` approved into the simulated `.invalid` outbox, and a second fictional email/`REQUIRE_APPROVAL` rejected with no simulated effect. Each two-request workflow returned a model continuation. The authenticated approval/rejection was performed by an ephemeral test client, not by an owner clicking the current offline console. No real email or external tool ran.

This demonstrates live integration for those three exploratory workflows only. The rejected-email continuation suggested another calendar lookup, which did not execute. An untrusted fictional calendar description was present in the model history, but the email requests were explicitly specified by the test scenarios; this is not evidence that prompt injection caused an unauthorized action or that ADR resists prompt injection. Six responses reported 4,449 input and 269 output tokens; the public-rate cost estimate was USD 0.00033150 before tax, not a verified invoice. The original evidence remains in the separate sealed session folder. `demo/build_live_integration_summary.py` verifies its result and 19-file manifest hashes offline and builds the safe read-only summary shown in `demo/index.html`; it does not replay requests or call a provider.

## Runtime verification boundary

The original protocol entrypoint `run_approval_live.py` remains gated by B1 and stops while the binding is unverified. The V2 exploratory route is a separately activated product path; it preserves `verified:false` and records `EXPLORATORY_LIVE_NON_B1` only for provider requests. Tests with a local HTTP provider substitute record `OFFLINE_MOCK_NEBIUS_TRANSPORT_NOT_PROVIDER`. The source-derived V2 adapter, scenario-enabled workflow and explicit launcher differ from the earlier six-request bundle. The two-request smoke is a distinct, hash-linked run of this V2 source commit; it does not reproduce the six-request bundle. See `docs/PARITY_INTEGRATION_V2.md` for exact scope and changes.

## Distribution provenance

Functional source is reused from the accepted Stage 1 tree. Private historical reference inventories and personal paths in contract documentation are removed. This candidate has its **own distribution manifest**, not the original Gate A freeze. The only Python difference is the document-manifest SHA constant in `adr_gateb/design.py`; policy bytes, profile bytes, all 78 planned episode rows, runner, evaluators and B1 controls are unchanged. See `docs/DISTRIBUTION_PROVENANCE.json`. No historical checkpoints or protected experimental traces are included.

Architecture and limitations: `docs/ARCHITECTURE_AND_LIMITATIONS.md`. Release checklist: `docs/PUBLICATION_CHECKLIST.md`. Licenses: LICENSE for original ADR code and materials, and THIRD_PARTY_NOTICES.md for third-party terms. V2 is a local review candidate, not submitted; no remote or public URL is provided.

## Experimental local input counter (separate from B1)

The isolated `EXPLORATORY_LIVE_NON_B1` path uses the supplied Nebius `nemotron-input-counter-v0.3.1` package for a local admission count. Its status is **INTEGRATED — EXPERIMENTAL** in this work branch. It loads pinned tokenizer/template assets offline in a separate worker process, denies network access from that worker, and refuses dispatch when validation fails or the local count exceeds 8,192. The existing B1 `run_approval_live.py` path and `verified:false` binding are unchanged. This counter is not provider-certified; local count agreement with historical `prompt_tokens` observations does not certify future serving serialization or revisions. Do not treat it as B1 verification or as a guarantee of provider billing.

The counter worker needs its own dependency versions because its pinned Transformers/tokenizers versions differ from the main application lock. In PowerShell, prepare those packages only inside the ignored counter runtime directory:

```powershell
.\scripts\install_counter_v031.ps1
```

No live call is made by installation. The worker is prewarmed when the exploratory model is built (before the HTTP console accepts a workflow) and reused for the process session, so tokenizer initialization does not consume the first request timeout. Focused local checks:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -B -m unittest diagnostics.test_counter_v031_integration -v
```

`runtime_packages` is intentionally ignored by Git; reproduce it from the pinned `vendor/nemotron-input-counter-v0.3.1/requirements.txt`. The package archive supplied for review was not accompanied by a publisher signature; its included checksums validate the supplied files internally, not their external provenance.
