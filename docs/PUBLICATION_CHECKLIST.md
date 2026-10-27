# Release checklist — review candidate

Official rules reviewed 24 October 2026: https://nebiusglobalaihackathon.devpost.com/rules

## V2 release status — 27 October 2026

- [x] V2 candidate contains the offline ScriptedModel demo and a separate guarded `EXPLORATORY_LIVE_NON_B1` Nebius/Nemotron approval route. The live route is disabled by default, requires explicit `--enable-exploratory-live`, a fresh reviewed grant and current preflight; no active grant is included.
- [x] Three fixed fictional workflows passed against a local HTTP mock. These are offline integration tests, not provider use. Separately, source commit `7b9a5067ab916d3f43045faf1114268a0d1a57f0` completed a two-request real `calendar_allow` smoke; see `demo/V2_LIVE_SMOKE_SUMMARY.json`. Historical six-call evidence remains separate and read-only.
- [x] B1 remains BLOCKED; `verified:false` and the protocol-bound `run_approval_live.py` remain intact. No B1 or efficacy claim is made.
- [x] README, Windows startup/test commands, MIT license and third-party notices are present. No dependency was added. Existing Python 3.12.10 / 72-pin clean-install evidence applies to the unchanged lock; this closure reused the isolated environment and `pip check` passed.
- [x] The bounded V2 calendar smoke received two real model responses, passed the fictional calendar ALLOW/tool/continuation checks, and has durable hash-linked evidence. It does not establish calendar-query accuracy, prompt-injection resistance, B1 or production readiness; billing was estimated, not invoice-verified.
- [ ] Screenshot-level UI review in the owner's Windows browser remains outstanding. The available in-app browser cannot reach the loopback server launched in the restricted shell; the owner should perform the short same-device review below.
- [ ] Public source repo, free unrestricted judge test-build URL through 15 December 2026, and public YouTube video under three minutes remain unpublished/unavailable.
- [ ] Confirm track, entrant fields and final Devpost content; review the prepared feedback/significant-updates text. No submission has been sent.
- [x] Source candidate is commit `7b9a5067ab916d3f43045faf1114268a0d1a57f0` on `adr/counter-v031-experimental-20261027` (275 tracked files; clean; no remote). The public release copy is a documentation-only package derived from that exact tree; its own local commit and tree hash are recorded in the private reconciliation handoff.

## Official requirement status (evidence boundary)

- [x] Runtime use of Nebius Token Factory and NVIDIA Nemotron is evidenced in the separate isolated candidate: six complete real requests across three workflows. Evidence is explicitly exploratory and hash-linked in `demo/HISTORICAL_LIVE_INTEGRATION_SUMMARY.json`. This does not certify B1 or production readiness.
- [x] V2 contains a distinct, explicit `EXPLORATORY_LIVE_NON_B1` runtime path alongside the offline ScriptedModel path. The live adapter passed local HTTP mocks and the separately summarized two-request calendar smoke. The historical six-request record remains separate. B1 remains BLOCKED and `verified:false`.
- [x] A local offline test build and an authenticated local approval console are prepared; both use fictional data/tools and make no external calls in their default mode.
- [x] English project description, reproducible setup/run guidance, source, required assets, MIT license and third-party notices are prepared. Python 3.12.10 clean-install evidence from 18 October records all 72 pinned versions and `pip check` PASS; no dependencies were changed in this closure.
- [x] A local read-only summary of the integrated live run is reproducible from the preserved result: its builder verifies the source RESULT hash and all 19 session-manifest entries, and makes no network calls.
- [x] V2 is a local Git repository with the commit above; the final staged-content scan found no credential-like patterns, private Windows paths, or protected raw evidence. No remote is configured.
- [ ] Public source repository with a visible open-source license and complete source/assets/instructions.
- [ ] Public demo, hosted app or test-build URL with free, unrestricted judge access through the judging period ending 15 December 2026.
- [ ] Public YouTube video under three minutes, showing the app running on its intended device. A ~2:30 narration draft is prepared; no video has been recorded.
- [ ] Select the hackathon track and complete required English project description/testing instructions.
- [ ] Provide feedback on Nebius Token Factory / AI Cloud and NVIDIA tools/models used.
- [ ] Explain significant updates made during the submission period because ADR predates it.
- [ ] Complete and verify all required entrant and Devpost fields.

Current disposition: **local candidate ready for final owner review; not ready to submit**. V2 has a separately guarded exploratory live route, but this exact build has only mock-tested that route; do not claim exact parity with the historical live bundle. The protocol binding remains `B1 BLOCKED` and is a disclosed technical limitation, not a hackathon rule. Public repository/demo links, the recorded public video, final Devpost fields and owner authorization for publication/submission remain pending.

- [x] Source, setup/run guidance, version pins and origin/license notices prepared.
- [x] Existing demo keeps simulated/historical/experimental classes distinct.
- [x] A bounded scan of the local code/demo candidate found no credential-like filenames or credential-pattern matches (284 files scanned); environments, caches and runtime/private files were excluded. The closed campaign evidence and live raw trace remain in their protected source folders, outside the distributable candidate.
- [x] Public documentary manifest distinguished from original Gate A; operational inputs unchanged.
- [x] Owner approved MIT for original ADR material and the local candidate LICENSE was created with the authorized copyright holder/year; third-party terms remain separate.
- [x] Fresh Windows installation verified 18 October: 72 exact versions, pip check PASS and six minimal startup checks; no accepted suite replay.
- [x] Real Nebius/Nemotron use is recorded for the six-call exploratory integration milestone. B1 remains blocked for the original protocol; no protocol-confirmatory 39+39 pilot, production certification or general security claim is made.
- [ ] Record and review the Windows demonstration; publish repository, test build/demo and video only with authorization.
- [ ] Supply and verify public links, English materials, track, feedback and entrant details; provide judges' free access through judging end.

