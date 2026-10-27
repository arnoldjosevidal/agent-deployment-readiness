# Nemotron local input counter — v0.3.1

Counts the complete rendered input for `nvidia/Nemotron-3_5-Lightning`, including the supported function-tool definitions, assistant tool calls, tool results, conversation text, special tokens and assistant generation prefix. No model weights or GPU are needed. Counting runs locally and sends no requests.

This release covers the supplied initial and tool-history payload shapes. It uses the serving engine's MiniJinja 2.18.0 renderer and pinned tokenizer/template assets. It does not estimate a fixed per-tool overhead.

## Quick start

Python 3.12 was tested. Install the fixed dependencies once (network access is needed for installation), then counting works offline:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python count_request.py --request example-tool-history.json --input-limit 8192
```

Replace the example with the complete JSON request you intend to send. Keep object/key order, tool schemas, messages and raw argument strings unchanged. The counter normalizes a private copy; send the original request, not the normalized projection in the output.

The default result is a summary containing `prompt_tokens`, `input_limit`, `within_input_limit`, public asset fingerprints and a rendered-prompt SHA-256. `count` is an alias of `prompt_tokens`. It excludes request content, token IDs and local filesystem paths.

Use `--include-details` only for private debugging. Detailed output contains the full normalized request, reversible token IDs and local filesystem paths; do not publish it or routinely log it. `evaluate_request()` also returns a summary by default; `include_details=True` opts into sensitive details. The lower-level `LocalCounter.count()` and projection helpers return detailed data and should not be logged directly.

| CLI exit | Meaning | Caller action |
| --- | --- | --- |
| 0 | Count succeeded and input is at or below the limit | Eligible under this local input check |
| 2 | Count succeeded but input exceeds the limit | Do not send |
| 1 | Invalid/unsupported input, mismatched assets/dependencies or another counting error | Do not send |

`--project-only --include-details` validates and projects without counting. It exposes request content. Its exit code 0 is **not** an admission decision. Do not use it as an input gate.

## Use in an application

Run from this bundle directory or add it to your Python import path:

```python
from pathlib import Path
from count_chat import LocalCounter
from count_request import evaluate_request
from serving_profile import load_json

counter = LocalCounter()  # Reuse this instance across requests.
request = load_json(Path("request.json").read_text(encoding="utf-8"))
report = evaluate_request(request, counter, input_limit=8192)
if not report["result"]["within_input_limit"]:
    raise ValueError("Full input exceeds 8192 tokens; request not sent")
# Only here may your application submit the original `request`.
# Let any counting/validation exception stop dispatch as well.
```

The limit is inclusive: 8,192 passes; 8,193 fails. No messages or tokens are shortened to fit. This limit counts **input only**; it does not include reserved/generated output or impose a model context-window limit. Cached tokens remain part of the full input count.

## Verification on October 26, 2026

Four previously recorded calls to `https://api.tokenfactory.nebius.com/v1/chat/completions` matched local counts. The corrected v0.3.1 code was replayed offline against those same requests and preserved the full token IDs and rendered-prompt hashes:

| Input | Local count | API `usage.prompt_tokens` |
| --- | ---: | ---: |
| Supplied initial request, 24 tools | 4,340 | 4,340 |
| Supplied request with tool history | 4,436 | 4,436 |
| Full tools/history boundary | 8,191 | 8,191 |
| Full tools/history boundary | 8,192 | 8,192 |

The 8,193-token boundary was rejected locally and was not dispatched. The earlier API verification changed only `max_tokens` to 1, after confirming the rendered input was unchanged; it did not test output quality or execute tools. The local regression suite also covers prior text fixtures, nested arguments, ordering, parallel/multiple tool rounds, negative-zero refusal and report privacy. Test totals are recorded in `validation-summary.json`. No new API calls were made for this correction.

These are dated sample checks, not a guarantee about every serving replica, region or future request. The manifest identifies the bundled tokenizer and template; it is not a live endpoint version handshake. See `manifest.json` and `validation-summary.json`.

## Scope and remaining gaps

Read `request-contract.md` before integration. Function tools with `tool_choice` omitted or `"auto"` and omitted `parallel_tool_calls` are supported, including the supplied tool-history request. This profile accepts at most 100 messages, independently of the token limit. Unsupported shapes are rejected rather than estimated.

Not supported in this profile: media, assistant prefill, separate reasoning-history fields, other tool-choice modes, explicit `parallel_tool_calls`, arbitrary template settings, or floating-point values inside tool schemas/decoded arguments. Raw tool-argument numbers written as `-0` are also refused: the serving parser treats them as floating-point negative zero. String values such as `"-0"` and ordinary integer `0` remain supported. Nested JSON-schema structures are preserved, but the counter is not a complete API or schema validator.

The local assets and dependency versions are checked. **Automatic detection of server-side tokenizer/template/default/serialization changes is not provided.** Revalidate or replace the bundle when a relevant serving change is announced. There is no built-in notification channel or endpoint version handshake.

Your application must enforce the local decision before dispatch. This bundle does not create a provider-side custom cap or a reject-before-inference/no-charge billing guarantee for requests that are sent.

## Changes from v0.3.0

- Closes an undercount edge by refusing numeric `-0` inside raw historical tool arguments before its sign can be lost, including nested arrays and objects.
- Makes CLI and `evaluate_request()` output summaries by default; sensitive diagnostics require explicit opt-in.
- Removes unnecessary operational details and personal archive metadata from the customer package.

Use v0.3.1 instead of v0.3.0. The tokenizer/template bytes and counts for the recorded customer and boundary cases are unchanged.

## Tools support added since v0.2.1

- Mirrors engine normalization of function definitions, including optional fields, and decodes historical tool arguments once while preserving JSON order.
- Adds complete tool-result rounds and the tools-auto default behavior.
- Uses MiniJinja instead of Python Jinja: equal counts alone can hide different rendered scalar values and token IDs.
- Adds the inclusive input gate and explicit refusal/over-limit exit codes.

Tokenizer/template bytes are unchanged. v0.2.1 remains a separate text-only bundle. No production endpoint or engine changes were required for this local extension.
