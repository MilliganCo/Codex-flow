"""Strict, project-local JSON configuration with fail-closed migration."""
from dataclasses import dataclass, asdict, fields
from pathlib import Path
import json
from .contracts import PolicyError

@dataclass(frozen=True)
class Config:
    schema_version: int = 1
    enabled: bool = False
    mode: str = 'safe'
    max_agents: int = 3
    max_depth: int = 1
    max_attempts: int = 1
    timeout_s: int = 1200
    model: str = 'gpt-6.1-sol'
    effort: str = 'xhigh'
    mercury: bool = False
    harness2: bool = False
    max_refinements: int = 1
    allow_paid_api: bool = False
    max_model_requests: int = 80
    native_request_retries: int = 0

    def __post_init__(self):
        for name in ('enabled','mercury','harness2','allow_paid_api'):
            if type(getattr(self,name)) is not bool: raise PolicyError('expected boolean: '+name)
        for name, lo, hi in [('schema_version',1,1),('max_agents',1,3),('max_depth',1,1),
                             ('max_attempts',1,2),('timeout_s',1,3600),('max_refinements',1,2),('max_model_requests',1,80),
                             ('native_request_retries',0,1)]:
            v=getattr(self,name)
            if type(v) is not int or not lo <= v <= hi: raise PolicyError('invalid bound: '+name)
        if self.mode not in ('safe','benchmark','experimental'): raise PolicyError('invalid mode')
        if self.model != 'gpt-6.1-sol' or self.effort != 'xhigh': raise PolicyError('unverified root model/effort')
        if self.allow_paid_api: raise PolicyError('paid API unsupported; separate authorization required')

def load(path: Path | None) -> Config:
    if path is None or not path.exists(): return Config()
    raw=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(raw,dict): raise PolicyError('config must be object')
    if set(raw)-{f.name for f in fields(Config)}: raise PolicyError('unknown config fields')
    return Config(**raw)
