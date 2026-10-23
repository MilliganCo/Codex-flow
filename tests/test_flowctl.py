"""Offline functional tests. No model, network, account, or user filesystem access."""
from __future__ import annotations
import importlib.util
import json
import shutil
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import re
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'payload' / 'codex-flow'
MODULE = SOURCE / 'scripts' / 'flowctl.py'
if MODULE.exists():
    spec = importlib.util.spec_from_file_location('flowctl', MODULE)
    flow = importlib.util.module_from_spec(spec)
    sys.modules['flowctl'] = flow
    spec.loader.exec_module(flow)
else:
    flow = None

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(flow, 'flowctl implementation does not exist yet')
        self.tmp = tempfile.TemporaryDirectory(prefix='codex-flow-test-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'User Space Кириллица'
        self.home.mkdir()
        self.s = flow.Settings(self.home, self.home / '.codex', self.home / '.agents' / 'skills')

    def repo(self):
        p = Path(self.tmp.name) / 'Repo с пробелами [1]'
        p.mkdir()
        subprocess.run(['git', 'init', '-q', str(p)], check=True)
        return p

    def link(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            if os.name == 'nt' and getattr(exc, 'winerror', None) in (5, 1314):
                self.skipTest('This Windows user cannot create symlinks')
            raise

    def install(self, **kwargs):
        return flow.install(self.s, SOURCE, **kwargs)

    def test_browser_default_off_gate_preserves_mandatory_checks(self):
        entry = (SOURCE / 'SKILL.md').read_text()
        run = (SOURCE / 'references/run.md').read_text()
        browser = (SOURCE / 'references/browser.md').read_text()
        self.assertIn('Playwright', entry)
        self.assertIn('*not* default', entry)
        self.assertIn('do not automatically launch Playwright', run)
        self.assertIn('Default: NO', browser)
        self.assertIn('project, CI or release', browser)
        self.assertIn('critical user journey', browser)
        self.assertIn('browser MCP', browser)
        self.assertIn('NOT_RUN', browser)

    def test_edit_inside_global_block_refuses_upgrade_without_mutation(self):
        self.install()
        globalp = self.s.codex_home / 'AGENTS.md'
        old = globalp.read_text()
        globalp.write_text(old.replace('Playwright/browser UI checks are NOT default.',
                                  'MY MANUAL CUSTOM INSTRUCTIONS.'))
        previous = globalp.read_bytes()
        manifest = self.s.manifest.read_bytes()
        with self.assertRaisesRegex(flow.FlowError, 'edited or removed'):
            self.install(dry_run=True)
        with self.assertRaises(flow.FlowError):
            self.install(replace_edited=True)
        self.assertEqual(previous, globalp.read_bytes())
        self.assertEqual(manifest, self.s.manifest.read_bytes())

    def test_edit_outside_global_block_preserved_on_upgrade_and_uninstall(self):
        self.install()
        p = self.s.codex_home / 'AGENTS.md'
        user_addition = '\n# User directives\nKeep my custom tool selection.\n'
        p.write_text(p.read_text() + user_addition)
        self.install()
        self.assertIn(user_addition, p.read_text())
        flow.uninstall(self.s)
        self.assertIn(user_addition, p.read_text())
        self.assertNotIn('codex-flow:begin', p.read_text())

    def test_missing_manifest_does_not_adopt_existing_marker(self):
        self.s.codex_home.mkdir()
        p = self.s.codex_home / 'AGENTS.md'
        p.write_text(flow.update_block(b'', flow.GLOBAL_BLOCK).decode())
        with self.assertRaisesRegex(flow.FlowError, 'without a matching install manifest'):
            self.install()
        self.assertFalse(self.s.manifest.exists())

    def test_override_target_change_fails_closed(self):
        self.install()
        override = self.s.codex_home / 'AGENTS.override.md'
        override.write_text('Manual override that changes effective instructions.')
        original = override.read_bytes()
        with self.assertRaisesRegex(flow.FlowError, 'Effective global AGENTS target differs'):
            self.install()
        self.assertEqual(override.read_bytes(), original)

    def test_uninstall_preserves_edited_global_block(self):
        self.install()
        p = self.s.codex_home / 'AGENTS.md'
        p.write_text(p.read_text().replace('Playwright/browser UI checks are NOT default.',
                                               'Manual instructions for my workflow.'))
        original = p.read_bytes()
        with self.assertRaisesRegex(flow.FlowError, 'Edited global Codex Flow block'):
            flow.uninstall(self.s)
        self.assertTrue(self.s.manifest.exists())
        self.assertEqual(original, p.read_bytes())

    def test_browser_route_included_only_when_relevant(self):
        entry = (SOURCE / 'SKILL.md').read_text(encoding='utf-8')
        route = (SOURCE / 'references' / 'browser.md').read_text(encoding='utf-8')
        self.assertIn('references/browser.md', entry)
        self.assertIn('connectOverCDP', route)
        self.assertIn('fallback', route)
        self.assertIn('Chromium', route)
        self.assertIn('Do not edit Playwright config', route)
        self.assertIn('Do not download browsers', route)
        self.assertIn('existing', route)

    def test_browser_reference_is_managed_and_removed(self):
        result = self.install()
        route = self.s.skill_dir / 'references' / 'browser.md'
        self.assertTrue(route.is_file())
        self.assertIn(str(route), result['changed'])
        flow.uninstall(self.s)
        self.assertFalse(route.exists())

    def test_global_block_explains_browser_fallback(self):
        self.install()
        body = (self.s.codex_home / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('Playwright/browser UI checks are NOT default', body)
        self.assertIn('Lightpanda/Obscura', body)
        self.assertNotIn('curl -', body)

    def test_upgrade_from_older_managed_skill_preserves_global_original(self):
        legacy = Path(self.tmp.name) / 'legacy-skill'
        shutil.copytree(SOURCE, legacy)
        (legacy / 'references' / 'browser.md').unlink()
        (legacy / 'SKILL.md').write_text('---\nname: codex-flow\ndescription: Use for work\n---\n# Older Skill\n', encoding='utf-8')
        self.s.codex_home.mkdir(parents=True)
        original = b'# Existing rules\nKeep them.\n'
        (self.s.codex_home / 'AGENTS.md').write_bytes(original)
        flow.install(self.s, legacy)
        manifest = json.loads(self.s.manifest.read_text(encoding='utf-8'))
        manifest['version'] = '1.0.0'
        self.s.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        self.install()
        self.assertTrue((self.s.skill_dir / 'references' / 'browser.md').exists())
        self.assertIn(b'# Existing rules\nKeep them.\n', (self.s.codex_home / 'AGENTS.md').read_bytes())
        flow.uninstall(self.s)
        self.assertEqual((self.s.codex_home / 'AGENTS.md').read_bytes(), original)

    def test_browser_smoke_node_with_local_fake_playwright(self):
        import shutil
        node = shutil.which('node')
        if not node: self.skipTest('Node.js not present; smoke example syntax checked separately')
        project = Path(self.tmp.name) / 'Demo browser project'
        modules = project / 'node_modules' / 'playwright'
        modules.mkdir(parents=True)
        (project / 'package.json').write_text('{"name":"smoke-test"}', encoding='utf-8')
        (modules / 'index.js').write_text("""
module.exports = { chromium: {
  launch: async () => ({
    newContext: async () => ({
      newPage: async () => ({
        goto: async () => ({status: () => 200}),
        locator: () => ({count: async () => 1, textContent: async () => 'OK'})
      }),
      close: async () => {}
    }),
    close: async () => {}
  }),
  connectOverCDP: async () => { throw new Error('CDP not used in baseline smoke') }
} };
""", encoding='utf-8')
        script = ROOT / 'examples' / 'browser-smoke.cjs'
        completed = subprocess.run([node, str(script), '--engine=chromium',
                                    '--url=http://127.0.0.1:3000', '--runs=2'],
                                   cwd=project, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result['runs'], 2)
        self.assertEqual(result['httpStatuses'], [200, 200])
        self.assertNotIn('OK', completed.stdout)
        blocked = subprocess.run([node, str(script), '--engine=cdp',
                                  '--endpoint=http://192.168.1.1:9222',
                                  '--url=http://127.0.0.1:3000'],
                                 cwd=project, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('loopback', blocked.stderr)

    def test_install_new_global_skill(self):
        self.install()
        self.assertTrue((self.s.skill_dir / 'SKILL.md').exists())
        self.assertIn(b'codex-flow:begin', (self.s.codex_home / 'AGENTS.md').read_bytes())
        self.assertFalse((self.s.codex_home / 'config.toml').exists())

    def test_preserves_existing_instructions_and_config(self):
        self.s.codex_home.mkdir()
        original = '# Правила\r\nНе менять API.\r\n'.encode('utf-8-sig')
        target = self.s.codex_home / 'AGENTS.md'
        target.write_bytes(original)
        config = self.s.codex_home / 'config.toml'
        config.write_text('model_reasoning_effort = "high"\n', encoding='utf-8')
        self.install()
        self.assertTrue(target.read_bytes().startswith(original))
        self.assertEqual(config.read_text(), 'model_reasoning_effort = "high"\n')
        flow.uninstall(self.s)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(self.s.skill_dir.exists())

    def test_utf16_global_roundtrip(self):
        self.s.codex_home.mkdir()
        target = self.s.codex_home / 'AGENTS.md'
        original = '# Правила\r\n'.encode('utf-16')
        target.write_bytes(original)
        self.install()
        self.assertIn('codex-flow:begin', target.read_bytes().decode('utf-16'))
        flow.uninstall(self.s)
        self.assertEqual(target.read_bytes(), original)

    def test_effective_override_selected(self):
        self.s.codex_home.mkdir()
        plain = self.s.codex_home / 'AGENTS.md'
        over = self.s.codex_home / 'AGENTS.override.md'
        plain.write_text('base')
        over.write_text('override')
        self.install()
        self.assertEqual(plain.read_text(), 'base')
        self.assertIn('codex-flow:begin', over.read_text())

    def test_empty_override_falls_back(self):
        self.s.codex_home.mkdir()
        (self.s.codex_home / 'AGENTS.override.md').write_text('')
        self.install()
        self.assertIn('codex-flow:begin', (self.s.codex_home / 'AGENTS.md').read_text())

    def test_idempotent(self):
        first = self.install()
        before = self.s.manifest.read_bytes()
        second = self.install()
        self.assertEqual(second['changed'], [])
        self.assertEqual(self.s.manifest.read_bytes(), before)
        self.assertTrue(first['changed'])

    def test_skill_only(self):
        self.install(skill_only=True)
        self.assertFalse((self.s.codex_home / 'AGENTS.md').exists())

    def test_dry_run_creates_nothing(self):
        result = self.install(dry_run=True)
        self.assertTrue(result['changed'])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_unowned_destination_refused(self):
        self.s.skill_dir.mkdir(parents=True)
        (self.s.skill_dir / 'SKILL.md').write_text('not ours')
        with self.assertRaises(flow.FlowError): self.install()
        self.assertEqual((self.s.skill_dir / 'SKILL.md').read_text(), 'not ours')

    def test_edited_skill_refused_on_reinstall(self):
        self.install()
        p = self.s.skill_dir / 'SKILL.md'
        p.write_text('user modified')
        with self.assertRaises(flow.FlowError): self.install()
        self.assertEqual(p.read_text(), 'user modified')

    def test_edited_skill_refused_on_uninstall(self):
        self.install()
        (self.s.skill_dir / 'SKILL.md').write_text('user modified')
        with self.assertRaises(flow.FlowError): flow.uninstall(self.s)
        self.assertTrue(self.s.manifest.exists())

    def test_user_global_edits_survive_uninstall(self):
        self.install()
        p = self.s.codex_home / 'AGENTS.md'
        p.write_text(p.read_text() + '\n# Added by user\n')
        flow.uninstall(self.s)
        self.assertIn('# Added by user', p.read_text())
        self.assertNotIn('codex-flow:begin', p.read_text())

    def test_uninstall_dry_run(self):
        self.install()
        flow.uninstall(self.s, dry_run=True)
        self.assertTrue(self.s.manifest.exists())
        self.assertTrue((self.s.skill_dir / 'SKILL.md').exists())

    def test_uninstall_without_install_noop(self):
        self.assertEqual(flow.uninstall(self.s)['changed'], [])

    def test_manifest_path_escape_refused(self):
        self.install()
        data = json.loads(self.s.manifest.read_text())
        victim = self.home / 'personal.txt'
        victim.write_text('keep')
        data['files'][str(victim)] = {'before': None, 'after': flow.digest(b'keep')}
        self.s.manifest.write_text(json.dumps(data))
        with self.assertRaises(flow.FlowError): flow.uninstall(self.s)
        self.assertEqual(victim.read_text(), 'keep')

    def test_symlink_destination_refused(self):
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        self.s.skills_dir.parent.mkdir(parents=True)
        self.link(self.s.skills_dir, outside)
        with self.assertRaises(flow.FlowError): self.install()
        self.assertEqual(list(outside.iterdir()), [])

    def test_duplicate_block_refused(self):
        raw = b'<!-- codex-flow:begin -->\na\n<!-- codex-flow:begin -->\nb'
        with self.assertRaises(flow.FlowError): flow.update_block(raw, 'new')

    def test_transaction_rolls_back(self):
        self.s.codex_home.mkdir()
        p = self.s.codex_home / 'AGENTS.md'
        p.write_text('preserve')
        original = flow.atomic_write
        calls = 0
        def fail_once(path, content):
            nonlocal calls
            calls += 1
            if calls == 3: raise OSError('simulated disk failure')
            return original(path, content)
        with patch.object(flow, 'atomic_write', fail_once):
            with self.assertRaises(flow.FlowError): self.install()
        self.assertEqual(p.read_text(), 'preserve')
        self.assertFalse(self.s.manifest.exists())

    def test_bootstrap_preserves_repo_and_unverified_commands(self):
        repo = self.repo()
        (repo / 'package.json').write_text(json.dumps({'scripts': {'test': 'vitest', 'lint':'eslint .'}}))
        (repo / 'AGENTS.md').write_text('# Team rules\n')
        result = flow.bootstrap(repo, attach=True)
        profile = (repo / '.codex-flow' / 'PROJECT.md').read_text()
        self.assertIn('UNVERIFIED', profile)
        self.assertIn('npm run test', profile)
        self.assertIn('# Team rules', (repo / 'AGENTS.md').read_text())
        self.assertFalse((repo / 'node_modules').exists())
        self.assertTrue(result['changed'])

    def test_bootstrap_idempotent(self):
        repo = self.repo()
        flow.bootstrap(repo, attach=True)
        p = repo / '.codex-flow' / 'PROJECT.md'
        p.write_text(p.read_text() + '\nCustom knowledge\n')
        result = flow.bootstrap(repo, attach=True)
        self.assertEqual(result['changed'], [])
        self.assertIn('Custom knowledge', p.read_text())

    def test_bootstrap_dryrun(self):
        repo = self.repo()
        flow.bootstrap(repo, attach=True, dry_run=True)
        self.assertFalse((repo / '.codex-flow').exists())
        self.assertFalse((repo / 'AGENTS.md').exists())

    def test_bootstrap_resolves_git_root(self):
        repo = self.repo()
        child = repo / 'src'
        child.mkdir()
        result = flow.bootstrap(child)
        self.assertEqual(result['repo'], str(repo.resolve()))
        self.assertTrue((repo / '.codex-flow' / 'PROJECT.md').exists())

    def test_bootstrap_non_git_refused(self):
        with self.assertRaises(flow.FlowError): flow.bootstrap(self.home)

    def test_bootstrap_symlink_refused(self):
        repo = self.repo()
        out = self.home / 'private'
        out.mkdir()
        self.link(repo / '.codex-flow', out)
        with self.assertRaises(flow.FlowError): flow.bootstrap(repo)
        self.assertEqual(list(out.iterdir()), [])

    def test_bootstrap_invalid_manifest_reported(self):
        repo = self.repo()
        (repo / 'package.json').write_text('NOT JSON')
        result = flow.bootstrap(repo)
        self.assertTrue(result['warnings'])
        self.assertNotIn('npm run test', (repo / '.codex-flow' / 'PROJECT.md').read_text())

    def test_doctor_no_secrets_no_writes(self):
        self.s.codex_home.mkdir()
        (self.s.codex_home / 'auth.json').write_text('SUPERSECRET')
        (self.s.codex_home / 'config.toml').write_text('model_reasoning_effort="xhigh"\n[mcp_servers.demo]\nurl="https://secret.invalid/APISECRET"\n[plugins.test]\nenabled=true\n')
        before = sorted(str(p) for p in self.home.rglob('*'))
        result = flow.doctor(self.s)
        serialized = json.dumps(result)
        self.assertNotIn('SUPERSECRET', serialized)
        self.assertNotIn('APISECRET', serialized)
        self.assertIn('xhigh', serialized)
        self.assertEqual(sorted(str(p) for p in self.home.rglob('*')), before)

    def test_doctor_invalid_toml_no_raw_secret_error(self):
        self.s.codex_home.mkdir()
        (self.s.codex_home / 'config.toml').write_text('token = SUPERSECRET INVALID')
        result = flow.doctor(self.s)
        self.assertTrue(result['warnings'])
        self.assertNotIn('SUPERSECRET', json.dumps(result))

    def test_doctor_does_not_count_cache_as_active(self):
        p = self.s.codex_home / '.tmp' / 'marketplaces' / 'huge' / 'skills' / 'fake'
        p.mkdir(parents=True)
        (p / 'SKILL.md').write_text('fake')
        result = flow.doctor(self.s)
        self.assertEqual(result['local_skills']['count'], 0)

    def test_new_task_safe_path_and_no_overwrite(self):
        repo = self.repo()
        r = flow.new_task(repo, 'parser-fix', 'Parser fix')
        self.assertTrue(Path(r['path']).exists())
        self.assertIn('Acceptance', Path(r['path']).read_text())
        with self.assertRaises(flow.FlowError): flow.new_task(repo, 'parser-fix', 'again')
        with self.assertRaises(flow.FlowError): flow.new_task(repo, '../escape', 'bad')
        with self.assertRaises(flow.FlowError): flow.new_task(repo, 'CON', 'bad')

    def test_cli_help(self):
        r = subprocess.run([sys.executable, str(MODULE), '--help'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn('doctor', r.stdout)

    def test_skill_contract(self):
        text = (SOURCE / 'SKILL.md').read_text()
        self.assertTrue(text.startswith('---\nname: codex-flow\n'))
        self.assertLess(len(text.splitlines()), 150)
        for route in ('run', 'init', 'doctor', 'review', 'resume'):
            self.assertIn(route, text)
        self.assertNotIn('always spawn', text.lower())


    def test_manifest_wrong_top_level_refused_cleanly(self):
        self.s.codex_home.mkdir()
        self.s.manifest.write_text('[]')
        with self.assertRaises(flow.FlowError): flow.uninstall(self.s)

    def test_package_wrong_top_level_reported(self):
        repo = self.repo()
        (repo / 'package.json').write_text('[]')
        result = flow.bootstrap(repo)
        self.assertTrue(result['warnings'])

    def test_uninstall_never_recurses_untracked_user_directories(self):
        self.install()
        extra = self.s.skill_dir / 'my-notes' / 'empty-folder'
        extra.mkdir(parents=True)
        flow.uninstall(self.s)
        self.assertTrue(extra.is_dir(), 'Unowned directories must not be traversed or removed')

    def test_manifest_scan_limits_entries_not_only_matching_folders(self):
        repo = self.repo()
        packages = repo / 'packages'
        packages.mkdir()
        consumed = []
        original = Path.iterdir
        def fake_iterdir(path):
            if path == packages:
                for n in range(1000):
                    consumed.append(n)
                    yield packages / ('not-a-directory-' + str(n))
            else:
                yield from original(path)
        with patch.object(Path, 'iterdir', fake_iterdir):
            flow.manifest_candidates(repo)
        self.assertLessEqual(len(consumed), 101)

    def test_doctor_recognizes_highest_reasoning_enums(self):
        self.s.codex_home.mkdir()
        config = self.s.codex_home / 'config.toml'
        for value in ('max', 'ultra'):
            config.write_text('model_reasoning_effort="' + value + '"')
            self.assertEqual(flow.config_facts(config)['values']['model_reasoning_effort'], value)

    def test_options_change_refused_without_mutation(self):
        self.install()
        before = self.s.manifest.read_bytes()
        with self.assertRaises(flow.FlowError): self.install(skill_only=True)
        self.assertEqual(self.s.manifest.read_bytes(), before)

    def test_replace_edited_requires_explicit_flag(self):
        self.install()
        p = self.s.skill_dir / 'SKILL.md'
        p.write_text('edited')
        self.install(replace_edited=True)
        self.assertEqual(p.read_bytes(), (SOURCE / 'SKILL.md').read_bytes())

    def test_checkpoint_dryrun_has_no_side_effects(self):
        repo = self.repo()
        flow.new_task(repo, 'test-1', 'Check', dry_run=True)
        self.assertFalse((repo / '.codex-flow').exists())

    def test_repo_assets_match_generated_block(self):
        self.assertEqual((SOURCE / 'assets/repo-instructions.md').read_text().strip(), (flow.BEGIN + '\n' + flow.REPO_BLOCK.strip() + '\n' + flow.END))


    def test_optional_native_roles_install_and_uninstall(self):
        self.install(native_agents=True)
        roles = self.s.codex_home / 'agents'
        self.assertEqual(len(list(roles.glob('cf-*.toml'))), 3)
        for p in roles.glob('cf-*.toml'):
            data = tomllib.loads(p.read_text())
            for key in ('name', 'description', 'developer_instructions'):
                self.assertTrue(data.get(key))
            self.assertNotIn('model', data)
            self.assertNotIn('model_reasoning_effort', data)
        self.assertFalse((self.s.codex_home / 'config.toml').exists())
        flow.uninstall(self.s)
        self.assertEqual(list(roles.glob('cf-*.toml')), [])

    def test_optional_native_roles_refuse_unowned_conflict(self):
        p = self.s.codex_home / 'agents' / 'cf-worker.toml'
        p.parent.mkdir(parents=True)
        p.write_text('user content')
        with self.assertRaises(flow.FlowError): self.install(native_agents=True)
        self.assertEqual(p.read_text(), 'user content')
        self.assertFalse(self.s.manifest.exists())

    def test_relative_skill_links_and_scenario_contract(self):
        for p in SOURCE.rglob('*.md'):
            for rel in re.findall(r'\[[^\]]*\]\(([^)]+)\)', p.read_text()):
                if '://' not in rel and not rel.startswith('#'):
                    self.assertTrue((p.parent / rel.split('#')[0]).exists(), str(p) + ': ' + rel)
        data = json.loads((ROOT / 'evals/scenarios.json').read_text(encoding='utf-8'))
        self.assertEqual(data['status'], 'NOT_RUN_WITH_LIVE_MODEL')
        self.assertEqual(len(data['scenarios']), 24)
        self.assertEqual(len(set(x['id'] for x in data['scenarios'])), 24)

    def test_instruction_size_budget(self):
        self.assertLess(len(flow.GLOBAL_BLOCK.encode('utf-8')), 1800)
        self.assertLess(len((SOURCE / 'SKILL.md').read_text().splitlines()), 150)

    def test_actual_cli_install_doctor_init_uninstall(self):
        env = dict(os.environ)
        env.pop('CODEX_HOME', None)
        common = ['--home', str(self.home)]
        def call(action, *args):
            proc = subprocess.run([sys.executable, str(MODULE), action, *args],
                                  capture_output=True, text=True, encoding='utf-8', env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)
        call('install', *common)
        self.assertTrue(call('doctor', *common)['local_skills']['flow_present'])
        repo = self.repo()
        info = call('init', '--repo', str(repo), '--attach')
        self.assertFalse(info['commands_executed'])
        call('new-task', '--repo', str(repo), '--id', 'cli-task', '--title', 'CLI smoke test')
        call('uninstall', *common)
        self.assertFalse(self.s.manifest.exists())
        self.assertTrue((repo / '.codex-flow' / 'PROJECT.md').exists())

if __name__ == '__main__':
    unittest.main(verbosity=2)
