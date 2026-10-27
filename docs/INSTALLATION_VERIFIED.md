# Clean Windows installation — verified 18 October 2026

A new isolated virtual environment was created with Python 3.12.10 and system site packages disabled. All 72 existing pinned dependency versions installed successfully from public PyPI wheels and matched the lock. `python -m pip check` returned no broken requirements. No packages were copied from the operational environment and no dependency pins changed.

The minimal offline startup smoke loaded the documentary manifest, the S1-only AgentDojo facade and 24 tool schemas, local tokenizer, empty SQLite/trace/CSV store and zero-budget transport. The provider binding remained false, and no model request or episode was run. The accepted 34/34 and historical 216/216 suites were not repeated.

## Reproduce the setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated --disable-pip-version-check install --no-input --only-binary=:all: --index-url https://pypi.org/simple -r requirements-windows-py312.lock.txt
.\.venv\Scripts\python.exe -m pip --isolated --disable-pip-version-check check
```

For the no-service product walkthrough, open `demo/index.html` directly. Do not set a real API key or change either authorization/provider-binding flag to review the software. The full real-run entrypoint remains disabled pending B1 evidence and explicit human authorization.

See CLEAN_INSTALL_EVIDENCE.json for a public-safe record. Detailed installation logs and the isolated environment stay outside the public repository. The lock's original comments describe its capture on 16 October; this document records the later installation result. No wheel-hash lock, portable bundled runtime, real-provider validation or deployment certification is claimed.
