# Demo recording and review notes

The static walkthrough is `demo/index.html`. Its showcase labels synthetic offline fixtures, historical live read-only evidence and exploratory observations separately. It makes no inference calls. The integrated approval console is a separate offline `ScriptedModel` fixture. Authenticate locally, show a pending fictional email, approve or reject it, and show the backend-recorded decision, simulated effect and final scripted response.

The six-request historical panel shows three workflows from a separate isolated variant. It is read-only and uses a sanitized hash-verified summary. Approval and rejection in that historical run were performed by an ephemeral authenticated test operator, not by the owner. A rejected workflow proposed another calendar lookup; that lookup did not execute. This supports only the recorded integration behavior.

A separate matched R6 case may be mentioned as one exploratory observation: A executed a structured fictional email action and G retained it with `REQUIRE_APPROVAL`; both stopped before a final answer. Do not claim injection causality, utility preservation, general protection or superiority.

## Local review steps

1. From the `engine` directory, run `python -B .\run_approval_demo.py --db "$env:TEMP\adr-approval-demo-manual.sqlite3" --port 8766`.
2. Choose and confirm a temporary password of at least 16 characters at the hidden prompt. The server binds to `127.0.0.1` only.
3. Open `http://127.0.0.1:8766/` on the same Windows computer. Confirm the banner says `OFFLINE · ScriptedModel` and that tools/data are simulated.
4. Start the integrated workflow. Inspect the pending action, approve it once, and confirm the outbox contains only the fictional `.invalid` destination and the final response is marked `ScriptedModel`. Restart with a fresh temporary database to test the rejection path.
5. To preview the static evidence walkthrough from `engine`, run `python -m http.server 8767 --bind 127.0.0.1 --directory .\demo`, then open `http://127.0.0.1:8767/`. Stop with Ctrl+C. This server is loopback-only. The Work browser could not reach a server launched in its isolated shell, so use the Windows browser on the same host if that limitation persists.

For recording, use the shortened `DEMO_SCRIPT_3MIN_EN.md` (target about 2:30), show the project running on the laptop, keep evidence labels visible, use fictional data, and avoid credentials, billing, private paths, raw traces, copyrighted music and unlicensed marks. Video remains unrecorded and unpublished.
