"""Owned native clocks and metadata-only operation fingerprints; no execution."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from codex_flow import native
from codex_flow.budget import ExecutionBudget
from codex_flow.config import Config
import test_native_failures as fixture


class NativeBudgetTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()

    def test_shared_clock_includes_login_preparation(self):
        clock=[0.]
        budget=ExecutionBudget(100,clock=lambda:clock[0])
        process=fixture.Process(fixture.Input(),[{'type':'turn.completed','usage':{}}])
        def prepared(_):clock[0]=60
        with patch.object(native,'subscription',side_effect=prepared),patch.object(native.subprocess,'Popen',return_value=process):
            result=native._run('fake',self.root,Config(timeout_s=100),'task',self.root/'run',execution_budget=budget)
        self.assertEqual(result['execution_budget']['remaining_s'],40)
        self.assertEqual(result['execution_budget']['phase'],'stabilize')
        self.assertEqual(result['status'],'completed_unverified')

    def test_operation_hashes_repeat_only_within_run_without_command_persistence(self):
        command='synthetic private command and arguments'
        all_hashes=[]
        for n in (1,2):
            events=[]
            for item in ('item-1','item-2'):
                body={'type':'command_execution','id':item,'command':command,'status':'completed','exit_code':0}
                events += [{'type':'item.started','item':body},{'type':'item.completed','item':body}]
            events.append({'type':'turn.completed','usage':{}})
            process=fixture.Process(fixture.Input(),events)
            folder=self.root/f'run-{n}'
            with patch.object(native,'subscription'),patch.object(native.subprocess,'Popen',return_value=process):
                native._run('fake',self.root,Config(),'task',folder)
            raw=(folder/'events.jsonl').read_text()
            self.assertNotIn(command,raw)
            self.assertNotIn('arguments',raw)
            completed=[json.loads(line)['payload'] for line in raw.splitlines() if json.loads(line)['event_type']=='native.item.completed']
            self.assertEqual(len(completed),2)
            hashes=[item['operation_hash'] for item in completed]
            self.assertEqual(hashes[0],hashes[1])
            self.assertEqual(len(hashes[0]),64)
            self.assertTrue(all(item['tool_duration_s']>=0 for item in completed))
            all_hashes.append(hashes[0])
        self.assertNotEqual(*all_hashes)


if __name__=='__main__':unittest.main()
