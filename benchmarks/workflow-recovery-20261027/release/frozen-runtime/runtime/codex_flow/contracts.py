"""Small, serializable contracts; no model output can grant permissions."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import math
import stat

class PolicyError(ValueError):
    pass

@dataclass(frozen=True)
class TaskSpec:
    id: str
    requirement: str
    allowed_paths: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    risk_level: str = 'normal'
    max_budget: int | None = None
    deadline: str | None = None
    seed: int | None = None

@dataclass(frozen=True)
class RouteDecision:
    strategy: str
    reason: str
    source: str = 'rules'
    model: str = 'gpt-6.1-sol'
    effort: str = 'xhigh'
    confidence: float | None = None
    fallback_reason: str | None = None

@dataclass
class IntegrationHealth:
    status: str = 'disabled'
    configured: bool = False
    reachable: bool | None = None
    validated: bool = False
    active: bool = False
    fallback: str = 'deterministic'
    reason: str | None = None
    version: str | None = None
    provider: str | None = None
    spend_policy: str = 'no-paid-api'

@dataclass
class AgentRun:
    run_id: str
    model: str = 'gpt-6.1-sol'
    effort: str = 'xhigh'
    adapter: str = 'native-codex-cli'
    status: str = 'pending'
    attempts: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None

@dataclass(frozen=True)
class ExecutionPlan:
    tasks: tuple[TaskSpec, ...]

    def ready_batches(self) -> list[list[str]]:
        by_id = {t.id: t for t in self.tasks}
        if len(by_id) != len(self.tasks): raise PolicyError('duplicate task id')
        if any(d not in by_id for t in self.tasks for d in t.dependencies):
            raise PolicyError('unknown dependency')
        done: set[str] = set()
        batches = []
        while len(done) < len(by_id):
            ready = [t for t in self.tasks if t.id not in done and set(t.dependencies) <= done]
            if not ready: raise PolicyError('cyclic task graph')
            owned: list[Path] = []
            batch = []
            for task in ready:
                paths = [Path(p).resolve() for p in task.allowed_paths]
                if not any(a == b or a in b.parents or b in a.parents for a in paths for b in owned):
                    batch.append(task.id); owned.extend(paths)
            batches.append(batch); done.update(batch)
        return batches

def inside(root: Path, path: Path) -> Path:
    for item in (path,*path.parents):
        try:info=item.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise PolicyError('link or junction boundary refused')
    root, path = root.resolve(), path.resolve()
    if path != root and root not in path.parents: raise PolicyError('path outside allowed root')
    return path
