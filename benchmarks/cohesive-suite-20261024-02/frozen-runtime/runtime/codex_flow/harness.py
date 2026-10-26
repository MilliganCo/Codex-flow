"""Harness2-inspired local instruction probes, never upstream Codex execution."""
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib, json, math
from .contracts import PolicyError, inside
from .telemetry import write_json, utc

def runtime_guard():
    """Do not spend a task's budget calibrating an unvalidated proxy objective.

    Plan coverage and faster plan generation do not measure application quality.
    Keep this enabled guard explicit, but defer calibration outside the task's
    critical path. No active instruction file is loaded or promoted implicitly.
    """
    return {'status':'deferred','mode':'Harness2-inspired','upstream_probes':0,
            'inspired_probes':0,'runs':[],'decision':{'adopted':False},
            'application_quality_eligible':False,
            'reason':'no independent application-quality calibration; online plan probes disabled',
            'limitation':'guard only; no measured optimizer benefit or upstream Harness2 execution'}

@dataclass(frozen=True)
class HarnessProposal:
    id: str
    instructions: str
    expected_effect: str
    probe_ids: tuple[str,...] = ()

@dataclass(frozen=True)
class EvaluationResult:
    quality: float
    duration_s: float
    safety_passed: bool
    complete: bool
    probe_id: str

    def __post_init__(self):
        if type(self.safety_passed) is not bool or type(self.complete) is not bool:raise PolicyError('expected boolean evidence')
        if not isinstance(self.probe_id,str) or not self.probe_id:raise PolicyError('probe evidence missing')
        for v in (self.quality,self.duration_s):
            if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise PolicyError('invalid measured metrics')

class GuardedHarness:
    def __init__(self,root:Path,max_refinements=1):
        if type(max_refinements) is not int or max_refinements not in (1,2):raise PolicyError('probe budget exceeded')
        self.root=root.resolve();self.maximum=max_refinements
        self.store=inside(self.root,self.root/'.codex-flow'/'lessons')
    def compare(self,proposal:HarnessProposal,baseline:EvaluationResult,candidate:EvaluationResult,*,adopt=False):
        if type(adopt) is not bool:raise PolicyError('expected boolean adoption')
        inside(self.root,self.store)
        if not proposal.id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in proposal.id):
            raise PolicyError('invalid proposal id')
        if any(not math.isfinite(v) or v<0 for v in (baseline.quality,candidate.quality,baseline.duration_s,candidate.duration_s)):
            raise PolicyError('invalid measured metrics')
        self.store.mkdir(parents=True,exist_ok=True)
        if len(list(self.store.glob('proposal-*.json')))>=self.maximum:raise PolicyError('probe budget exceeded')
        if (self.store/('proposal-'+proposal.id+'.json')).exists():raise PolicyError('proposal already recorded')
        better=(candidate.quality>baseline.quality or (candidate.quality==baseline.quality and candidate.duration_s<baseline.duration_s))
        eligible=bool(candidate.safety_passed and baseline.safety_passed and candidate.complete and baseline.complete and candidate.probe_id!=baseline.probe_id and better)
        record={'mode':'Harness2-inspired','proposal':asdict(proposal),'baseline':asdict(baseline),'candidate':asdict(candidate),
                'eligible':eligible,'adopted':eligible and adopt,'timestamp':utc()}
        target=inside(self.root,self.store/'active.txt')
        if record['adopted']:
            record['previous']=target.read_text(encoding='utf-8') if target.exists() else None
            target.write_text(proposal.instructions,encoding='utf-8')
            record['adopted_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        write_json(self.store/('proposal-'+proposal.id+'.json'),record)
        return record
    def rollback(self,proposal_id):
        if not proposal_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in proposal_id):raise PolicyError('invalid proposal id')
        record_path=inside(self.root,self.store/('proposal-'+proposal_id+'.json'))
        record=json.loads(record_path.read_text(encoding='utf-8'))
        target=inside(self.root,self.store/'active.txt')
        if not record.get('adopted'):raise PolicyError('proposal was not adopted')
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=record['adopted_sha256']:
            raise PolicyError('active instructions changed; rollback refused')
        if record['previous'] is None:target.unlink()
        else:target.write_text(record['previous'],encoding='utf-8')
        record['rolled_back']=True;write_json(record_path,record)
        return record
