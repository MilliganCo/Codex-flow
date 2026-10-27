"""Offline snapshot tests: fixture source and checker bytes are never executed."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import workflow_files as files
from codex_flow.contracts import PolicyError


@unittest.skipUnless(shutil.which('git'), 'Git is required for fixture metadata')
class WorkflowFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='flow-files-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'project'
        self.repo.mkdir()
        self.git('init', '--template=')
        self.put('app.py', b'owner bytes; do not execute\r\n')
        self.put('gone.txt', b'original\n')
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
        self.seed = self.root / 'seed'

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        return subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false',
                               '-C', str(self.repo), *args], env=env, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def put(self, name, raw):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def snapshot(self):
        return files.seed_project(self.repo, self.seed)

    def test_dirty_untracked_deleted_and_binary_working_bytes_are_preserved(self):
        self.put('app.py', b'dirty\r\n')
        self.put('new/data.bin', b'\x00\xff\x01')
        (self.repo / 'gone.txt').unlink()
        manifest = self.snapshot()
        self.assertEqual(set(manifest['files']), {'app.py', 'new/data.bin'})
        self.assertIn('gone.txt', manifest['omitted'])
        self.assertEqual((self.seed / 'app.py').read_bytes(), b'dirty\r\n')
        self.assertEqual((self.seed / 'new/data.bin').read_bytes(), b'\x00\xff\x01')
        self.assertEqual(manifest['source_head'], self.git('rev-parse', 'HEAD').decode().strip())
        self.assertNotIn(str(self.repo), json.dumps(manifest))
        result = self.root / 'attempt'
        files.materialize(self.seed, manifest, result)
        files.assert_snapshot(result, manifest)

    def test_secrets_control_files_and_ignored_dependencies_are_excluded(self):
        for name in ('.env', '.env.local', 'auth.json', 'nested/credentials.json', 'private.KEY',
                     'cert.pem', '.codex/config.toml', '.agents/rule', '.home/state', '.tmp/temp',
                     '.codex-flow/task', 'node_modules/dependency'):
            self.put(name, b'private fixture')
        self.put('.env.example', b'EXAMPLE=placeholder\n')
        self.put('.gitignore', b'node_modules/\n')
        self.git('add', '.')
        manifest = self.snapshot()
        self.assertEqual(set(manifest['files']), {'app.py', 'gone.txt', '.env.example', '.gitignore'})
        self.assertIn('.env.local', manifest['omitted'])
        self.assertFalse(any('node_modules' in n for n in manifest['files']))

    def test_metadata_disables_fsmonitor_hooks_and_inherited_git_overrides(self):
        marker = self.root / 'executed-marker'
        script = self.root / 'fsmonitor-hook'
        script.write_text('#!/bin/sh\ntouch "' + marker.as_posix() + '"\n', encoding='utf-8')
        script.chmod(0o755)
        self.git('config', 'core.fsmonitor', str(script))
        hooks = self.repo / '.git/hooks'
        hooks.mkdir(exist_ok=True)
        for name in ('post-checkout', 'post-index-change', 'pre-commit'):
            path = hooks / name
            path.write_bytes(script.read_bytes())
            path.chmod(0o755)
        with patch.dict(os.environ, {'GIT_DIR': str(self.root / 'nonexistent'), 'GIT_OPTIONAL_LOCKS': '1'}):
            manifest = self.snapshot()
        self.assertIn('app.py', manifest['files'])
        self.assertFalse(marker.exists())

    def test_inventory_detects_added_deleted_changed_and_ignores_git_control(self):
        manifest = self.snapshot()
        self.put('app.py', b'changed\n')
        self.put('extra.txt', b'new\n')
        (self.repo / 'gone.txt').unlink()
        current = files.inventory(self.repo)
        self.assertEqual(set(current['files']), {'app.py', 'extra.txt'})
        with self.assertRaises(PolicyError):
            files.assert_snapshot(self.repo, manifest)

    def test_bundle_has_exact_result_files_hashes_and_text_diff_without_origin_writes(self):
        original = files.inventory(self.repo)['files']
        manifest = self.snapshot()
        result = self.root / 'attempt'
        files.materialize(self.seed, manifest, result)
        (result / 'app.py').write_bytes(b'new result\r\n')
        (result / 'gone.txt').unlink()
        (result / 'binary.bin').write_bytes(b'\x00\xff')
        current = files.inventory(result)
        bundle = self.root / 'bundle'
        report = files.report_bundle(self.seed, manifest, result, current, bundle)
        self.assertEqual(report['changed'], ['app.py'])
        self.assertEqual(report['deleted'], ['gone.txt'])
        self.assertEqual(report['added'], ['binary.bin'])
        self.assertEqual((bundle / 'files/app.py').read_bytes(), b'new result\r\n')
        self.assertEqual((bundle / 'files/binary.bin').read_bytes(), b'\x00\xff')
        self.assertFalse((bundle / 'files/gone.txt').exists())
        diff = (bundle / 'diff.patch').read_bytes()
        self.assertIn(b'+new result', diff)
        self.assertIn(b'Diff summary for binary.bin: binary content', diff)
        self.assertTrue(report['text_diff_limited'])
        self.assertEqual(report['diff_sha256'], hashlib.sha256(diff).hexdigest())
        self.assertNotIn(str(self.root), diff.decode())
        self.assertEqual(json.loads((bundle / 'manifest.json').read_text()), current)
        self.assertEqual(json.loads((bundle / 'report.json').read_text()), report)
        self.assertEqual(files.inventory(self.repo)['files'], original)

    def test_fresh_destination_never_overwrites_unrelated_files(self):
        self.seed.mkdir()
        marker = self.seed / 'keep.txt'
        marker.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):
            self.snapshot()
        self.assertEqual(marker.read_bytes(), b'preserve')

    def test_text_diff_preserves_missing_final_newline_changes(self):
        self.put('app.py', b'unchanged line')
        manifest = self.snapshot()
        result = self.root / 'attempt'
        files.materialize(self.seed, manifest, result)
        (result / 'app.py').write_bytes(b'unchanged line\n')
        bundle = self.root / 'bundle'
        files.report_bundle(self.seed, manifest, result, files.inventory(result), bundle)
        diff = (bundle / 'diff.patch').read_text()
        self.assertIn('-unchanged line\n\\ No newline at end of file', diff)
        self.assertIn('+unchanged line', diff)

    def test_oversized_text_diff_is_summarized_without_difflib_but_exact_bytes_survive(self):
        self.put('app.py', b'old large line' * 100)
        manifest = self.snapshot()
        result = self.root / 'attempt'
        files.materialize(self.seed, manifest, result)
        expected = b'new large line' * 100
        (result / 'app.py').write_bytes(expected)
        bundle = self.root / 'bundle'
        with patch.object(files, 'MAX_DIFF_FILE_BYTES', 1024), \
             patch.object(files.difflib, 'unified_diff') as algorithm:
            report = files.report_bundle(self.seed, manifest, result, files.inventory(result), bundle)
        algorithm.assert_not_called()
        self.assertTrue(report['text_diff_limited'])
        self.assertIn(b'text size limit', (bundle / 'diff.patch').read_bytes())
        self.assertEqual((bundle / 'files/app.py').read_bytes(), expected)
        self.assertEqual(json.loads((bundle / 'manifest.json').read_text())['files']['app.py']['sha256'],
                         hashlib.sha256(expected).hexdigest())

    def test_total_text_diff_cap_preserves_all_files_and_emits_a_bounded_summary(self):
        for index in range(12):
            self.put('text-' + str(index) + '.txt', b'old line\n' * 10)
        manifest = self.snapshot()
        result = self.root / 'attempt'
        files.materialize(self.seed, manifest, result)
        for index in range(12):
            (result / ('text-' + str(index) + '.txt')).write_bytes(b'new line\n' * 10)
        current = files.inventory(result)
        bundle = self.root / 'bundle'
        with patch.object(files, 'MAX_DIFF_TOTAL_BYTES', 1024):
            report = files.report_bundle(self.seed, manifest, result, current, bundle)
        diff = (bundle / 'diff.patch').read_bytes()
        self.assertTrue(report['text_diff_limited'])
        self.assertLessEqual(len(diff), 1024)
        self.assertIn(b'Diff size limit reached', diff)
        self.assertEqual(len(report['changed']), 12)
        files.assert_snapshot(bundle / 'files', current)

    def test_materialize_and_bundle_refuse_tampered_seeds_before_creating_destination(self):
        manifest = self.snapshot()
        (self.seed / 'app.py').write_bytes(b'tampered')
        for operation in (
                lambda dest: files.materialize(self.seed, manifest, dest),
                lambda dest: files.report_bundle(self.seed, manifest, self.repo, files.inventory(self.repo), dest)):
            dest = self.root / 'refused'
            with self.assertRaises(PolicyError):
                operation(dest)
            self.assertFalse(dest.exists())

    def test_source_drift_during_copy_is_refused(self):
        original_write = files._write
        def changing(root, name, raw, executable=False):
            original_write(root, name, raw, executable)
            self.put('app.py', b'mutated during copy')
        with patch.object(files, '_write', side_effect=changing), self.assertRaises(PolicyError):
            self.snapshot()

    def test_file_hardlinks_are_refused(self):
        os.link(self.repo / 'app.py', self.repo / 'hardlink.py')
        for operation in (self.snapshot, lambda: files.inventory(self.repo)):
            with self.assertRaises(PolicyError):
                operation()

    def test_symlinks_are_refused_without_following_their_targets(self):
        try:
            (self.repo / 'linked.py').symlink_to(self.repo / 'app.py')
        except OSError as error:
            self.skipTest('host does not permit symlink creation: ' + str(error))
        for operation in (self.snapshot, lambda: files.inventory(self.repo)):
            with self.assertRaises(PolicyError):
                operation()

    def test_reparse_points_are_refused(self):
        original = Path.lstat
        target = self.repo / 'app.py'
        def reparse(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400) if path == target else info
        with patch.object(Path, 'lstat', reparse), self.assertRaises(PolicyError):
            files.inventory(self.repo)

    def test_manifest_path_aliases_escapes_private_paths_and_invalid_rows_are_refused(self):
        manifest = self.snapshot()
        row = manifest['files']['app.py']
        for names in (['../escape'], ['/absolute'], ['a\\b'], ['C:drive'], ['a/./b'], ['a//b'],
                      ['bad.'], ['bad '], ['NUL.txt'], ['x\0y'], ['App.py', 'app.py'],
                      ['Folder/a', 'folder/b'], ['a', 'a/b'], ['.env'], ['.codex/secret']):
            with self.subTest(names=names), self.assertRaises(PolicyError):
                files.materialize(self.seed, {'schema': 1, 'files': {n: row for n in names}, 'omitted': []},
                                  self.root / 'invalid')
        self.assertFalse((self.root / 'invalid').exists())
        for change in ({'size': True}, {'size': -1}, {'sha256': 'bad'}, {'executable': 1}):
            bad = {'schema': 1, 'files': {'app.py': {**row, **change}}, 'omitted': []}
            with self.subTest(change=change), self.assertRaises(PolicyError):
                files.manifest_hash(bad)

    def test_limits_fail_without_silent_truncation(self):
        for constant, bound in (('MAX_FILES', 1), ('MAX_TOTAL_BYTES', 1), ('MAX_FILE_BYTES', 1)):
            with self.subTest(constant=constant), patch.object(files, constant, bound):
                with self.assertRaises(PolicyError):
                    files.inventory(self.repo)

    def test_source_metadata_requires_nul_filename_termination(self):
        with patch.object(files, '_git', return_value=b'app.py'), self.assertRaises(PolicyError):
            files._source(self.repo)

    def test_canonical_manifest_hash_is_order_independent(self):
        manifest = self.snapshot()
        reversed_manifest = dict(reversed(list(manifest.items())))
        reversed_manifest['files'] = dict(reversed(list(manifest['files'].items())))
        self.assertEqual(files.manifest_hash(manifest), files.manifest_hash(reversed_manifest))
        changed_metadata = {**manifest, 'omitted': ['ignored-private-file']}
        self.assertEqual(files.content_hash(manifest), files.content_hash(changed_metadata))
        self.assertNotEqual(files.manifest_hash(manifest), files.manifest_hash(changed_metadata))

    def test_project_inventory_is_read_only_and_detects_dirty_origin_without_ignored_dependencies(self):
        self.put('.gitignore', b'ignored/\n')
        self.put('ignored/dependency', b'ignored')
        original = files.project_inventory(self.repo)
        self.assertFalse(self.seed.exists())
        self.assertNotIn('ignored/dependency', original['files'])
        self.put('app.py', b'dirty original')
        self.put('untracked.txt', b'current working bytes')
        current = files.project_inventory(self.repo)
        self.assertNotEqual(files.content_hash(original), files.content_hash(current))
        self.assertIn('untracked.txt', current['files'])
        self.assertEqual(current['source_head'], original['source_head'])

    def test_executable_mode_is_preserved_on_posix(self):
        if os.name == 'nt':
            self.skipTest('Windows does not preserve POSIX executable bits')
        (self.repo / 'app.py').chmod(0o755)
        manifest = self.snapshot()
        files.materialize(self.seed, manifest, self.root / 'attempt')
        self.assertTrue(manifest['files']['app.py']['executable'])
        self.assertTrue((self.root / 'attempt/app.py').stat().st_mode & stat.S_IXUSR)

    def test_seed_may_live_in_excluded_workflow_control_but_not_ordinary_source(self):
        control = self.repo / '.codex-flow/workflows/workflow-id'
        control.mkdir(parents=True)
        (control / 'workflow.sqlite').write_bytes(b'fixture state')
        self.seed = control / 'seed'
        self.snapshot()
        self.assertEqual(set(files.inventory(self.seed)['files']), {'app.py', 'gone.txt'})
        with self.assertRaises(PolicyError):
            files.seed_project(self.repo, self.repo / 'ordinary-output')
        self.assertFalse((self.repo / 'ordinary-output').exists())

    def test_nested_control_git_workspace_does_not_change_project_content_or_enter_a_seed(self):
        original = self.snapshot()
        workspace = self.repo / '.codex-flow/workflows/id/attempts/generate/attempt/workspace'
        workspace.parent.mkdir(parents=True)
        files.materialize(self.seed, original, workspace)
        self.git('init', '--template=', str(workspace))
        (workspace / 'private-output.txt').write_bytes(b'generated fixture; never execute')
        metadata = self.git('ls-files', '-z', '--cached', '--others', '--exclude-standard')
        relative = workspace.relative_to(self.repo).as_posix()
        self.assertIn((relative + '/').encode() + b'\0', metadata)
        current = files.project_inventory(self.repo)
        self.assertEqual(files.content_hash(original), files.content_hash(current))
        self.assertEqual(set(current['files']), {'app.py', 'gone.txt'})
        copied = files.seed_project(self.repo, self.root / 'second-seed')
        self.assertEqual(copied['files'], original['files'])
        self.assertFalse((self.root / 'second-seed/.codex-flow').exists())


if __name__ == '__main__':
    unittest.main()
