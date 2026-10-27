from __future__ import annotations

import atexit
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

from adr_g64r.common import SafetyError
from adr_p1.transport import MODEL, hashed

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "vendor" / "nemotron-input-counter-v0.3.1"
WORKER = ROOT / "adr_live" / "counter_worker_v031.py"
PUBLIC_REVISION = "a9904d24bcc1d289a1950fa9d2b978c47cf903b9"
TOKENIZER_SHA256 = "623c34567aebb18582765289fbe23d901c62704d6518d71866e0e58db892b5b7"
TEMPLATE_SHA256 = "17dc9cd8a6b70ec56bc2b758f9539a113ba789b5b025105234ae3aed78a5f49d"
INPUT_LIMIT = 8192
STARTUP_TIMEOUT_SECONDS = 90
COUNT_TIMEOUT_SECONDS = 15
MAX_LINE_BYTES = 64_000
MAX_REQUEST_BYTES = 1_100_000
EXPECTED_RUNTIME_VERSIONS = {
    "transformers": "5.14.1", "tokenizers": "0.22.2", "jinja2": "3.1.6",
    "huggingface-hub": "1.24.0", "minijinja": "2.18.0",
}


class NebiusInputCounterV031:
    """Isolated persistent worker for experimental local admission checks.

    The worker is a separate, offline Python process with its own pinned
    dependencies. It returns summary-only reports and never certifies B1.
    """

    profile_id = "nemotron-lightning-input-v2"
    counter_version = "0.3.1"
    b1_verified = False

    def __init__(self):
        self._proc = None
        self._lines = queue.Queue()
        self._lock = threading.Lock()
        atexit.register(self.close)

    def _start(self):
        if self._proc is not None and self._proc.poll() is None:
            return
        if self._proc is not None:
            self.close()
        self._lines = queue.Queue()
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-S", "-B", str(WORKER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=ROOT,
                bufsize=0,
            )
        except OSError:
            raise SafetyError("INPUT_COUNTER_WORKER_UNAVAILABLE_NO_DISPATCH") from None
        self._proc = proc

        def read_lines():
            try:
                while True:
                    line = proc.stdout.readline(MAX_LINE_BYTES + 1)
                    if not line:
                        self._lines.put(None)
                        return
                    if len(line) > MAX_LINE_BYTES:
                        self._lines.put(False)
                        return
                    self._lines.put(line)
            except BaseException:
                self._lines.put(None)

        threading.Thread(target=read_lines, name="adr-counter-v031-output", daemon=True).start()
        ready = self._read_report(STARTUP_TIMEOUT_SECONDS, "INPUT_COUNTER_STARTUP_TIMEOUT_NO_DISPATCH")
        if (not isinstance(ready, dict) or ready.get("ready") is not True
                or ready.get("counter_version") != self.counter_version
                or ready.get("model") != MODEL):
            self.close()
            raise SafetyError("INPUT_COUNTER_WORKER_NOT_READY_NO_DISPATCH")

    def _read_report(self, timeout, failure_code):
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise SafetyError(failure_code) from None
        if line is None or line is False:
            self.close()
            raise SafetyError("INPUT_COUNTER_WORKER_EXITED_NO_DISPATCH")
        try:
            return json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError):
            self.close()
            raise SafetyError("INPUT_COUNTER_REPORT_INVALID_NO_DISPATCH") from None

    def prepare(self):
        """Load pinned local assets before accepting an operator workflow."""
        with self._lock:
            self._start()

    def certificate(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or payload.get("model") != MODEL:
            raise SafetyError("INPUT_COUNTER_MODEL_OR_PAYLOAD_INVALID")
        try:
            request_bytes = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                       separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            raise SafetyError("INPUT_COUNTER_PAYLOAD_INVALID_NO_DISPATCH") from None
        if len(request_bytes) > MAX_REQUEST_BYTES:
            raise SafetyError("INPUT_COUNTER_PAYLOAD_OVERSIZE_NO_DISPATCH")

        with self._lock:
            self._start()
            try:
                self._proc.stdin.write(request_bytes + b"\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self.close()
                raise SafetyError("INPUT_COUNTER_WORKER_WRITE_FAILED_NO_DISPATCH") from None
            report = self._read_report(COUNT_TIMEOUT_SECONDS,
                                       "INPUT_COUNTER_TIMEOUT_NO_DISPATCH")

        if not isinstance(report, dict) or report.get("status") != "verified-bounded-profile":
            raise SafetyError("INPUT_COUNTER_REFUSED_NO_DISPATCH")
        provenance = report.get("provenance")
        result = report.get("result")
        if (not isinstance(provenance, dict) or not isinstance(result, dict)
                or provenance.get("counter_version") != self.counter_version
                or provenance.get("profile_id") != self.profile_id
                or provenance.get("model") != MODEL
                or provenance.get("public_artifact_revision") != PUBLIC_REVISION
                or provenance.get("verified_model_file_sha256", {}).get("tokenizer.json") != TOKENIZER_SHA256
                or provenance.get("served_template_sha256") != TEMPLATE_SHA256
                or provenance.get("local_files_only") is not True
                or provenance.get("trust_remote_code") is not False
                or not isinstance(provenance.get("runtime_versions"), dict)
                or any(provenance["runtime_versions"].get(k) != v for k, v in EXPECTED_RUNTIME_VERSIONS.items())
                or not str(provenance["runtime_versions"].get("python", "")).startswith("3.12.")
                or result.get("status") != "verified-bounded-profile"
                or type(result.get("prompt_tokens")) is not int
                or result.get("input_limit") != INPUT_LIMIT
                or type(result.get("within_input_limit")) is not bool):
            raise SafetyError("INPUT_COUNTER_PROFILE_MISMATCH_NO_DISPATCH")
        if not result["within_input_limit"]:
            raise SafetyError("INPUT_LIMIT_EXCEEDED_NO_DISPATCH")

        return {
            "payload_sha256": hashed(payload),
            "model": MODEL,
            "tokenizer_revision": PUBLIC_REVISION,
            "local_template_tokens": result["prompt_tokens"],
            "upper_bound": INPUT_LIMIT,
            "headroom_tokens": INPUT_LIMIT - result["prompt_tokens"],
            "verified": False,
            "provider_binding": "EXPERIMENTAL_LOCAL_V0_3_1_NOT_PROVIDER_CERTIFIED",
            "counter_version": self.counter_version,
            "runtime_versions": provenance["runtime_versions"],
            "counter_profile_id": self.profile_id,
            "tokenizer_sha256": TOKENIZER_SHA256,
            "template_sha256": TEMPLATE_SHA256,
            "rendered_prompt_sha256": result.get("rendered_prompt_sha256"),
            "input_limit": INPUT_LIMIT,
            "within_input_limit": True,
        }

    def close(self):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            if proc.stdout:
                proc.stdout.close()
        except OSError:
            pass
