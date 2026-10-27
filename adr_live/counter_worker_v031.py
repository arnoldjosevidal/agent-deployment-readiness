"""One-request isolated worker for Nebius input counter v0.3.1.

Input is one JSON request on stdin. Output is the counter's privacy-preserving
summary only. Network connections are denied for this process.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "vendor" / "nemotron-input-counter-v0.3.1"
PACKAGES = BUNDLE / "runtime_packages"
os.environ.update({
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
})

def deny_network(*_args, **_kwargs):
    raise RuntimeError("COUNTER_NETWORK_DISABLED")

socket.create_connection = deny_network
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
sys.addaudithook(lambda event, _args: deny_network() if event.startswith("socket.connect") else None)

# -I -S leaves standard-library paths intact; only this pinned package set and
# the verified counter source are appended after the standard library.
sys.path.extend((str(PACKAGES), str(BUNDLE)))

def emit(value) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    sys.stdout.flush()

def main() -> int:
    try:
        from count_chat import LocalCounter
        from count_request import evaluate_request
        from serving_profile import load_json

        counter = LocalCounter(BUNDLE / "tokenizer", BUNDLE / "served_template.jinja")
        emit({"ready": True, "counter_version": "0.3.1", "model": "nvidia/Nemotron-3_5-Lightning"})
    except BaseException as exc:
        emit({"error": "INPUT_COUNTER_INIT_FAILED", "error_type": type(exc).__name__})
        return 1

    for raw in sys.stdin.buffer:
        try:
            if len(raw) > 1_100_000:
                raise ValueError("request-too-large")
            request = load_json(raw.decode("utf-8"))
            report = evaluate_request(request, counter, input_limit=8192)
            summary = {
                "status": report.get("status"),
                "provenance": report.get("provenance"),
                "result": report.get("result"),
            }
            emit(summary)
        except BaseException as exc:
            # Do not echo exception messages, request content, paths, or IDs.
            emit({"error": "INPUT_COUNTER_REFUSED", "error_type": type(exc).__name__})
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
