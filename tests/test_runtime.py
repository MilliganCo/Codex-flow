"""Focused offline runtime contracts: no live models, credentials, or network."""
from __future__ import annotations

from dataclasses import replace
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from codex_flow.config import Config, load
from codex_flow.contracts import ExecutionPlan, PolicyError, TaskSpec, inside
from codex_flow.harness import EvaluationResult, GuardedHarness, HarnessProposal
from codex_flow import native, policy, telemetry, benchmark


class TemporaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="flow-runtime-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)


class ConfigTests(TemporaryTests):
    def test_missing_configuration_is_disabled_with_safe_bounded_defaults(self):
        for config in (load(None), load(self.root / "missing.json")):
            self.assertFalse(config.enabled)
            self.assertFalse(config.mercury)
            self.assertFalse(config.harness2)
            self.assertFalse(config.allow_paid_api)
            self.assertEqual((config.model, config.effort), ("gpt-6.1-sol", "xhigh"))
            self.assertLessEqual(config.max_agents, 3)
            self.assertEqual(config.max_depth, 1)

    def test_project_json_changes_only_explicit_supported_fields(self):
        target = self.root / "config.json"
        target.write_text(json.dumps({"enabled": True, "max_agents": 2, "timeout_s": 20}), encoding="utf-8")
        config = load(target)
        self.assertTrue(config.enabled)
        self.assertEqual((config.max_agents, config.timeout_s), (2, 20))
        self.assertFalse(config.mercury)

    def test_unknown_schema_fields_and_nonobject_rejected(self):
        for value in ({"sandbox_mode": "danger-full-access"}, [], {"schema_version": 2}):
            with self.subTest(value=value):
                path = self.root / "bad.json"
                path.write_text(json.dumps(value))
                with self.assertRaises(PolicyError):
                    load(path)

    def test_boolean_flags_require_real_boolean(self):
        for name in ("enabled", "mercury", "harness2", "allow_paid_api"):
            for value in (1, "false", None):
                with self.subTest(name=name, value=value), self.assertRaises(PolicyError):
                    Config(**{name: value})

    def test_budget_limits_cannot_be_expanded_or_boolean(self):
        cases = {"max_agents": (0, 4, True), "max_depth": (0, 2, True),
                 "max_attempts": (0, 3, True), "timeout_s": (0, 3601, True),
                 "max_refinements": (0, 3, True)}
        for name, values in cases.items():
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaises(PolicyError):
                    Config(**{name: value})

    def test_unverified_models_efforts_modes_and_paid_api_rejected(self):
        for kwargs in ({"model": "other/model"}, {"effort": "low"}, {"mode": "unsafe"}, {"allow_paid_api": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(PolicyError):
                Config(**kwargs)


class ContractTests(TemporaryTests):
    def task(self, name, paths=(), dependencies=()):
        return TaskSpec(name, "bounded work", tuple(str(self.root / p) for p in paths), dependencies)

    def test_dependency_order_and_disjoint_work_batches(self):
        plan = ExecutionPlan((self.task("prepare", ("manifest",)),
                              self.task("a", ("src/a.py",), ("prepare",)),
                              self.task("b", ("src/b.py",), ("prepare",)),
                              self.task("join", ("result",), ("a", "b"))))
        self.assertEqual(plan.ready_batches(), [["prepare"], ["a", "b"], ["join"]])

    def test_duplicate_unknown_and_cyclic_dependencies_rejected(self):
        plans = ((self.task("a"), self.task("a")),
                 (self.task("a", dependencies=("missing",)),),
                 (self.task("a", dependencies=("b",)), self.task("b", dependencies=("a",))),
                 (self.task("a", dependencies=("a",)),))
        for tasks in plans:
            with self.subTest(tasks=tasks), self.assertRaises(PolicyError):
                ExecutionPlan(tasks).ready_batches()

    def test_same_file_ownership_serializes_writers(self):
        self.assertEqual(ExecutionPlan((self.task("a", ("src/a.py",)), self.task("b", ("src/a.py",)))).ready_batches(), [["a"], ["b"]])

    def test_ancestor_and_descendant_ownership_conflict_both_orders(self):
        for paths in (("src", "src/a.py"), ("src/a.py", "src")):
            with self.subTest(paths=paths):
                tasks = (self.task("a", (paths[0],)), self.task("b", (paths[1],)))
                self.assertEqual(ExecutionPlan(tasks).ready_batches(), [["a"], ["b"]])

    def test_path_guard_allows_root_children_but_blocks_escape(self):
        self.assertEqual(inside(self.root, self.root / "src/a.py"), self.root / "src/a.py")
        self.assertEqual(inside(self.root, self.root), self.root)
        with self.assertRaises(PolicyError):
            inside(self.root, self.root / "../outside")


class RouteTests(unittest.TestCase):
    @staticmethod
    def observed(route="parallel"):
        return {"status": "OBSERVED", "route": route, "confidence": .9}

    def test_safety_risk_always_precedes_mercury(self):
        for risk in ("high", "critical", "unknown"):
            with self.subTest(risk=risk):
                result = policy.route(independent_steps=3, risk_level=risk, mercury=self.observed())
                self.assertEqual((result.strategy, result.source), ("escalate", "rules"))

    def test_ownership_sequence_and_explicit_single_precede_mercury(self):
        for kwargs in ({"conflicting_paths": True, "independent_steps": 3}, {"independent_steps": 1},
                       {"single": True, "independent_steps": 3}):
            with self.subTest(kwargs=kwargs):
                result = policy.route(**kwargs, mercury=self.observed())
                self.assertEqual((result.strategy, result.source), ("single", "rules"))

    def test_only_observed_typed_routes_are_used(self):
        good = policy.route(independent_steps=3, mercury=self.observed("single"))
        self.assertEqual((good.strategy, good.source), ("single", "mercury"))
        for status in ("SKIPPED", "UNAVAILABLE", "REJECTED", "success"):
            with self.subTest(status=status):
                result = policy.route(independent_steps=3, mercury={"status": status, "route": "single", "reason": "offline"})
                self.assertEqual((result.strategy, result.source), ("parallel", "rules"))
                self.assertEqual(result.fallback_reason, "offline")


class TelemetryTests(TemporaryTests):
    def test_atomic_json_does_not_touch_predictable_temporary_sentinel(self):
        target = self.root / "report.json"
        sentinel = target.with_suffix(".tmp")
        sentinel.write_text("Unrelated existing file", encoding="utf-8")
        telemetry.write_json(target, {"measured": True})
        self.assertEqual(json.loads(target.read_text()), {"measured": True})
        self.assertEqual(sentinel.read_text(), "Unrelated existing file")
        self.assertEqual(list(self.root.glob(".flow-*.tmp")), [])

    def test_atomic_json_rejects_linked_destination_when_supported(self):
        outside = self.root / "outside.txt"
        outside.write_text("Preserve this file", encoding="utf-8")
        directory = self.root / "store"
        directory.mkdir()
        target = directory / "report.json"
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable on this runner")
        with self.assertRaises(PolicyError):
            telemetry.write_json(target, {"measured": True})
        self.assertEqual(outside.read_text(), "Preserve this file")

    def test_atomic_json_rejects_linked_parent_when_supported(self):
        outside = self.root / "outside"
        outside.mkdir()
        linked = self.root / "linked-store"
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable on this runner")
        with self.assertRaises(PolicyError):
            telemetry.write_json(linked / "report.json", {"measured": True})
        self.assertFalse((outside / "report.json").exists())

    def test_nested_credentials_sensitive_fields_and_local_paths_redacted(self):
        secret = "sk-proj-" + "a" * 32
        data = {"prompt": "private task", "command": "private command", "authorization": "Bearer token",
                "nested": [{"message": secret + " E:/private/file.txt /home/alice/private", "api_key": "abc"}]}
        text = json.dumps(telemetry.sanitize(data))
        for sensitive in (secret, "private task", "private command", "Bearer token", "E:/private", "/home/alice", '"abc"'):
            self.assertNotIn(sensitive, text)
        self.assertIn("[REDACTED]", text)
        self.assertIn("[LOCAL_PATH]", text)

    def test_list_and_string_payloads_are_bounded(self):
        self.assertEqual(len(telemetry.sanitize(list(range(200)))), 100)
        self.assertEqual(len(telemetry.sanitize("x" * 5000)), 2048)

    def test_trace_replay_preserves_safe_usage_and_errors(self):
        path = self.root / "events.jsonl"
        trace = telemetry.Trace(path, "run")
        trace.emit("native.turn.completed", {"usage": {"input_tokens": 5, "output_tokens": 2}, "prompt": "private task"})
        trace.emit("native.error", {"message": "Bearer abc"}, error_category="native_error")
        result = telemetry.replay(path)
        self.assertEqual(result["events"], {"native.turn.completed": 1, "native.error": 1})
        self.assertEqual(result["usage"], {"input_tokens": 5, "output_tokens": 2})
        self.assertEqual(result["errors"], 1)
        self.assertNotIn("private task", path.read_text())

    def test_replay_rejects_oversized_event(self):
        path = self.root / "large.jsonl"
        path.write_text("x" * 65537)
        with self.assertRaisesRegex(ValueError, "oversized"):
            telemetry.replay(path)


class HarnessTests(TemporaryTests):
    def proposal(self, name="candidate"):
        return HarnessProposal(name, "Use exact interfaces.", "measured quality improvement", ("baseline", "candidate"))

    @staticmethod
    def measurement(quality=1, duration=2, safety=True, complete=True, probe="candidate"):
        return EvaluationResult(quality, duration, safety, complete, probe)

    def compare(self, candidate, *, adopt=False, baseline=None, name="candidate"):
        return GuardedHarness(self.root).compare(self.proposal(name), baseline or self.measurement(quality=.8, probe="baseline"), candidate, adopt=adopt)

    def test_measured_improvement_eligible_but_not_adopted_by_default(self):
        result = self.compare(self.measurement())
        self.assertTrue(result["eligible"])
        self.assertFalse(result["adopted"])
        self.assertFalse((self.root / ".codex-flow/lessons/active.txt").exists())

    def test_quality_regression_incomplete_unsafe_or_same_probe_rejected(self):
        candidates = (self.measurement(quality=.5, duration=.1), self.measurement(complete=False),
                      self.measurement(safety=False), self.measurement(probe="baseline"))
        for index, candidate in enumerate(candidates):
            with self.subTest(candidate=candidate):
                location = self.root / str(index)
                result = GuardedHarness(location).compare(self.proposal(), self.measurement(quality=.8, probe="baseline"), candidate, adopt=True)
                self.assertFalse(result["eligible"])
                self.assertFalse(result["adopted"])
                self.assertFalse((location / ".codex-flow/lessons/active.txt").exists())

    def test_equal_quality_only_faster_candidate_can_be_eligible(self):
        baseline = self.measurement(quality=1, duration=2, probe="baseline")
        self.assertTrue(self.compare(self.measurement(quality=1, duration=1), baseline=baseline)["eligible"])
        with tempfile.TemporaryDirectory() as directory:
            result = GuardedHarness(Path(directory)).compare(self.proposal(), baseline, self.measurement(quality=1, duration=2))
            self.assertFalse(result["eligible"])

    def test_invalid_metrics_fail_closed(self):
        for value in (float("nan"), float("inf"), -1):
            for field in ("quality", "duration_s"):
                with self.subTest(value=value, field=field), self.assertRaises((PolicyError, ValueError)):
                    self.compare(replace(self.measurement(), **{field: value}), adopt=True)

    def test_safety_and_completion_require_real_booleans(self):
        for field in ("safety_passed", "complete"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises((PolicyError, ValueError)):
                    GuardedHarness(Path(directory)).compare(self.proposal(), self.measurement(probe="baseline"),
                                                           replace(self.measurement(quality=2), **{field: "false"}), adopt=True)

    def test_adoption_requires_boolean_not_truthy_text(self):
        with self.assertRaises((PolicyError, ValueError)):
            self.compare(self.measurement(), adopt="false")

    def test_probe_budget_requires_integer_and_is_enforced(self):
        with self.assertRaises(PolicyError):
            GuardedHarness(self.root, max_refinements=True)
        harness = GuardedHarness(self.root)
        harness.compare(self.proposal(), self.measurement(probe="baseline"), self.measurement(quality=2))
        with self.assertRaisesRegex(PolicyError, "budget"):
            harness.compare(self.proposal("second"), self.measurement(probe="baseline2"), self.measurement(quality=2))

    def test_adoption_and_rollback_restore_prior_instructions(self):
        target = self.root / ".codex-flow/lessons/active.txt"
        target.parent.mkdir(parents=True)
        target.write_text("Original instructions", encoding="utf-8")
        harness = GuardedHarness(self.root)
        result = harness.compare(self.proposal(), self.measurement(quality=.8, probe="baseline"), self.measurement(), adopt=True)
        self.assertTrue(result["adopted"])
        self.assertEqual(target.read_text(), self.proposal().instructions)
        self.assertTrue(harness.rollback("candidate")["rolled_back"])
        self.assertEqual(target.read_text(), "Original instructions")

    def test_rollback_of_new_adoption_removes_only_unchanged_active_file(self):
        self.compare(self.measurement(), adopt=True)
        GuardedHarness(self.root).rollback("candidate")
        self.assertFalse((self.root / ".codex-flow/lessons/active.txt").exists())
        self.assertTrue((self.root / ".codex-flow/lessons/proposal-candidate.json").is_file())

    def test_rollback_refuses_manual_drift_and_preserves_edit(self):
        self.compare(self.measurement(), adopt=True)
        target = self.root / ".codex-flow/lessons/active.txt"
        target.write_text("Manual edit")
        with self.assertRaisesRegex(PolicyError, "changed"):
            GuardedHarness(self.root).rollback("candidate")
        self.assertEqual(target.read_text(), "Manual edit")

    def test_path_traversal_proposal_identifiers_rejected(self):
        harness = GuardedHarness(self.root)
        for name in ("../escape", "", "a/b"):
            with self.subTest(name=name):
                with self.assertRaises(PolicyError):
                    harness.compare(self.proposal(name), self.measurement(probe="baseline"), self.measurement())
                with self.assertRaises(PolicyError):
                    harness.rollback(name)


class BenchmarkProbeTests(TemporaryTests):
    def test_adopted_candidate_is_exact_native_probe_instruction_text(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        probes = self.root / "probes"
        probes.mkdir()
        instructions = []
        prompts = []
        def fake_native(exe, directory, config, prompt, run_directory, **kwargs):
            instructions.append(kwargs["instructions"])
            prompts.append(prompt)
            plan = {key: "Concrete measured planning detail for " + key
                    for key in ("geometry", "projection4d", "occlusion", "controls", "verification")}
            (directory / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            return {"status": "completed_unverified", "wall_clock_s": 2 if len(instructions) == 1 else 1}
        with patch.object(benchmark, "git"), patch.object(benchmark, "run", side_effect=fake_native) as run:
            result = benchmark.probe("fake-codex", workspace, probes, Config(enabled=True))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(prompts[0], prompts[1])
        self.assertNotEqual(instructions[0], instructions[1])
        self.assertTrue(result["decision"]["adopted"])
        self.assertEqual(result["decision"]["proposal"]["instructions"], instructions[1])
        self.assertEqual((workspace / ".codex-flow/lessons/active.txt").read_text(), instructions[1])
        self.assertEqual(result["upstream_probes"], 0)
        self.assertEqual(result["inspired_probes"], 2)
        self.assertEqual(result["status"], "degraded")


class FakeProcess:
    """Finite in-memory native process; no executable is launched."""
    pid = 12345

    def __init__(self, events, exit_code=0, stderr=""):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(json.dumps(e) + "\n" for e in events))
        self.stderr = io.StringIO(stderr)
        self.returncode = None
        self.exit_code = exit_code

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = self.exit_code
        return self.returncode

    def kill(self):
        self.returncode = -9


class NativeTests(TemporaryTests):
    @staticmethod
    def overrides(command):
        return {command[i + 1].split("=", 1)[0]: json.loads(command[i + 1].split("=", 1)[1])
                for i, value in enumerate(command[:-1]) if value == "-c"}

    def test_argv_enforces_native_sandbox_network_off_and_bounded_concurrency(self):
        command = native.argv("codex", self.root, Config(), parallel=True)
        options = self.overrides(command)
        self.assertFalse(any("bypass" in argument for argument in command))
        self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertNotIn("--ephemeral", command)
        self.assertIn("--ephemeral",native.argv('codex',self.root,Config(),parallel=False))
        self.assertFalse(options["sandbox_workspace_write.network_access"])
        provider = options["model_provider"]
        self.assertEqual(options["model_providers." + provider + ".base_url"], "https://chatgpt.com/backend-api/codex")
        self.assertTrue(options["model_providers." + provider + ".requires_openai_auth"])
        self.assertFalse(options["model_providers." + provider + ".supports_websockets"])
        self.assertEqual(options["model_providers." + provider + ".request_max_retries"], 0)
        self.assertEqual(options["model_providers." + provider + ".stream_max_retries"], 0)
        self.assertEqual(options["model_reasoning_effort"], "xhigh")
        self.assertLessEqual(options["agents.max_concurrent_threads_per_session"], 3)
        self.assertNotIn("agents.max_depth", options)
        for option in ("web_search",):
            self.assertEqual(options[option], "disabled")
        for option in ("hooks", "plugins", "apps", "browser_use", "computer_use", "image_generation", "memories"):
            self.assertFalse(options["features." + option])

    def test_single_mode_disables_native_delegation(self):
        self.assertFalse(self.overrides(native.argv("codex", self.root, Config(), parallel=False))["features.multi_agent"])

    def test_environment_strips_api_keys_tokens_and_secret_variables(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "private-key", "OPENROUTER_API_KEY": "private-key",
                                    "MY_ACCESS_TOKEN": "token", "ANY_SECRET": "secret", "CODEX_OTHER": "setting"}):
            env = native.environment(self.root)
        for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "MY_ACCESS_TOKEN", "ANY_SECRET", "CODEX_OTHER"):
            self.assertNotIn(name, env)
        self.assertEqual(env["CODEX_HOME"], str(Path.home() / ".codex"))
        self.assertEqual(env["TEMP"], str(self.root / ".tmp"))

    def test_api_auth_and_failed_login_rejected_without_launching_work(self):
        for output, code in (("Logged in using an API key", 0), ("Logged in using ChatGPT", 1), ("not logged in", 0)):
            with self.subTest(output=output, code=code), patch.object(native.subprocess, "run", return_value=subprocess.CompletedProcess([], code, output, "")), \
                 patch.object(native.subprocess, "Popen") as popen:
                with self.assertRaises(PolicyError):
                    native.run("fake-codex", self.root, Config(), "bounded task", self.root / "run")
                popen.assert_not_called()

    def invoke(self, events, *, exit_code=0, stderr="", cancel=None):
        process = FakeProcess(events, exit_code=exit_code, stderr=stderr)
        with patch.object(native, "subscription"), patch.object(native.subprocess, "Popen", return_value=process):
            return native.run("fake-codex", self.root, Config(timeout_s=1), "private task",
                              self.root / "run", cancel=cancel)

    def test_zero_exit_without_completed_turn_is_failed(self):
        result = self.invoke([])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["native_exit_code"], 0)
        self.assertIsNone(result["input_tokens"])

    def test_completed_turn_is_explicitly_unverified_not_task_success(self):
        result = self.invoke([{"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 4, "cached_input_tokens": 2}}])
        self.assertEqual(result["status"], "completed_unverified")
        self.assertEqual((result["input_tokens"], result["output_tokens"], result["cached_tokens"]), (10, 4, 2))
        self.assertIsNone(result["actual_api_cost_usd"])
        self.assertFalse(result["full_filesystem_read_isolation_verified"])
        self.assertIn("instruction-only", result["depth_and_total_agent_caps"])

    def test_native_nonzero_exit_cannot_be_completed(self):
        result = self.invoke([{"type": "turn.completed", "usage": {}}], exit_code=1)
        self.assertEqual(result["status"], "failed")

    def test_cancellation_terminates_child_without_claiming_completion(self):
        cancelled = threading.Event()
        cancelled.set()
        process = FakeProcess([])
        def terminate(proc):
            proc.returncode = -9
        with patch.object(native, "subscription"), patch.object(native.subprocess, "Popen", return_value=process), \
             patch.object(native, "terminate_tree", side_effect=terminate) as stop:
            result = native.run("fake-codex", self.root, Config(timeout_s=1), "task", self.root / "run", cancel=cancelled)
        stop.assert_called_once_with(process)
        self.assertEqual(result["status"], "timed_out")

    def test_wall_deadline_terminates_child(self):
        process = FakeProcess([])
        def terminate(proc):
            proc.returncode = -9
        with patch.object(native, "subscription"), patch.object(native.subprocess, "Popen", return_value=process), \
             patch.object(native, "terminate_tree", side_effect=terminate) as stop, \
             patch.object(native.time, "monotonic", side_effect=[0, 0, 0, 2, 2, 2]):
            result = native.run("fake-codex", self.root, Config(timeout_s=1), "task", self.root / "run")
        stop.assert_called_once_with(process)
        self.assertEqual(result["status"], "timed_out")

    def test_tool_counts_preserved_without_raw_commands_or_prompt(self):
        result = self.invoke([{"type": "item.completed", "item": {"type": "command_execution", "command": "secret command", "exit_code": 2}},
                              {"type": "turn.completed", "usage": {}}])
        self.assertEqual((result["tool_calls"], result["failed_calls"]), (1, 1))
        text = (self.root / "run/events.jsonl").read_text()
        self.assertNotIn("secret command", text)
        self.assertNotIn("private task", text)


if __name__ == "__main__":
    unittest.main()
