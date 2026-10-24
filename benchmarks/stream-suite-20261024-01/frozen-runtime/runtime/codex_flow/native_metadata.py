"""Narrow read-only parent-linked metadata for one CLI-observed root thread.

Only this workspace's existing state file is consulted after process termination.
No historical rollout files, titles, nicknames or global databases are opened.
"""
from __future__ import annotations
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from .contracts import inside


def canonical_cwd(value):
    text = str(value)
    if text.startswith('\\\\?\\UNC\\'): text = '\\\\' + text[8:]
    elif text.startswith('\\\\?\\'): text = text[4:]
    if re.match(r'^[A-Za-z]:[\\/]|^\\\\', text):
        return ntpath.normcase(ntpath.normpath(text))
    if not Path(text).is_absolute(): return None
    return os.path.normcase(str(Path(text).resolve()))


def thread_hash(value):
    if not isinstance(value, str): return None
    try: uuid.UUID(value)
    except (ValueError, AttributeError): return None
    return hashlib.sha256(value.encode()).hexdigest()


def observe_children(workspace: Path, root_id):
    """Return sanitized evidence or a fixed unavailable reason, never raw rows."""
    def unavailable(reason):
        return {'status': 'unavailable', 'reason': reason, 'children': None}
    root_hash = thread_hash(root_id)
    if root_hash is None: return unavailable('root_id_unavailable')
    connection = None
    try:
        database = inside(workspace, workspace / '.codex-flow/native-state/state_5.sqlite')
        for suffix in ('-wal', '-shm'): inside(workspace, Path(str(database) + suffix))
        if not database.is_file(): return unavailable('state_missing')
        connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=.2)
        connection.execute('PRAGMA query_only=ON')
        deadline = time.monotonic() + .2
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        columns = {row[1] for row in connection.execute('PRAGMA table_info(threads)')}
        if not {'id', 'cwd', 'source', 'tokens_used', 'model', 'reasoning_effort'} <= columns:
            return unavailable('state_schema')
        own = connection.execute('SELECT cwd FROM threads WHERE id=?', (root_id,)).fetchone()
        if own is None or not isinstance(own[0], str) or canonical_cwd(own[0]) != canonical_cwd(workspace):
            return unavailable('root_cwd_mismatch')
        if connection.execute('SELECT source FROM threads WHERE id=?', (root_id,)).fetchone() != ('exec',):
            return unavailable('root_source_schema')
        # Source is the only candidate field read before proving the exact parent.
        # LIKE is a narrow UUID prefilter, never evidence of a parent relationship.
        candidates = connection.execute('SELECT id,source FROM threads WHERE source LIKE ? AND length(source)<=4096 LIMIT 65',
                                        ('%' + root_id + '%',)).fetchall()
        if len(candidates) > 64: return unavailable('candidate_limit')
        children = []
        for child_id, source in candidates:
            try:
                document = json.loads(source)
                subagent = document.get('subagent') if isinstance(document, dict) else None
                spawn = subagent.get('thread_spawn') if isinstance(subagent, dict) else None
            except (ValueError, TypeError): continue
            if not isinstance(spawn, dict) or spawn.get('parent_thread_id') != root_id: continue
            if type(spawn.get('depth')) is not int or spawn['depth'] != 1 or not isinstance(spawn.get('agent_role'), str):
                return unavailable('parent_link_schema')
            child_hash = thread_hash(child_id)
            if child_hash is None or child_id == root_id: return unavailable('child_id_schema')
            row = connection.execute('SELECT cwd,tokens_used,model,reasoning_effort FROM threads WHERE id=?', (child_id,)).fetchone()
            if row is None or not isinstance(row[0], str) or canonical_cwd(row[0]) != canonical_cwd(workspace): continue
            if type(row[1]) is not int or not 0 < row[1] <= 2**63 - 1: continue
            model = row[2] if isinstance(row[2], str) and re.fullmatch(r'[A-Za-z0-9._:/-]{1,128}', row[2]) else None
            effort = row[3] if row[3] in ('low', 'medium', 'high', 'xhigh', 'max') else None
            children.append({'thread_sha256': child_hash, 'model': model, 'requested_effort': effort,
                             'depth': 1, 'tokens_used': row[1]})
        return {'status': 'observed', 'reason': 'native_parent_link_and_usage_metadata' if children else 'no_used_children',
                'root_sha256': root_hash, 'children': children, 'peak_concurrent_agents': None}
    except (OSError, ValueError, sqlite3.Error):
        return unavailable('state_unavailable')
    finally:
        if connection is not None: connection.close()
