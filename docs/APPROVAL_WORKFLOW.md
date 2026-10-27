# Local human-approval workflow

The isolated candidate has a runnable local operator console. The integrated flow routes scripted model-interface proposals through the candidate's unchanged `adr_gateb.Policy`, the authenticated approval backend, a SQLite-backed simulated runtime and a persisted conversation transcript.

## Run on Windows

From the repository root:

```powershell
python -B .\run_approval_demo.py --db "$env:TEMP\adr-approval-demo-manual.sqlite3" --port 8766
```

Choose a password of at least 16 characters at the hidden terminal prompt. Open `http://127.0.0.1:8766/` in the same computer's browser and sign in with that password. Port 8766 keeps this approval console separate from the presentation demo currently served on 8765. Stop the service with Ctrl+C. Keep the SQLite database if you want to inspect the local audit later; delete it yourself when you no longer need the demo state.

## Offline integrated flow

1. Choose **Start integrated agent → ADR flow**. The existing finite `ScriptedModel` fixture proposes a fictional calendar search.
2. The actual candidate policy returns `ALLOW`; the simulated calendar runtime returns a fictional event whose description contains an explicitly marked untrusted attack string.
3. The scripted fixture receives that tool result in its next model-interface request and emits a predetermined `send_email` tool call. The backend evaluates that exact proposal and returns `REQUIRE_APPROVAL`; the pending action is durably stored and has no effect yet.
4. Review the exact tool, arguments, destination, reason, immutable action fingerprint and expiry. Approve or reject as the authenticated local operator. Approval writes only to the simulated `.invalid` outbox; rejection records a denial and causes no message effect.
5. The decision result is added to the persisted transcript and the scripted model interface continues to a final response. The UI shows tool results, request hashes, whether the untrusted string was present in the local model input, and the final task state.
6. Use **Try file access** separately to confirm policy `BLOCK`; it cannot be approved.

For a quick manual UI check of all four outcomes, sign in and click **Read calendar (ALLOW)** once; confirm its simulated result. Click **Propose email (REQUIRE_APPROVAL)** and reject it; confirm the action has no effect. Click **Propose email (REQUIRE_APPROVAL)** again and approve the exact action; confirm one fictional `.invalid` outbox entry. Then click **Try file access (BLOCK)** and confirm the card says it is not eligible for approval and offers no approval buttons. Finally use **Start integrated agent → ADR flow**, approve the pending email, and confirm the workflow shows the resumed final `ScriptedModel` response. Start that integrated flow again and reject the pending email to confirm its rejection continuation. These are offline fixture interactions, not Nemotron outputs.

The default integrated workflow is an **offline scripted demonstration**, not a Nemotron call and not evidence that a model was successfully attacked. Its model proposal is predetermined by the fixture. The request hashes and payload-presence check describe data passed to the local scripted interface, not transmission to any provider. The standalone calendar/email/file controls are operator fixtures.

## B1-bound protocol bridge

`adr_approval.NebiusApprovalModel` adapts the existing guarded `adr_live.NebiusModel` to the approval workflow. Model responses are parsed into the same `Frame` contract as the offline model. The workflow sends every single tool call through the actual candidate policy; `ALLOW` and `BLOCK` results are returned to the model, `REQUIRE_APPROVAL` pauses for the authenticated operator, and the decision result is returned for a final model turn. Tool effects remain limited to the simulated local runtime. Multiple calls in one provider response, malformed arguments, and unknown outcomes fail closed without retry.

The bridge was exercised end to end against a loopback HTTP mock using the real ADR `Transport` and `wire_worker`: request schemas, tool-call parsing, the untrusted calendar tool result in the next request, simulated approval and rejection, final responses, usage persistence, and `Store.verify()` were checked. This is mock HTTP evidence only. The test counter is explicitly injected under `ADR_TEST_OUTPUT`; it does not validate the provider's tokenizer or B1.

The separate entrypoint is `run_approval_live.py`. It requires a new approved grant, a fresh evidence root, the current process environment key, a matching candidate/config hash, no retries, local request/time/budget caps, and the accredited binding. The current `config/PROVIDER_TOKEN_BINDING.json` has `verified:false`, so startup stops at B1 before the sink is created or any request can be sent. Do not edit the binding flag to enable it. No live grant is included in this candidate.

```powershell
python -B .\run_approval_live.py --grant <new-approved-grant.json> --evidence-root <fresh-evidence-directory> --db <new-approval.sqlite3> --port 8766
```

This command is not usable until a separate live authorization and B1 evidence exist. It does not use the old laboratory or campaign grants.

## Separate exploratory product route (B1 stays blocked)

