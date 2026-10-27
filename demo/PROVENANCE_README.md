# Demo provenance

`index.html` is a local offline walkthrough. Its interactive fixture is synthetic, the historical live panel is read-only, and the page makes no provider or external tool calls.

`OFFLINE_REPLAY_PROVENANCE.json` and `UTILITY_REPLAY_PROVENANCE.json` describe separate `ScriptedModel` replays; neither is Nemotron behavior. Raw replay databases, traces, grant files and campaign evidence remain in the private local evidence area and are excluded from the Git candidate. The browser page uses only the checked-in provenance summaries.

`HISTORICAL_LIVE_INTEGRATION_SUMMARY.json` is derived from the preserved six-request `EXPLORATORY_LIVE_NON_B1` session. The summary builder checks the source `RESULT.json` SHA-256, the manifest SHA-256 and each of its 19 entries before writing the safe summary and embedding it in this page. It never sends a request. The raw session remains outside the candidate repository; a user who has the private evidence may regenerate the summary by supplying its `RESULT.json` path:

```powershell
python .\build_live_integration_summary.py --result <path-to-preserved-RESULT.json>
```

The presentation reports a public-rate cost estimate, not a provider invoice. The run used a fictional untrusted calendar string, but its email flows were explicit fictional requests; it does not evidence injection-induced unauthorized behavior, prompt-injection resistance, B1 certification, production readiness, or statistical superiority. The authenticated approve/reject actions were performed by an ephemeral test client, not an owner click.
