"""Freeze generic task metadata without changing the canonical Tree defaults."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from codex_flow import benchmark
from codex_flow.contracts import PolicyError


def ledger():
    return {'id':'ledgerreconcile.v1','acceptance':'All 20 frozen criteria pass; score=100',
            'quality_scores':{f'L{i:02}':5 for i in range(1,21)},
            'terminal':'offline subprocess CLI evaluation in the official SDK sandbox'}


class ContractTests(unittest.TestCase):
    def test_tree_defaults_remain_original(self):
        value=benchmark.task_contract()
        self.assertEqual(value['id'],'ascii-tree.v1')
        self.assertEqual(value['quality_scores'],{'2d':12,'3d':13,'4d':20,'ux':12,'aesthetics':12,
                         'reliability':10,'tests':9,'maintainability':7,'readme':5})
        self.assertIn('score>=80',value['acceptance'])

    def test_new_task_weights_are_copied_and_validated(self):
        original=ledger();frozen=benchmark.task_contract(original)
        original['quality_scores']['L01']=1
        self.assertEqual(frozen['quality_scores']['L01'],5)
        for change in ({'id':'../bad'},{'quality_scores':{'bad':True}},
                       {'quality_scores':{'bad':99}},{'extra':'unknown'}, {'acceptance':''}):
            value=ledger();value.update(change)
            with self.subTest(change=change),self.assertRaises(PolicyError):benchmark.task_contract(value)

    def test_prepare_records_actual_contract_and_literal_brief(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);task=root/'task.md';evaluator=root/'evaluator.py'
            task.write_bytes(b'Literal neutral synthetic task\n');evaluator.write_bytes(b'# inert\n')
            evaluator.with_name('rubric.json').write_text('{}')
            with patch.object(benchmark,'git',return_value='frozen-scaffold'), \
                    patch.object(benchmark,'hardware',return_value={}), \
                    patch.object(benchmark.subprocess,'run',return_value=SimpleNamespace(stdout='codex-cli fixture')):
                result=benchmark.prepare(root/'experiment',task,evaluator,'fake',1500,'AB',contract=ledger())
            self.assertEqual(result['task_kind'],'ledgerreconcile.v1')
            self.assertEqual(result['quality_scores_frozen'],ledger()['quality_scores'])
            self.assertEqual((root/'experiment/frozen/TASK.md').read_bytes(),task.read_bytes())
            self.assertEqual(json.loads((root/'experiment/experiment-manifest.json').read_text())['acceptance'],ledger()['acceptance'])


if __name__=='__main__':unittest.main()