No publication or submission is authorized by this file. MIT applies locally to original ADR material; public release contents and publication still require approval. Source distribution checks are scoped packaging checks, not a new general security audit or experimental gate closure.

## 24 October review addendum

The Work browser displayed the `OFFLINE · ScriptedModel` approval-console login at both `127.0.0.1:8765` and `:8766`; it did not show the static walkthrough. Windows did not expose an identifiable listener for those ports. A loopback-only static server launched from the restricted Work shell could not be reached by that browser, so visual rendering of `demo/index.html` remains unverified. Local preview instructions are in `docs/APPROVAL_WORKFLOW.md`; do not expose a private server publicly to work around this limitation.

The live runtime source and distribution candidate are not byte-identical. The historical exploratory transport/runtime components are absent from the distribution, and four related runtime modules differ; the candidate restores B1 fail-closed behavior. Do not claim the distribution reproduces the historical six-call run. Details are recorded in the private `mi_agente` review package, not bundled with public source.

## 25 October final-submission preparation
- [x] Confirmed the official Devpost requirements: a working project using Nebius Token Factory or AI Cloud and an NVIDIA open model; a working demo/test-build URL with free, unrestricted judge access through the judging period; a public open-source repository with visible license and README/setup instructions; a public YouTube demo under three minutes showing the app running; an identified track; feedback on Nebius/NVIDIA tools; and an explanation of significant updates. Source: [official rules](https://nebiusglobalaihackathon.devpost.com/rules).
- [x] The static `demo/index.html` is self-contained: its CSP denies network connections (`connect-src 'none'`), it has no provider/backend integration, and its embedded historical panel is read-only. Proposed public route after repository publication: `https://<github-account>.github.io/<repository>/demo/` when Pages serves the repository branch root. This URL is a template, not a live link; Pages is not enabled.
- [x] V2 source candidate is branch `adr/counter-v031-experimental-20261027`, commit `7b9a5067ab916d3f43045faf1114268a0d1a57f0`, with 275 tracked files and no remote. Its parent/recovery point is `f6cd1b179ec992ef09ac1106783ceeec5eb205f5`. The release-copy manifest covers the packaged files and is distribution provenance, not an experimental freeze.
- [x] The video script and recording notes are prepared in `demo/DEMO_SCRIPT_3MIN_EN.md` and `demo/RECORDING_NOTES.md`. The narration targets about 2:30, calls the offline approval flow scripted, treats the six Nebius/Nemotron requests as historical read-only evidence, and states that the exploratory matched case does not prove injection causality or utility preservation. No video has been recorded.
- [x] Owner reports a manual Chrome review of the static V2 demo: it loads, Attack/Harden/Decide work, and the synthetic record shows ALLOW/BLOCK/REQUIRE_APPROVAL. This is owner-reported visual verification, not a new local screenshot or live-model run. The authenticated local approval console's full manual walkthrough remains separate from this static-page check.
- [ ] Public source repository, public static demo URL, public YouTube video, Devpost entrant fields and submission remain unpublished/unsubmitted. Recommended track is **Best Apps and Agents**; owner selects it on Devpost.
- [ ] The official runtime-use requirement is supported by the separately documented two-request V2 smoke and six-request exploratory evidence, subject to the rules' exact interpretation and the absence of public deployment. This is not a claim of B1 compliance or security efficacy; confirm the final submission against the rules before sending.

Minimum proposed V2 validation before submission: one fresh owner-reviewed grant bound to the reviewed candidate and plan; run only the fictional `calendar_allow` workflow (two sequential provider requests maximum, no retries), with 8,192 locally estimated input / 1,024 output tokens per request, 30 seconds per request / 240 seconds total, and a USD 0.01 local reservation cap. A rough USD 0.00011 estimate is the arithmetic mean of the separate historical six-request estimate, not a current quote or invoice guarantee; confirm current price and billing preflight before execution. Pass requires a real provider response, a model-proposed calendar tool call, the simulated lookup result in the next model request, a final model response, and verified durable evidence. Any transport ambiguity, unexpected tool, missing continuation, usage uncertainty, or limit breach stops without retry. This validates only V2's basic runtime integration, not B1 or prompt-injection efficacy. No such run is authorized or performed here.

### Owner's final actions

1. Run the local commands in `demo/RECORDING_NOTES.md` and review the four offline paths on the Windows browser: calendar `ALLOW`, email approval, email rejection, and file-access `BLOCK`.
2. Create a public repository and publish the reviewed V2 branch. In **Settings → Pages → Build and deployment**, choose **Deploy from a branch**, branch `adr/adaptive-live-v2`, folder `/(root)`. The judge URL will be `https://<github-account>.github.io/<repository>/demo/`; verify it in a signed-out browser and confirm no outbound requests are made. Keep the repository and Pages site public and available through 15 December 2026.
3. Record the application on the Windows device using the prepared script; confirm the YouTube upload is public and under three minutes.
4. Fill the public repository, demo and video URLs plus entrant fields and feedback in Devpost, review the final entry, and submit before the deadline.
