"""Offline model metadata tests; no native login, dispatch, or paid API requests."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow.config import Config
from codex_flow.contracts import PolicyError
from codex_flow.workflow_models import catalog


class ModelCatalogTests(unittest.TestCase):
    def models(self, version=None):
        return {model['id']: model for model in catalog(version)['models']}

    def test_catalog_separates_wiring_from_account_verification(self):
        result = catalog()
        self.assertEqual(result['schema'], 1)
        self.assertEqual(result['default_chief'], 'gpt-6.1-sol')
        models = self.models()
        self.assertEqual(set(models), {'gpt-6.1-sol', 'gpt-6-luna', 'gpt-6.1-terra'})
        sol, luna, terra = (models[key] for key in ('gpt-6.1-sol', 'gpt-6-luna', 'gpt-6.1-terra'))
        self.assertEqual((sol['roles'], sol['default_effort']), (['chief'], 'xhigh'))
        self.assertTrue(sol['flow_dispatch_enabled'])
        self.assertIsNone(sol['native_account_verified'])
        self.assertEqual(sol['validation_status'], 'native_verified')
        self.assertEqual(luna['roles'], ['optional_executor'])
        self.assertTrue(luna['flow_dispatch_enabled'])
        self.assertIsNone(luna['native_account_verified'])
        self.assertEqual(luna['validation_status'], 'configured_unverified')
        self.assertEqual(terra['roles'], ['visual_review', 'scoped_code_fix'])
        self.assertEqual(terra['default_effort'], 'medium')
        self.assertFalse(terra['flow_dispatch_enabled'])
        self.assertIsNone(terra['native_account_verified'])
        self.assertEqual(terra['validation_status'], 'documented_candidate')
        self.assertEqual(terra['cli_min_version'], '0.159.0')
        self.assertIsNone(terra['cli_compatible'])
        for model in models.values():
            self.assertIsNone(model['native_account_verified'])
            self.assertTrue(model['official_source'].startswith('https://developers.openai.com/'))
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_results_are_fresh_nested_copies(self):
        expected = catalog('0.164.0-alpha.11.1')
        changed = catalog('0.164.0-alpha.11.1')
        changed['default_chief'] = 'changed'
        changed['models'][0]['roles'].append('changed')
        changed['models'][2]['flow_dispatch_enabled'] = True
        changed['models'].pop()
        self.assertEqual(catalog('0.164.0-alpha.11.1'), expected)

    def test_cli_version_threshold_and_prereleases(self):
        cases = {
            '0.158.9': False,
            '0.159.0-alpha.1': False,
            '0.159.0': True,
            '0.159.0+build.1': True,
            '0.159.1-alpha.1': True,
            '0.164.0-alpha.11.1': True,
            'codex-cli 0.164.0-alpha.11.1': True,
            '1.0.0': True,
        }
        for version, compatible in cases.items():
            with self.subTest(version=version):
                self.assertIs(self.models(version)['gpt-6.1-terra']['cli_compatible'], compatible)

    def test_cli_version_rejects_partial_or_ambiguous_input(self):
        invalid = ('', '0.159', '0.159.0.1', 'v0.159.0', 'codex 0.159.0',
                   ' 0.159.0', '0.159.0\n', '0.159.0 trailing', '00.159.0',
                   '0.0159.0', '0.159.00', '0.159.0-alpha..1', '0.159.0-alpha.01',
                   '0.159.0+', '0.159.0-!', '０.159.0', '9' * 129)
        for version in invalid:
            with self.subTest(version=version):
                self.assertIs(self.models(version)['gpt-6.1-terra']['cli_compatible'], False)

    def test_catalog_does_not_call_processes_network_or_write_files(self):
        with patch('subprocess.run') as process, patch('socket.create_connection') as network, \
                patch.object(Path, 'write_text') as write:
            catalog('codex-cli 0.164.0-alpha.11.1')
        process.assert_not_called()
        network.assert_not_called()
        write.assert_not_called()

    def test_cli_compatibility_does_not_enable_dispatch_or_change_defaults(self):
        terra = self.models('0.164.0-alpha.11.1')['gpt-6.1-terra']
        self.assertTrue(terra['cli_compatible'])
        self.assertFalse(terra['flow_dispatch_enabled'])
        self.assertIsNone(terra['native_account_verified'])
        self.assertEqual((Config().model, Config().effort, Config().allow_paid_api),
                         ('gpt-6.1-sol', 'xhigh', False))
        with self.assertRaises(PolicyError):
            Config(model='gpt-6.1-terra')


if __name__ == '__main__':
    unittest.main()
