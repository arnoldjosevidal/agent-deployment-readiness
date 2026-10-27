#!/usr/bin/env python3
"""Offline input count for the pinned, bounded Nemotron request profile.

Bounded profile checked against the public API on 2026-10-26; never sends requests.
Use count_request.py for raw API requests and wire-format tool arguments.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

from serving_profile import MODEL, PROFILE_ID, STATUS, load_json, normalize_request, require

EXPECTED = {
    "tokenizer.json": "623c34567aebb18582765289fbe23d901c62704d6518d71866e0e58db892b5b7",
    "tokenizer_config.json": "10f93eabcb9b1602fbb991d6308e787ce1df28ee9cd7a1c6d1e8c3f338b957bc",
    "special_tokens_map.json": "e9435fefd6d838fd9fcbbc44b97a8e3ff322be7f6dfb7e4fd2468586574bb52b",
}
TEMPLATE_SHA = "17dc9cd8a6b70ec56bc2b758f9539a113ba789b5b025105234ae3aed78a5f49d"
COUNTER_VERSION = "0.3.1"
PUBLIC_REVISION = "a9904d24bcc1d289a1950fa9d2b978c47cf903b9"
EXPECTED_VERSIONS = {"transformers": "5.14.1", "tokenizers": "0.22.2", "jinja2": "3.1.6", "huggingface-hub": "1.24.0", "minijinja": "2.18.0"}

DETAILS_WARNING = "Detailed output contains request content, reversible token IDs and local paths. Treat it as sensitive; do not publish or routinely log it."


def summarize_report(report):
    """Select counts and public fingerprints without request content or paths."""
    provenance_fields = {
        "status", "counter_version", "public_artifact_revision", "model",
        "verified_model_file_sha256", "served_template_sha256", "tokenizer_class",
        "runtime_versions", "local_files_only", "trust_remote_code",
        "add_generation_prompt", "add_special_tokens", "profile_id",
        "profile_verification_date", "scope",
    }
    result_fields = {
        "status", "count", "prompt_tokens", "input_limit", "within_input_limit",
        "rendered_utf8_sha256", "rendered_prompt_sha256",
    }
    return {
        **{key: report[key] for key in ("adapter_version", "status") if key in report},
        "provenance": {key: value for key, value in report["provenance"].items() if key in provenance_fields},
        "result": {key: value for key, value in report["result"].items() if key in result_fields},
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalCounter:
    def __init__(self, model_dir=None, template=None, *, tokenizer_dir=None, template_path=None):
        root = Path(__file__).resolve().parent
        require(not (model_dir is not None and tokenizer_dir is not None), "Specify only one tokenizer directory")
        require(not (template is not None and template_path is not None), "Specify only one template path")
        model_dir = model_dir if model_dir is not None else tokenizer_dir
        template = template if template is not None else template_path
        model_dir = root / "tokenizer" if model_dir is None else model_dir
        template = root / "served_template.jinja" if template is None else template
        self.model_dir = Path(model_dir).resolve(strict=True)
        self.template_path = Path(template).resolve(strict=True)
        require(self.model_dir.is_dir(), "model-dir must be a local directory")
        require({p.name for p in self.model_dir.iterdir()} == set(EXPECTED), "Use the pinned three-file tokenizer bundle; extra files/config/templates are rejected")
        for name, expected_version in EXPECTED_VERSIONS.items():
            require(importlib.metadata.version(name) == expected_version, f"Unsupported {name} version; expected {expected_version}")
        hashes = {name: sha256_file(self.model_dir / name) for name in EXPECTED}
        require(hashes == EXPECTED, "Tokenizer/config checksum mismatch; do not use this counter")
        template_sha = sha256_file(self.template_path)
        require(template_sha == TEMPLATE_SHA, "Served-template checksum mismatch")
        self.template = self.template_path.read_text()
        # Set before importing/loading Hugging Face libraries. Never allow downloads.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(
            str(self.model_dir), local_files_only=True, trust_remote_code=False, use_fast=True
        )
        require(self.tokenizer.is_fast, "Only the local fast tokenizer is supported")
        optional = {}
        for name in ("special_tokens_map.json", "added_tokens.json", "chat_template.jinja", "vocab.json", "merges.txt", "tokenizer.model"):
            path = self.model_dir / name
            if path.is_file():
                optional[name] = sha256_file(path)
        versions = {"python": platform.python_version()}
        for name in EXPECTED_VERSIONS:
            versions[name] = importlib.metadata.version(name)
        self.provenance = {
            "status": STATUS, "counter_version": COUNTER_VERSION, "public_artifact_revision": PUBLIC_REVISION, "model": MODEL, "model_dir": str(self.model_dir),
            "verified_model_file_sha256": hashes, "served_template": str(self.template_path),
            "served_template_sha256": template_sha, "additional_local_tokenizer_files_sha256": optional,
            "tokenizer_class": type(self.tokenizer).__name__, "runtime_versions": versions,
            "local_files_only": True, "trust_remote_code": False,
            "add_generation_prompt": True, "add_special_tokens": False,
            "profile_id": PROFILE_ID,
            "profile_verification_date": "2026-10-26",
            "scope": "Full rendered prompt IDs for the bounded text and auto-function-tools profiles. Dated sample parity is documented in manifest.json. No media, assistant prefill, arbitrary kwargs or automatic live-version check. Use count_request.py for full API requests.",
        }

    def count(self, request, input_limit=8192):
        """Low-level detailed result: includes request content and token IDs."""
        require(type(input_limit) is int and input_limit >= 0, "input_limit must be a nonnegative integer")
        normalized = normalize_request(request)
        from renderer import render_prompt

        rendered = render_prompt(self.template, normalized, bos_token=self.tokenizer.bos_token, eos_token=self.tokenizer.eos_token)
        # The Rust frontend renders MiniJinja first and encodes without added
        # special tokens. Python Jinja can produce different null/bool strings.
        ids = self.tokenizer(rendered, add_special_tokens=False, return_attention_mask=False)["input_ids"]
        require(type(ids) is list and all(type(token) is int for token in ids), "Tokenizer did not return a flat integer ID list")
        rendered_sha = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        return {
            "status": STATUS, "count": len(ids), "prompt_tokens": len(ids), "tokens": ids, "token_ids": ids,
            "rendered_utf8_sha256": rendered_sha, "rendered_prompt_sha256": rendered_sha,
            "input_limit": input_limit, "within_input_limit": len(ids) <= input_limit,
            "under_3000_input_tokens": len(ids) < 3000,
            "effective_request": normalized,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input-limit", type=int, default=8192)
    parser.add_argument("--include-details", action="store_true", help="Include sensitive request content, token IDs and local paths")
    args = parser.parse_args()
    request = load_json(args.request.read_text(encoding="utf-8"))
    normalize_request(request)  # Reject unsupported input before any library load.
    counter = LocalCounter(args.model_dir, args.template)
    result = {"provenance": counter.provenance, "result": counter.count(request, input_limit=args.input_limit)}
    if args.include_details:
        print(DETAILS_WARNING, file=sys.stderr)
    else:
        result = summarize_report(result)
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(output)
    else:
        print(output, end="")
    return 0 if result["result"]["within_input_limit"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Count refused: {exc}", file=sys.stderr)
        sys.exit(1)
