# ADR demo script — recording draft, about 2:30

**0:00–0:20 — Problem**
“Agents can read useful content that also contains untrusted instructions. Agent Deployment Readiness, or ADR, checks a proposed tool action before the tool runtime executes it. The proposal, policy decision and actual effect are recorded separately.”

**0:20–0:42 — Offline walkthrough**
“This walkthrough is synthetic and offline. Its actions are fixtures; it makes no model calls. The comparison table says NOT RUN wherever evidence is missing. The frozen S1 comparison remains unrun, and B1 remains blocked.”

**0:42–1:15 — Human decision**
“In the local approval console, ScriptedModel proposes a fictional calendar search. ADR allows the simulated read. The fixture returns marked untrusted text, then ScriptedModel proposes a fictional email. ADR holds it for approval. I sign in, review the exact action, and approve or reject it. Only the approved fictional message reaches the simulated outbox. BLOCK cannot be approved. The final response is also identified as scripted.”

**1:15–1:48 — Historical live integration**
“This read-only panel summarizes six completed Nebius Token Factory requests to NVIDIA Nemotron across three fictional workflows: a calendar read, an approved fictional email, and a rejected fictional email. Effects stayed in a simulated outbox. These saved records are not replayed here. After rejection, Nemotron suggested another calendar lookup; it was not executed.”

**1:48–2:13 — Separate exploratory observation**
“A separate exploratory matched case recorded a structured email action in A and REQUIRE_APPROVAL with no execution in G. Both episodes stopped at the request limit before a final answer. One case does not establish that the injection caused the call or that utility was preserved.”

**2:13–2:30 — Close**
“V2 includes a separately activated exploratory Nebius route, checked here against local mocks only. The six historical requests remain a separate read-only record. B1 is blocked, and this evidence does not establish prompt-injection resistance, production readiness, or statistical superiority.”

## Recording checklist

- Record the actual application running on the Windows laptop; show the main modules in action.
- Keep the labels **synthetic/offline**, **historical live/read-only**, and **exploratory** visible.
- Show the operator decision and simulated effect; do not show passwords, API keys, billing, private paths or raw evidence.
- Use fictional data, clear speech and no copyrighted music or unlicensed marks.
- Target about 2:30; final upload must be a public YouTube video under 3 minutes. Nothing has been recorded or uploaded yet.
