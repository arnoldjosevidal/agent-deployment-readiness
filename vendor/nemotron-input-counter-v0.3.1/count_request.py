#!/usr/bin/env python3
"""Offline full-input counting for a bounded Nemotron serving profile.

Bounded profile checked against the public API on 2026-10-26. No requests are sent.
Exit 0: counted input fits the limit; 2: counted input exceeds it; 1: refused.
"""

import argparse
import copy
import json
import math
from pathlib import Path
import sys

from count_chat import DETAILS_WARNING, LocalCounter, MODEL, normalize_request, require, summarize_report
from serving_profile import STATUS, decode_tool_arguments, load_json, validate_json


ADAPTER_VERSION = "0.3.1"
NON_RENDERING = frozenset({
    "max_tokens", "max_completion_tokens", "temperature", "top_p", "seed",
    "n", "stream", "stream_options", "stop", "presence_penalty",
    "frequency_penalty", "logprobs", "top_logprobs", "response_format",
    "user", "store", "service_tier",
})
PINNED_FLAGS = {
    "add_generation_prompt": True,
    "continue_final_message": False,
    "add_special_tokens": False,
}
EXTRA_FIELDS = frozenset({"chat_template_kwargs", "thinking_token_budget", *PINNED_FLAGS})
EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})


def validate_non_rendering(request):
    """Reject malformed common controls; this is not a full API validator."""
    for key in NON_RENDERING & request.keys():
        value = request[key]
        if value is None:
            continue
        valid = True
        if key in {"max_tokens", "max_completion_tokens", "top_logprobs"}:
            valid = type(value) is int and value >= 0
        elif key == "seed":
            valid = type(value) is int
        elif key == "n":
            valid = type(value) is int and value == 1
        elif key in {"stream", "logprobs", "store"}:
            valid = type(value) is bool
        elif key in {"temperature", "top_p", "presence_penalty", "frequency_penalty"}:
            low, high = {"temperature": (0, 2), "top_p": (0, 1), "presence_penalty": (-2, 2), "frequency_penalty": (-2, 2)}[key]
            valid = type(value) in {int, float} and math.isfinite(value) and low <= value <= high
        elif key == "user":
            valid = type(value) is str
        elif key == "service_tier":
            valid = type(value) is str and value in {"auto", "default", "flex"}
        elif key == "stream_options":
            valid = type(value) is dict and not (value.keys() - {"include_usage"}) and all(type(v) is bool for v in value.values())
        elif key == "stop":
            valid = type(value) is list and len(value) <= 4 and all(type(v) is str for v in value)
        elif key == "response_format":
            valid = type(value) is dict and not (value.keys() - {"type", "json_schema"}) and type(value.get("type")) is str and value["type"] in {"text", "json_object", "json_schema"}
            if valid and value["type"] == "json_schema":
                schema = value.get("json_schema")
                valid = type(schema) is dict and not (schema.keys() - {"name", "description", "schema", "strict"}) and type(schema.get("name")) is str and type(schema.get("schema")) is dict
                if valid:
                    valid = (schema.get("strict") is None or type(schema["strict"]) is bool) and (schema.get("description") is None or type(schema["description"]) is str)
            elif valid:
                valid = value.get("json_schema") is None
        require(valid, f"Unsupported or invalid {key}; see the bounded input contract")


