# Devpost submission draft — Agent Deployment Readiness (not submitted)

**Project title:** Agent Deployment Readiness (ADR)
**Tagline:** Inspectable policy decisions and human approval for AI-agent tool actions.
**Proposed track:** Best Apps and Agents (owner confirmation required).

## Project description

ADR places an independently defined policy engine between an agent’s proposed tool call and the tool runtime. It records the proposal, decision, human review and execution separately. `ALLOW` proceeds, `BLOCK` stops, and `REQUIRE_APPROVAL` holds the exact action for an authenticated operator. A local approval console demonstrates approval, rejection and continuation using fictional calendar/email data and a simulated SQLite runtime.

A separate isolated variant completed six real Nebius Token Factory requests to NVIDIA Nemotron across three fictional workflows: calendar lookup, approved fictional email and rejected fictional email. The saved panel is read-only; it does not replay or create provider calls. Approval was performed by an ephemeral authenticated test operator, not by the project owner. After rejection, the model proposed another calendar lookup that was not executed.

One separate exploratory matched case recorded a structured fictional email action in A and `REQUIRE_APPROVAL` with no execution in G. Both episodes ended at a request limit before a final response. This single observation does not establish that prompt injection caused the action, preserve utility or show statistical superiority. B1 remains blocked for the original protocol. The V2 candidate includes a separate, explicitly activated `EXPLORATORY_LIVE_NON_B1` route and completed a two-request real `calendar_allow` smoke; its three approval workflows were validated separately against local HTTP mocks. The smoke demonstrated a fictional calendar tool proposal, ADR `ALLOW`, a simulated tool result in the follow-up request, and a model final response, with a known fixture-date mismatch. It does not establish calendar accuracy, prompt-injection resistance, B1 or production readiness. See `demo/V2_LIVE_SMOKE_SUMMARY.json`. The historical six-request evidence remains separate.

## Demo instructions

The offline walkthrough is `demo/index.html`; it is synthetic except for the clearly labeled read-only historical evidence summary. For an interactive local approval flow, run `python -B .\run_approval_demo.py --db "$env:TEMP\adr-approval-demo-manual.sqlite3" --port 8766` from the repository root, choose a temporary local password of at least 16 characters, then open `http://127.0.0.1:8766/`. All proposed tool effects are simulated. The offline demo makes no provider calls. The separate live launcher is disabled by default and is not part of this public walkthrough.

## Built with and significant updates

Python 3.12, AgentDojo components, SQLite, an independently defined policy engine, Nebius Token Factory and NVIDIA Nemotron 3.5 Lightning. During the submission period ADR gained a frozen S1 contract, an isolated A/G runner and analysis, durable decision/evidence handling, an authenticated offline approval workflow, and a hash-linked exploratory live integration record. V2 includes the exploratory integration code, but its live adapter was validated only against local mocks in this build. The historical six-request session is separate from the distribution build and is not B1 certification.

## Feedback draft for owner review

The six-request integration showed that the Token Factory endpoint could complete these bounded fictional tool workflows. For repeatable prompt budgeting, a documented preflight counter bound to the exact serving tokenizer, chat template, tool schemas and full conversation would be valuable. Billing totals should remain easy to distinguish from per-request usage and estimates. This is project feedback for owner review; it has not been submitted.

## Required submission fields

- Public source repository with license and README: **PENDING**
- Public demo/test-build URL with free, unrestricted judge access through the judging period: **PENDING**
- Public YouTube video under three minutes showing the app running: **PENDING**
- Track: **Best Apps and Agents proposed; owner confirmation pending**
- Nebius/NVIDIA feedback: **draft above; owner review pending**
- Prior-project significant updates: **draft above**
- English description and testing instructions: **drafted; V2 offline/mock integration verified, no V2 provider request**
- Entrant fields, public links, and final Devpost submission: **PENDING**

Local draft only. Not published or submitted. V2 has a guarded exploratory launch path, but there is no public URL and the required judge-facing live behavior has not been exercised from this build. No B1, security-efficacy or production claim is made.
