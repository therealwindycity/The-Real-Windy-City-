#!/usr/bin/env python3
"""Decide whether a city-mirror snapshot is safe to cache as last-known-good.

GitHub Actions cache restore-keys pick the *most recent* prefix match. Saving a
truncated or unreadable snapshot would hide a previous good cache. This script
exits 0 only for a readable, well-shaped state file so the workflow can skip
the cache save otherwise.

Usage:
    python3 tools/validate_mirror_snapshot.py [.cache/city-mirror/state.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ALLOWED_RUN_STATUS = {'completed', 'partial', 'failed', 'running', 'not yet run'}


def validate(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f'no snapshot at {path}')
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f'unreadable snapshot: {error}') from error
    if not isinstance(state, dict) or not isinstance(state.get('records'), dict):
        raise ValueError('snapshot shape invalid: expected {"records": {...}}')
    if 'changes' in state and not isinstance(state['changes'], list):
        raise ValueError('snapshot shape invalid: expected "changes" to be a list')
    run = state.get('latest_run')
    if run is None:
        status = 'not yet run'
    elif not isinstance(run, dict):
        raise ValueError('snapshot shape invalid: expected "latest_run" to be an object')
    else:
        status = run.get('status', 'not yet run')
        if status not in ALLOWED_RUN_STATUS:
            raise ValueError(f'unknown latest_run.status: {status!r}')
    return f'snapshot ok: {len(state["records"])} records, status={status}'


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0] if args else '.cache/city-mirror/state.json')
    try:
        print(validate(path))
        return 0
    except ValueError as error:
        print(error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
