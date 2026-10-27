"""Read-only role catalog; metadata never grants model dispatch or account access."""
from __future__ import annotations

import re
from typing import Any


_VERSION = re.compile(
    r'(?:codex-cli )?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
    r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
    r'(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?'
)


def _terra_cli_compatible(version: str | None) -> bool | None:
    if version is None:
        return None
    if not isinstance(version, str) or len(version) > 128:
        return False
    match = _VERSION.fullmatch(version)
    if match is None:
        return False
    prerelease = match.group(4)
    if prerelease and any(part.isdigit() and len(part) > 1 and part[0] == '0'
                          for part in prerelease.split('.')):
        return False
    release = tuple(int(part) for part in match.group(1, 2, 3))
    return release > (0, 159, 0) or (release == (0, 159, 0) and prerelease is None)


def catalog(cli_version: str | None = None) -> dict[str, Any]:
    """Return fresh metadata without inspecting configuration, login, or native CLI.

    Efforts describe Codex Flow's existing roles or the candidate's documented
    default. CLI compatibility checks syntax/version only, never account access.
    Dispatch flags describe existing wiring, not permission to execute it.
    Validation status records historical Flow evidence; caller access is unknown.
    """
    return {
        'schema': 1,
        'default_chief': 'gpt-6.1-sol',
        'models': [
            {
                'id': 'gpt-6.1-sol',
                'roles': ['chief'],
                'default_effort': 'xhigh',
                'flow_dispatch_enabled': True,
                'validation_status': 'native_verified',
                'native_account_verified': None,
                'official_source': 'https://developers.openai.com/api/docs/models/gpt-6.1-sol',
            },
            {
                'id': 'gpt-6-luna',
                'roles': ['optional_executor'],
                'default_effort': 'medium',
                'flow_dispatch_enabled': True,
                'validation_status': 'configured_unverified',
                'native_account_verified': None,
                'official_source': 'https://developers.openai.com/api/docs/models/gpt-6-luna',
            },
            {
                'id': 'gpt-6.1-terra',
                'roles': ['visual_review', 'scoped_code_fix'],
                'default_effort': 'medium',
                'flow_dispatch_enabled': False,
                'validation_status': 'documented_candidate',
                'native_account_verified': None,
                'official_source': 'https://developers.openai.com/api/docs/models/gpt-6.1-terra',
                'cli_min_version': '0.159.0',
                'cli_compatible': _terra_cli_compatible(cli_version),
            },
        ],
    }
