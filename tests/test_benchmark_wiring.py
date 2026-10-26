"""Offline orchestration wiring proofs, not live sandbox/model evidence."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from codex_flow import benchmark, native, cli
from codex_flow.config import Config
from codex_flow.contracts import PolicyError
from codex_flow.subscription import RequestBudget


def options(command):
    return {command[i + 1].split("=", 1)[0]: command[i + 1].split("=", 1)[1]
            for i, value in enumerate(command[:-1]) if value == "-c"}


class BenchmarkWiringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="flow-wiring-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_parallel_arms_share_prompt_safe_deny_targets_and_per_arm_budget(self):
        self.assert_execution('ABCD')

    def test_ab_only_creates_and_executes_two_fresh_concurrent_arms(self):
        self.assert_execution('AB')

    def test_opt_in_http_recovery_is_equal_in_both_arms_and_preserves_caps(self):
        self.assert_execution('AB', native_request_retries=1)

    def assert_execution(self, groups, native_request_retries=0):
        experiment = self.root / "new-experiment"
        task = self.root / "task.md"
        task.write_text("Synthetic common task; no implementation or real experiment solutions.", encoding="utf-8")
        evaluator = self.root / "hidden-evaluator/evaluate.py"
        evaluator.parent.mkdir()
        evaluator.write_text("# synthetic evaluator fixture\n")
        evaluator.with_name("rubric.json").write_text("{}")
        protected = self.root / "protected"
        protected.mkdir()
        previous = self.root / "previous-experiment"
        previous.mkdir()
        (previous / "experiment-manifest.json").write_text("{}")
        ignored = self.root / "ordinary-directory"
        ignored.mkdir()
        barriers = {"AB": threading.Barrier(2), "CD": threading.Barrier(2)}
        calls, budgets, thread_ids = {}, {}, {}
        lock = threading.Lock()
        main_thread = threading.get_ident()

        def fake_git(directory, *args):
            if args[:2] == ("worktree", "add"):
                Path(args[3]).mkdir()
            return "a" * 40 if args[:2] == ("rev-parse", "HEAD") else ""

        def observation():
            return {"status": "completed_unverified", "wall_clock_s": .01,
                    "input_tokens": 10, "output_tokens": 2, "cached_tokens": 0,
                    "all_requests_usage": {"input_tokens": 10, "output_tokens": 2, "cached_tokens": 0},
                    "subscription": {"requests": [{"model": "gpt-6.1-sol", "effort": "xhigh"}]}}

        def fake_run(exe, workspace, cfg, prompt, run_root, **kwargs):
            group = workspace.name[-1]
            self.assertEqual(cfg.model, 'gpt-6.1-sol')
            self.assertEqual(cfg.effort, 'xhigh')
            self.assertEqual(cfg.max_model_requests, 80)
            self.assertEqual(cfg.native_request_retries, native_request_retries)
            budget = kwargs["request_budget"]
            budget.reserve()
            with lock:
                calls[group] = (prompt, tuple(kwargs["denied_reads"]), kwargs["parallel"])
                thread_ids[group] = threading.get_ident()
                if group in budgets:
                    self.assertIs(budgets[group], budget)
                budgets[group] = budget
                for target in kwargs["denied_reads"]:
                    self.assertTrue(target.exists())
                    self.assertNotEqual(target, experiment)
                    self.assertNotIn(experiment, target.parents)
            barriers["AB" if group in "AB" else "CD"].wait(timeout=3)
            return observation()

        mercury = Mock()
        mercury.decide.return_value = {"status": "UNAVAILABLE", "route": "rules", "successful_calls": 0}
        with patch.object(benchmark, "executable", return_value="fake-codex"), \
             patch.object(benchmark, "subscription"), patch.object(benchmark, "git", side_effect=fake_git), \
             patch.object(benchmark.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "codex-cli offline-fixture", "")), \
             patch.object(benchmark, "hardware", return_value={}), \
             patch("codex_flow.mercury.MercuryBridge", return_value=mercury), \
             patch.object(benchmark, "probe") as probes, \
             patch.object(benchmark, "run", side_effect=fake_run), \
             patch.object(benchmark, "ThreadPoolExecutor", wraps=ThreadPoolExecutor) as pools:
            result = benchmark.execute(experiment, task, evaluator, timeout=30, execute=True,
                                       protect_paths=(protected,), groups=groups,
                                       native_request_retries=native_request_retries)
        probes.assert_not_called()
        self.assertEqual(set(result), set(groups))
        self.assertTrue(all(result[g]["status"] == "completed_unverified" for g in groups))
        self.assertEqual({g: result[g]["model_requests_total"] for g in groups}, {g: 1 for g in groups})
        self.assertEqual(len({id(budget) for budget in budgets.values()}), len(groups))
        self.assertEqual({entry[0] for entry in calls.values()}, {task.read_text()})
        self.assertEqual(len({entry[1] for entry in calls.values()}), 1)
        self.assertEqual(set(calls["A"][1]), {previous, evaluator.parent, protected})
        self.assertNotIn(ignored, calls["A"][1])
        self.assertFalse(calls["A"][2])
        self.assertTrue(all(calls[g][2] for g in groups if g != 'A'))
        self.assertNotEqual(thread_ids["A"], thread_ids["B"])
        if 'C' in groups:self.assertNotEqual(thread_ids["C"], thread_ids["D"])
        else:
            self.assertFalse((experiment/'workspace-C').exists())
            self.assertFalse((experiment/'workspace-D').exists())
        self.assertNotIn(main_thread, thread_ids.values())
        self.assertEqual(pools.call_count, len(groups)//2)
        pools.assert_called_with(max_workers=2)
        manifest = json.loads((experiment / "experiment-manifest.json").read_text())
        self.assertFalse(manifest["isolation"]["cross_arm_read_isolation"])
        self.assertTrue(manifest["isolation"]["shared_deny_policy"])
        self.assertEqual(manifest['selected_groups'], list(groups))
        self.assertEqual(manifest['native_request_max_retries_both_arms'], native_request_retries)
        self.assertEqual(result['B']['details']['harness']['status'], 'deferred')
        self.assertEqual(result['B']['harness_inspired_probes'], 0)
        self.assertEqual(manifest['task_sha256'], benchmark.sha(task))
        self.assertEqual(manifest['evaluator_sha256'], benchmark.sha(evaluator))
        self.assertEqual(manifest['rubric_sha256'], benchmark.sha(evaluator.with_name('rubric.json')))

    def test_real_probe_wiring_passes_same_budget_and_deny_targets_to_both_phases(self):
        workspace, probes, protected = (self.root / name for name in ("workspace", "probes", "protected"))
        for folder in (workspace, probes, protected): folder.mkdir()
        active = workspace/'.codex-flow/lessons/active.txt'
        active.parent.mkdir(parents=True)
        active.write_text('preserve old diagnostic instructions')
        budget = RequestBudget(3)
        seen = []
        def fake_run(exe, directory, cfg, prompt, run_directory, **kwargs):
            self.assertIs(kwargs["request_budget"], budget)
            self.assertEqual(kwargs["denied_reads"], (protected,))
            budget.reserve()
            seen.append(kwargs["instructions"])
            plan = {field: "A concrete offline planning observation for " + field
                    for field in ("geometry", "projection4d", "occlusion", "controls", "verification")}
            (directory / "plan.json").write_text(json.dumps(plan))
            return {"status": "completed_unverified", "wall_clock_s": 2 if len(seen) == 1 else 1}
        with patch.object(benchmark, "git"), patch.object(benchmark, "run", side_effect=fake_run):
            result = benchmark.probe("fake-codex", workspace, probes, Config(enabled=True),
                                     deadline=time.monotonic() + 30, request_budget=budget, denied_reads=(protected,))
        self.assertEqual(budget.used, 2)
        self.assertEqual(budget.reserve(), 3)
        self.assertEqual(result["decision"]["proposal"]["instructions"], seen[1])
        self.assertEqual(active.read_text(), 'preserve old diagnostic instructions')
        self.assertFalse(result['decision']['adopted'])
        self.assertFalse(result['application_quality_eligible'])

    def test_missing_deny_target_rejected_without_process_or_directory_creation(self):
        missing = self.root / "missing-target"
        with patch.object(native.subprocess, "Popen") as process:
            with self.assertRaisesRegex(PolicyError, "already exist"):
                native.argv("fake-codex", self.root, Config(), denied_reads=(missing,))
        process.assert_not_called()
        self.assertFalse(missing.exists())

    def test_existing_denies_use_named_profile_and_project_state_without_unsupported_role_overrides(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        deny = self.root / "hidden"
        deny.mkdir()
        private_state = workspace / ".codex-flow/native-state"
        private_state.mkdir(parents=True)
        profiles = native.role_profiles(workspace, named_permissions=True)
        command = native.argv("fake-codex", workspace, Config(), parallel=True,
                              denied_reads=(deny, private_state), profiles=profiles)
        config = options(command)
        self.assertNotIn("--sandbox", command)
        self.assertNotIn("--ephemeral", command)
        self.assertFalse(any("bypass" in token for token in command))
        self.assertEqual(json.loads(config["default_permissions"]), "flow_task")
        permission = tomllib.loads("value=" + config["permissions.flow_task"])["value"]
        self.assertEqual(permission["filesystem"][str(deny.resolve()).replace("\\", "/")], "deny")
        self.assertEqual(permission["filesystem"][str(private_state.resolve()).replace("\\", "/")], "deny")
        self.assertEqual(permission["filesystem"][str(workspace.resolve()).replace("\\", "/")], "write")
        self.assertFalse(permission["network"]["enabled"])
        self.assertEqual(json.loads(config["sqlite_home"]), str(workspace / ".codex-flow/native-state"))
        self.assertEqual(json.loads(config["log_dir"]), str(workspace / ".codex-flow/native-state/logs"))
        self.assertEqual(json.loads(config["history.persistence"]), "none")
        self.assertEqual(json.loads(config["agents.max_concurrent_threads_per_session"]), 3)
        self.assertNotIn("agents.max_depth", config)
        self.assertEqual(json.loads(config["model_reasoning_effort"]), "xhigh")
        for role, path in profiles.items():
            self.assertEqual(json.loads(config["agents." + role + ".config_file"]), str(path))
            role_config = tomllib.loads(path.read_text())
            if role == "reviewer":
                self.assertEqual(role_config["model"], "gpt-6.1-sol")
                self.assertEqual(role_config["model_reasoning_effort"], "high")
            self.assertFalse({"permissions", "default_permissions", "sandbox_mode", "approval_policy"} & role_config.keys())
            # shell_tool is a documented capability that custom agents may disable.
            self.assertLessEqual(set(role_config["features"]), {"shell_tool", "apps", "plugins", "memories", "request_permissions_tool"})
            if role == 'reviewer':self.assertFalse(role_config['features']['shell_tool'])
            else:self.assertNotIn('shell_tool',role_config['features'])
            self.assertTrue(all(value is False for value in role_config["features"].values()))
        self.assertIn("--ephemeral", native.argv("fake-codex", workspace, Config(), parallel=False))

    def test_native_run_precreates_only_owned_state_and_denies_tool_reads_without_content_isolation_claim(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        run_dir = self.root / "synthetic-run"
        state = workspace / ".codex-flow/native-state"
        self.assertFalse(state.exists())
        gateway = Mock()
        gateway.__enter__ = Mock(return_value=gateway)
        gateway.__exit__ = Mock(return_value=False)
        gateway.summary.return_value = {"completed_requests": 0, "aggregate_usage": None}
        def fake_run(exe, assigned, cfg, prompt, output, **kwargs):
            self.assertTrue(state.is_dir())
            self.assertIn(state, kwargs["denied_reads"])
            self.assertTrue(all(Path(target).exists() for target in kwargs["denied_reads"]))
            command = native.argv(exe, assigned, cfg, denied_reads=kwargs["denied_reads"])
            profile = tomllib.loads("value=" + options(command)["permissions.flow_task"])["value"]
            self.assertEqual(profile["filesystem"][str(state.resolve()).replace("\\", "/")], "deny")
            self.assertEqual(profile["filesystem"][str(workspace.resolve()).replace("\\", "/")], "write")
            output.mkdir()
            return {"status": "completed_unverified", "input_tokens": None, "output_tokens": None, "cached_tokens": None}
        with patch("codex_flow.subscription.SubscriptionGateway", return_value=gateway), \
             patch.object(native, "_run", side_effect=fake_run), patch.object(native.subprocess, "Popen") as process:
            result = native.run("fake-codex", workspace, Config(), "synthetic", run_dir)
        process.assert_not_called()
        self.assertTrue(result["native_state_tool_read_denial_configured"])
        self.assertFalse(result["native_state_tool_read_denial_verified"])
        self.assertTrue(result["native_state_may_rehydrate_shared_history"])
        self.assertFalse(result["native_state_content_isolation_verified"])
        self.assertEqual(list(state.iterdir()), [])

    def test_missing_workspace_is_not_created_to_materialize_state_denial(self):
        missing = self.root / "missing-workspace"
        with self.assertRaisesRegex(PolicyError, "workspace missing"):
            native.run("fake-codex", missing, Config(), "synthetic", self.root / "run")
        self.assertFalse(missing.exists())

    def test_both_instruction_variants_forbid_native_history_containers(self):
        for instructions in (cli.BASE_INSTRUCTIONS, cli.FLOW_INSTRUCTIONS):
            self.assertIn(".codex-flow/native-state", instructions)
            self.assertIn("history containers", instructions)


if __name__ == "__main__": unittest.main()