def project_request(request):
    """Return canonical rendering input without modifying the raw API request."""
    require(type(request) is dict, "Request must be a JSON object")
    validate_json(request)
    request = copy.deepcopy(request)
    allowed = {"model", "messages", "extra_body", "reasoning_effort", "tools", "tool_choice", *NON_RENDERING, *EXTRA_FIELDS}
    require(not (request.keys() - allowed), "Unsupported top-level fields: " + ", ".join(sorted(request.keys() - allowed)))
    require(request.get("model") == MODEL, f"Only model={MODEL!r} is supported")
    if "tool_choice" in request:
        require(type(request["tool_choice"]) is str and request["tool_choice"] == "auto", "Only omitted or auto tool_choice is qualified")
    validate_non_rendering(request)
    nested = request.get("extra_body")
    require(nested is None or type(nested) is dict, "extra_body must be an object or null")
    nested = nested or {}
    require(not (nested.keys() - EXTRA_FIELDS), "Unsupported extra_body fields: " + ", ".join(sorted(nested.keys() - EXTRA_FIELDS)))
    # Match inference_api.py's dictionary union: nested kwargs replace the
    # whole top-level kwargs object. Do not recursively merge its entries.
    extras = {key: request[key] for key in EXTRA_FIELDS if key in request} | nested
    # The matched gateway profile forwards this sampling-only field verbatim.
    # Validate its *effective* value after the same shallow precedence; Rust's
    # Option<i64> rejects booleans, fractional values and integers beyond i64.
    budget = extras.get("thinking_token_budget")
    require(budget is None or (type(budget) is int and -1 <= budget <= (1 << 63) - 1),
            "thinking_token_budget must be null, -1 (unlimited), or a nonnegative i64 integer")
    for key, expected in PINNED_FLAGS.items():
        if key in extras:
            require(type(extras[key]) is bool and extras[key] == expected, f"Only {key}={expected!r} is supported")
    kwargs = extras.get("chat_template_kwargs")
    # The whitelist's Optional field is omitted by exclude_none=True. Null
    # values *inside* this arbitrary dict are not removed by that operation.
    require(kwargs is None or type(kwargs) is dict, "chat_template_kwargs must be an object or null")
    kwargs = dict(kwargs or {})
    require(not (kwargs.keys() - {"enable_thinking", "force_nonempty_content"}), "Unsupported rendering kwargs")
    require(all(type(value) is bool for value in kwargs.values()), "Rendering kwargs must be boolean, not null")
    effort = request.get("reasoning_effort")
    require(effort is None or (type(effort) is str and effort in EFFORTS), "Unsupported reasoning_effort")
    if effort is not None and "enable_thinking" not in kwargs:
        kwargs["enable_thinking"] = effort != "none"
    rendering_input = {
        "model": MODEL,
        "messages": decode_tool_arguments(request.get("messages")),
        "chat_template_kwargs": kwargs,
    }
    if "tools" in request:
        rendering_input["tools"] = request["tools"]
    if "tool_choice" in request:
        rendering_input["tool_choice"] = request["tool_choice"]
    return normalize_request(rendering_input)


def evaluate_request(request, counter, input_limit=8192, *, include_details=False):
    """Count a raw request. Details opt-in includes sensitive payload and paths."""
    require(type(include_details) is bool, "include_details must be boolean")
    projection = project_request(request)
    report = {
        "adapter_version": ADAPTER_VERSION,
        "status": STATUS,
        "projection": projection,
        "provenance": counter.provenance,
        "result": counter.count(projection, input_limit=input_limit),
    }
    return report if include_details else summarize_report(report)


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project-only", action="store_true", help="Validate/project only; no token count or library load")
    parser.add_argument("--input-limit", type=int, default=8192, help="Inclusive full-input token limit (default: 8192)")
    parser.add_argument("--include-details", action="store_true", help="Include sensitive request content, token IDs and local paths")
    args = parser.parse_args()
    require(args.input_limit >= 0, "input-limit must be nonnegative")
    require(not args.project_only or args.include_details, "--project-only exposes request content and requires --include-details; it is not an input gate")
    request = load_json(args.request.read_text(encoding="utf-8"))
    projection = project_request(request)
    if args.project_only:
        output = {"adapter_version": ADAPTER_VERSION, "status": "projection-only-not-counted", "projection": projection}
    else:
        counter = LocalCounter(root / "tokenizer", root / "served_template.jinja")
        output = {"adapter_version": ADAPTER_VERSION, "status": STATUS, "projection": projection,
                  "provenance": counter.provenance, "result": counter.count(projection, input_limit=args.input_limit)}
    if args.include_details:
        print(DETAILS_WARNING, file=sys.stderr)
    else:
        output = summarize_report(output)
    encoded = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    else:
        print(encoded, end="")
    return 0 if args.project_only or output["result"]["within_input_limit"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Count refused: {exc}", file=sys.stderr)
        sys.exit(1)