V2 also contains `run_approval_exploratory_live.py`. It is a distinct product-integration path, not a B1 bypass: `config/PROVIDER_TOKEN_BINDING.json` stays `verified:false`, every request is classified `EXPLORATORY_LIVE_NON_B1`, and the runtime reports `b1: BLOCKED` and `provider_input_bound_certified: false`. The launcher requires the explicit `--enable-exploratory-live` flag plus a fresh owner-reviewed grant; live mode is not the default. The checked-in `config/EXPLORATORY_LIVE_GRANT_TEMPLATE_DISABLED.json` is not a grant and must never be edited in place or enabled.

The route is limited to three fictional workflows (`calendar_allow`, `email_approve`, `email_reject`), at most two requests each and six total, zero retries, local estimate up to 8,192 input / 1,024 output tokens, 30 seconds per request, 240 seconds per session and USD 0.01 local reservation. It requires a current `Independent-y4p` financial preflight, current public-price record, approved exception or verified-disabled Auto Top-up, process credential, fresh session and empty sink. These local controls do not guarantee the provider's final invoice and the input estimate does not resolve B1. Historical grants and evidence paths are not reusable.

On Windows, provision `NEBIUS_API_KEY` using the account's environment-variable settings or an approved local secrets manager, then start a fresh terminal. Do not place the value in a command line, repository file, grant, screenshot, or log. Verify presence without printing the value. Confirm the selected model, endpoint, current tariff and billing preflight against the provider console before a separately authorized run.

After a separate live authorization and preflight, the launcher form is:

```powershell
python -B .\run_approval_exploratory_live.py `
  --enable-exploratory-live `
  --grant <fresh-reviewed-grant.json> `
  --evidence-root .\evidence\exploratory_live_non_b1_v2\sessions\<grant-session-id>\sink `
  --db <private-fresh-session-database.sqlite3> `
  --port 8767
```

The evidence path must be empty and its session ID must match the grant. The server binds to loopback and still prompts for a local operator password; no tool reaches a real calendar, mailbox, filesystem or external service. Do not run this example without a newly authorized grant and fresh preflight. This work did not create an active grant or make a provider request.

`python -B -m unittest diagnostics.test_exploratory_live_non_b1 -v` tests the three workflows against a loopback provider mock. Test records are labeled `OFFLINE_MOCK_NEBIUS_TRANSPORT_NOT_PROVIDER`; these are not live calls. The offline demo stays on `ScriptedModel` and cannot start the exploratory route by environment flag alone.

## Safety and integrity

- The server refuses non-loopback binds. It makes no provider calls and exposes no real calendar, email, file or external tool.
- The operator password is entered with hidden terminal input, used to derive an in-memory verifier, and never persisted. The session cookie is HttpOnly and SameSite Strict; decision routes require same-origin requests and a CSRF token.
- Pending approval is bound to the canonical action hash and workflow/call IDs. Only `REQUIRE_APPROVAL` is approvable. Decisions are single-use; expiry, replay, altered fingerprints, unauthenticated decisions and policy `BLOCK` fail closed.
- Workflow state and transcript are stored in SQLite with a SHA-256 integrity check. A pending workflow survives process restart. A terminal decision resumes the scripted continuation after restart without re-executing the action, including recovery if the process stops after the decision has committed.
- The simulated effect and terminal action status are committed in one local database transaction. Execution errors or restart during execution become `execution_unknown`; no retry occurs.
- The audit log is a SHA-256 chain. The tests exercise approval, rejection, restart, duplicate resume, tampering and unknown execution.

Run the local regression suite from `engine`:

```powershell
python -B -m unittest diagnostics.test_approval_workflow diagnostics.test_approval_e2e diagnostics.test_approval_model_flow diagnostics.test_approval_nebius_bridge diagnostics.test_live_runtime_gates -v
```

## Boundary

The local operator account is a single password-authenticated demo identity, not an enterprise identity provider or OS account. HTTP is loopback-only and not suitable for remote or production deployment. The workflow does not resume the frozen experiment Runner. The default mode makes no model calls. The protocol-bound `run_approval_live.py` remains blocked by B1; the separate exploratory launcher has no approved grant in this candidate. This closure made no Nebius inference or new experimental result.

UI de continuidad: al aprobar/rechazar, la tarjeta de workflow sincroniza el estado integrado y presenta la respuesta final explícitamente marcada como `ScriptedModel` offline. Guía de prueba en la UI local, no requiere inferencia.


## Static walkthrough preview

From the repository root, run `python -B -m http.server 8767 --bind 127.0.0.1 --directory .\demo` and open `http://127.0.0.1:8767/` in a browser on the same Windows host. This binds to loopback only; stop it with Ctrl+C. The Work in-app browser may not share the host loopback. If so, use the Windows desktop browser on the same computer or open `demo/index.html` directly from disk. The static walkthrough does not call the approval backend or any provider.
