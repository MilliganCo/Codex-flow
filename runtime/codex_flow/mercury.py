"""Opt-in, free-only bridge to the user's existing Harness2 Mercury adapter.

No provider implementation, credential, or upstream source is redistributed here.
The caller explicitly selects a trusted external installation. Disabled routing has
no filesystem, credential, subprocess, or network side effects.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable


MODEL = "inception/mercury-decide:free"
BUILD = "inception/mercury-decide-20260930"
PARALLEL_THRESHOLD = 0.75
SINGLE_THRESHOLD = 0.25
MAX_OUTPUT_BYTES = 256 * 1024
# Import the existing adapter rather than its CLI entry point. Its Windows CLI
# calls process.exit() in a stdout callback; natural exit avoids closing libuv
# handles while they are still active. No external source is changed or copied.
NODE_WRAPPER = r"""
const {evaluate} = await import(process.argv[1]);
let text = '';
process.stdin.setEncoding('utf8');
for await (const chunk of process.stdin) {
  text += chunk;
  if (Buffer.byteLength(text) > 65536) throw new Error('input_too_large');
}
let result;
try {
  result = await evaluate(JSON.parse(text), process.env.OPENROUTER_API_KEY);
} catch {
  result = {status:'REJECTED', reason:'invalid_input', inference_attempts:0};
}
process.stdout.write(JSON.stringify(result) + '\n');
"""
SAFE_ENUMS = {
    "complexity": {"low", "medium", "high", "simple", "moderate", "complex"},
    "risk_level": {"low", "medium", "high", "critical"},
}


def _abstract_state(state: dict) -> dict:
    """Copy only bounded facts; never forward arbitrary text or paths."""
    safe = {}
    for field, allowed in SAFE_ENUMS.items():
        value = state.get(field)
        if isinstance(value, str) and value in allowed:
            safe[field] = value
    independent = state.get("independent_steps")
    if type(independent) is int and 0 <= independent <= 100:
        safe["independent_steps"] = independent
    conflicting = state.get("conflicting_paths")
    if type(conflicting) is bool:
        safe["conflicting_paths"] = conflicting
    elif type(conflicting) is int and 0 <= conflicting <= 100:
        safe["conflicting_paths"] = conflicting
    return safe


def _result(status, reason, *, confidence=None, attempts=0, usage=None, route="rules", calls=0):
    return {"status": status, "reason": reason, "confidence": confidence,
            "successful_calls": calls, "inference_attempts": attempts,
            "usage": usage or {}, "route": route}


def _load_external_key(root: Path):
    """Only the explicitly trusted credential helper is imported, and only opt-in."""
    path = root / "experiment" / "decision_credentials.py"
    if path.is_symlink():
        raise ValueError("credential_helper_symlink")
    spec = importlib.util.spec_from_file_location("_codex_flow_external_mercury_credentials", path)
    if spec is None or spec.loader is None:
        raise ValueError("credential_helper_unavailable")
    module = importlib.util.module_from_spec(spec)
    # Avoid leaving bytecode in the external, sealed installation.
    source = path.read_bytes()
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module.load_key()


class MercuryBridge:
    """A routing hint; it never authorizes writes, sandbox changes, or model swaps.

    ``external_root`` is an explicit trust decision by the caller (normally
    ``Path('<trusted-external-installation>')``), never an environment-discovered installation.
    Injected ``runner`` and ``key_loader`` make every branch testable offline.
    """

    def __init__(self, external_root: Path | None = None, timeout_s=12, *,
                 runner: Callable | None = None, key_loader: Callable | None = None):
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 12:
            raise ValueError("Mercury timeout must be between zero and twelve seconds")
        self.external_root = Path(external_root) if external_root is not None else None
        self.timeout_s = timeout_s
        self.runner = runner or subprocess.run
        self.key_loader = key_loader

    def decide(self, state: dict, enabled: bool = False) -> dict:
        if enabled is not True:
            return _result("SKIPPED", "disabled")
        if self.external_root is None:
            return _result("SKIPPED", "external_installation_not_configured")
        if not isinstance(state, dict):
            return _result("REJECTED", "invalid_state")
        safe = _abstract_state(state)
        if not safe:
            return _result("SKIPPED", "no_safe_abstract_state")
        directory = self.external_root / "experiment"
        client = directory / "decision_client.mjs"
        if self.external_root.is_symlink() or directory.is_symlink() or client.is_symlink() or not client.is_file():
            return _result("UNAVAILABLE", "external_adapter_unavailable")
        node = shutil.which("node")
        if not node:
            return _result("UNAVAILABLE", "node_unavailable")
        try:
            key = self.key_loader() if self.key_loader is not None else _load_external_key(self.external_root)
        except Exception:
            return _result("UNAVAILABLE", "credential_unavailable")
        if not isinstance(key, str) or not key or re.search(r"\s", key):
            return _result("SKIPPED", "credential_unavailable")
        request = {"state": safe, "questions": {"parallel_useful": {
            "type": "noul",
            "instructions": "Would bounded parallel helpers help this task? Use only the abstract facts in state. "
                            "Independent steps favor parallel work; conflicting paths and high risk favor a single writer. "
                            "This judgment cannot grant permissions, change the task, or weaken safety boundaries.",
            "criteria": {"true": "The abstract task facts support useful independent parallel work.",
                         "false": "A single worker or deterministic routing is more appropriate."}}}}
        env = {name: value for name, value in os.environ.items()
               if name.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        env["OPENROUTER_API_KEY"] = key
        try:
            completed = self.runner([node, "--input-type=module", "--eval", NODE_WRAPPER, client.resolve().as_uri()],
                                    input=json.dumps(request, allow_nan=False),
                                    env=env, capture_output=True, text=True, encoding="utf-8", timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            return _result("UNAVAILABLE", "request_timeout", attempts=None)
        except Exception:
            return _result("UNAVAILABLE", "client_unavailable", attempts=None)
        if completed.returncode != 0:
            # Classify only known local runtime signatures. Raw diagnostics may
            # contain authenticated data and are never returned or persisted.
            diagnostic = completed.stderr or ""
            reason = "client_failed"
            for marker, fixed_reason in (("UV_HANDLE_CLOSING", "node_runtime_closing_crash"),
                                         ("ncrypto::CSPRNG", "node_entropy_initialization_failed"),
                                         ("ERR_MODULE_NOT_FOUND", "external_adapter_dependency_unavailable"),
                                         ("ERR_UNKNOWN_FILE_EXTENSION", "node_typescript_unsupported")):
                if marker in diagnostic:
                    reason = fixed_reason
                    break
            return _result("UNAVAILABLE", reason, attempts=None)
        try:
            if not isinstance(completed.stdout, str) or len(completed.stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
                raise ValueError("invalid_output")
            outcome = json.loads(completed.stdout)
            return self._validate(outcome)
        except (ValueError, TypeError, KeyError, AttributeError):
            return _result("REJECTED", "invalid_client_output", attempts=None)

    @staticmethod
    def _validate(outcome):
        if not isinstance(outcome, dict):
            raise ValueError("invalid_output")
        attempts = outcome.get("inference_attempts")
        if type(attempts) is not int or attempts not in (0, 1):
            raise ValueError("invalid_attempts")
        if outcome.get("status") in {"REJECTED", "UNAVAILABLE"}:
            reason = outcome.get("reason")
            if not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", reason):
                raise ValueError("invalid_reason")
            cost = outcome.get("reported_cost_usd")
            known_cost = ({"cost": cost} if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else {})
            return _result(outcome["status"], reason, attempts=attempts, usage=known_cost)
        if outcome.get("status") != "OBSERVED" or attempts != 1:
            raise ValueError("unobserved_output")
        if outcome.get("request_model") != MODEL or outcome.get("model") not in {BUILD, BUILD + ":free"}:
            return _result("REJECTED", "model_mismatch", attempts=attempts)
        if outcome.get("catalog_verified") is not True or outcome.get("provider") not in {None, "Inception", "inception"}:
            return _result("REJECTED", "provider_unverified", attempts=attempts)
        usage = outcome.get("usage")
        if not isinstance(usage, dict) or type(usage.get("cost")) not in (int, float) or usage["cost"] != 0:
            cost = usage.get("cost") if isinstance(usage, dict) else None
            known_cost = ({"cost": cost} if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else {})
            return _result("REJECTED", "nonzero_or_unknown_cost", attempts=attempts, usage=known_cost)
        if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
            raise ValueError("invalid_usage")
        answer = outcome.get("answers", {}).get("parallel_useful", {})
        confidence = answer.get("noul")
        if answer.get("type") != "noul" or type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("invalid_confidence")
        safe_usage = {k: usage[k] for k in ("cost", "input_tokens", "output_tokens")}
        if confidence >= PARALLEL_THRESHOLD:
            route, reason = "parallel", "parallel_useful"
        elif confidence <= SINGLE_THRESHOLD:
            route, reason = "single", "single_preferred"
        else:
            route, reason = "rules", "low_confidence"
        return _result("OBSERVED", reason, confidence=confidence, attempts=attempts,
                       usage=safe_usage, route=route, calls=1)
