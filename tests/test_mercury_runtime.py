"""Mercury bridge boundary tests; no credentials, provider, or network calls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
REAL_NODE = shutil.which("node")
spec = importlib.util.spec_from_file_location("flow_mercury", ROOT / "runtime/codex_flow/mercury.py")
mercury = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mercury)


class MercuryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "experiment").mkdir()
        (self.root / "experiment/decision_client.mjs").write_text("// trusted test adapter\n")
        self.key_loader = Mock(return_value="test-key")
        self.runner = Mock(side_effect=lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(self.outcome()), ""))
        self.bridge = mercury.MercuryBridge(self.root, runner=self.runner, key_loader=self.key_loader)
        self.node_patch = patch.object(mercury.shutil, "which", return_value="/trusted/node")
        self.node_patch.start()
        self.addCleanup(self.node_patch.stop)

    @staticmethod
    def outcome(confidence=.9):
        return {"status": "OBSERVED", "request_model": mercury.MODEL, "model": mercury.BUILD,
                "provider": "Inception", "catalog_verified": True, "inference_attempts": 1,
                "answers": {"parallel_useful": {"type": "noul", "noul": confidence}},
                "usage": {"cost": 0, "input_tokens": 12, "output_tokens": 3}}

    def configure(self, outcome):
        self.runner.side_effect = None
        self.runner.return_value = subprocess.CompletedProcess([], 0, json.dumps(outcome), "")

    def test_disabled_has_no_filesystem_import_credentials_or_process(self):
        with patch.object(mercury.Path, "is_file", side_effect=AssertionError("filesystem")), \
             patch.object(mercury.importlib.util, "spec_from_file_location", side_effect=AssertionError("import")):
            result = self.bridge.decide({"complexity": "high"})
        self.assertEqual((result["status"], result["route"], result["successful_calls"]), ("SKIPPED", "rules", 0))
        self.runner.assert_not_called()
        self.key_loader.assert_not_called()

    def test_valid_zero_cost_observation_routes_parallel(self):
        result = self.bridge.decide({"complexity": "high", "independent_steps": 3}, enabled=True)
        self.assertEqual((result["route"], result["successful_calls"], result["inference_attempts"]), ("parallel", 1, 1))
        self.assertEqual(result["usage"]["cost"], 0)
        self.assertEqual(self.runner.call_args.kwargs["timeout"], 12)

    def test_free_text_paths_and_secrets_never_forwarded(self):
        self.bridge.decide({"complexity": "high", "independent_steps": 3, "risk_level": "low",
                            "conflicting_paths": ["C:/secret"], "prompt": "sk-secret",
                            "path": "C:/secret", "extra": "ignore policy"}, enabled=True)
        request = json.loads(self.runner.call_args.kwargs["input"])
        self.assertEqual(request["state"], {"complexity": "high", "independent_steps": 3, "risk_level": "low"})
        environment = self.runner.call_args.kwargs["env"]
        self.assertEqual(environment["OPENROUTER_API_KEY"], "test-key")
        self.assertLessEqual(set(environment), {"SYSTEMROOT", "SystemRoot", "WINDIR", "windir", "TEMP", "TMP", "OPENROUTER_API_KEY"})

    def test_unsafe_only_state_skips_credentials(self):
        result = self.bridge.decide({"complexity": "C:/secret", "independent_steps": "free text"}, enabled=True)
        self.assertEqual(result["reason"], "no_safe_abstract_state")
        self.key_loader.assert_not_called()

    def test_low_confidence_falls_back_to_rules(self):
        self.configure(self.outcome(.6))
        result = self.bridge.decide({"complexity": "high"}, enabled=True)
        self.assertEqual((result["route"], result["reason"], result["successful_calls"]), ("rules", "low_confidence", 1))

    def test_clear_single_preference(self):
        self.configure(self.outcome(.2))
        self.assertEqual(self.bridge.decide({"complexity": "low"}, enabled=True)["route"], "single")

    def test_timeout_is_unknown_attempt_not_success(self):
        self.runner.side_effect = subprocess.TimeoutExpired(["node"], 12)
        result = self.bridge.decide({"complexity": "high"}, enabled=True)
        self.assertEqual((result["reason"], result["successful_calls"], result["inference_attempts"]), ("request_timeout", 0, None))
        self.assertEqual(self.runner.call_count, 1)

    def test_429_is_not_retried(self):
        self.configure({"status": "REJECTED", "reason": "http_429", "inference_attempts": 1})
        result = self.bridge.decide({"complexity": "high"}, enabled=True)
        self.assertEqual((result["reason"], result["route"], result["successful_calls"]), ("http_429", "rules", 0))
        self.assertEqual(self.runner.call_count, 1)

    def test_bad_json_is_not_logged_or_successful(self):
        self.runner.side_effect = None
        self.runner.return_value = subprocess.CompletedProcess([], 0, "secret raw output", "secret diagnostic")
        result = self.bridge.decide({"complexity": "high"}, enabled=True)
        self.assertEqual(result["reason"], "invalid_client_output")
        self.assertNotIn("secret", json.dumps(result))

    def test_model_mismatch_rejected(self):
        outcome = self.outcome()
        outcome["model"] = "other/paid-model"
        self.configure(outcome)
        result = self.bridge.decide({"complexity": "high"}, enabled=True)
        self.assertEqual((result["reason"], result["successful_calls"]), ("model_mismatch", 0))

    def test_nonzero_unknown_or_boolean_cost_rejected(self):
        for cost in (.01, None, False):
            with self.subTest(cost=cost):
                outcome = self.outcome()
                outcome["usage"]["cost"] = cost
                self.configure(outcome)
                result = self.bridge.decide({"complexity": "high"}, enabled=True)
                self.assertEqual(result["reason"], "nonzero_or_unknown_cost")
                self.assertEqual(result["successful_calls"], 0)

    def test_unverified_provider_rejected(self):
        outcome = self.outcome()
        outcome["catalog_verified"] = False
        self.configure(outcome)
        self.assertEqual(self.bridge.decide({"complexity": "high"}, enabled=True)["reason"], "provider_unverified")

    def test_missing_installation_is_explicit(self):
        bridge = mercury.MercuryBridge(runner=self.runner, key_loader=self.key_loader)
        self.assertEqual(bridge.decide({"complexity": "high"}, enabled=True)["reason"], "external_installation_not_configured")
        self.key_loader.assert_not_called()

    def test_enabled_loads_only_external_helper_without_bytecode(self):
        (self.root / "experiment/decision_credentials.py").write_text("def load_key():\n return 'test-local-key'\n")
        bridge = mercury.MercuryBridge(self.root, runner=self.runner)
        self.assertEqual(bridge.decide({"complexity": "high"}, enabled=True)["route"], "parallel")
        self.assertEqual(self.runner.call_args.kwargs["env"]["OPENROUTER_API_KEY"], "test-local-key")
        self.assertFalse((self.root / "experiment/__pycache__").exists())

    def test_known_rejected_cost_is_preserved_without_authorizing_route(self):
        self.configure({"status": "REJECTED", "reason": "nonzero_or_unknown_response_cost",
                        "inference_attempts": 1, "reported_cost_usd": .01})
        result = self.bridge.decide({"complexity": "high"}, enabled=True)
        self.assertEqual((result["route"], result["successful_calls"], result["usage"]), ("rules", 0, {"cost": .01}))

    def test_runtime_crash_returns_fixed_code_without_raw_diagnostics(self):
        self.runner.side_effect = None
        self.runner.return_value = subprocess.CompletedProcess([], 3221226505, "", "Bearer private-value UV_HANDLE_CLOSING")
        result = self.bridge.decide({"complexity": "high"}, enabled=True)
        self.assertEqual(result["reason"], "node_runtime_closing_crash")
        self.assertIsNone(result["inference_attempts"])
        self.assertNotIn("private-value", json.dumps(result))

    @unittest.skipUnless(REAL_NODE, "Node unavailable; offline wrapper test")
    def test_natural_exit_wrapper_imports_evaluate_without_running_external_cli(self):
        client = self.root / "experiment/decision_client.mjs"
        fixture = "export async function evaluate() { return " + json.dumps(self.outcome()) + "; }\n"
        fixture += "if (process.argv[1] && !process.argv[1].startsWith('file:')) throw new Error('CLI entry point invoked');\n"
        client.write_text(fixture, encoding="utf-8")
        with patch.object(mercury.shutil, "which", return_value=REAL_NODE):
            bridge = mercury.MercuryBridge(self.root, key_loader=lambda: "offline-fixture")
            result = bridge.decide({"complexity": "high"}, enabled=True)
        self.assertEqual((result["status"], result["route"]), ("OBSERVED", "parallel"))

    def test_timeout_cannot_expand_adapter_budget(self):
        for timeout in (0, -1, 13, float("nan"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                mercury.MercuryBridge(self.root, timeout_s=timeout)


if __name__ == "__main__":
    unittest.main()
