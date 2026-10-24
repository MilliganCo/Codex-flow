"""Independent, fixed 57-check case10 ConPTY protocol. Execute only in SDK."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import MappingProxyType

from conpty_case10_neutral import WindowsConsole

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_inventory(root, frozen_sources):
    return {name: digest(root / name) if (root / name).is_file() else None
            for name in frozen_sources}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solution-root', required=True, type=Path)
    parser.add_argument('--solution-id', required=True, type=int, choices=(23, 24))
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    root, out, sid = args.solution_root.resolve(), args.output_dir.resolve(), args.solution_id
    if root.name != f'solution-{sid}' or not root.is_dir() or out.is_relative_to(root):
        parser.error('Expected matching anonymous root and external new output directory')
    out.mkdir(parents=True, exist_ok=False)
    export_dir = out / 'exports'
    export_dir.mkdir()
    frozen_sources = MappingProxyType(dict(json.loads((root.parent / 'source-hashes.json').read_text('utf-8'))[root.name]))
    before = source_inventory(root, frozen_sources)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONHASHSEED'] = '0'
    os.environ['PYTHONPATH'] = str(root)
    spec = ({'pitch': -7, 'yaw_step': 8, 'pitch_step': 6, 'hyper_step': 8,
             'hyper_flag': '--angle4d', 'help': b'CONTROLS / same tree in every mode'}
            if sid == 23 else
            {'pitch': 8, 'yaw_step': 7, 'pitch_step': 5, 'hyper_step': 10,
             'hyper_flag': '--angle4', 'help': b'ASCII TREE EXPLORER / HELP'})
    state = dict(seed=42, mode='2d', yaw=25, pitch=spec['pitch'], hyper=0, zoom=1, time=0)
    report = {'schema': 1, 'solution_id': sid, 'protocol': 'conpty-case10-protocol.md',
              'fixed_checks': 57, 'checks': [], 'embedded_3d': [], 'oracles': [],
              'sessions': [], 'runtime_repairs': [], 'source_before': before,
              'source_baseline_match_before': before == dict(frozen_sources),
              'checker_sha256': digest(Path(__file__)),
              'support_sha256': digest(HERE / 'conpty_case10_neutral.py'),
              'complete': False, 'error': None}
    check_no = 0
    export_no = 0
    sessions = []

    def check(name, ok, **evidence):
        nonlocal check_no
        check_no += 1
        item = dict(number=check_no, name=name, status='pass' if ok else 'fail', **evidence)
        report['checks'].append(item)
        return ok

    def dimensions(size):
        w, h = size
        if sid == 23:
            w = max(1, min(999, w - 1))
            h = max(1, min(250, h))
            return w, max(1, h - 1) if h < 8 or w < 24 else h - 5
        return max(1, min(500, w)), max(1, min(240, h) - (1 if h < 7 else 4))

    def bounded_ascii(raw, width, height):
        rows = raw.split(b'\n')
        shape = raw.endswith(b'\n') and len(rows) == height + 1 and rows[-1] == b'' and all(len(r) == width for r in rows[:-1])
        clean = b'\r' not in raw and all(32 <= b <= 126 or b == 10 for b in raw)
        return shape, clean

    def launch(label):
        command = ['-m', 'ascii_tree', 'view', '--seed', '42', '--mode', '2d', '--export-dir', str(export_dir)]
        console = WindowsConsole(command, root, 100, 40)
        sessions.append((label, console))
        console.wait_for(lambda: b'ASCII TREE EXPLORER' in bytes(console.output), 5)
        return console

    def oracle(label, width, height):
        target = out / f'oracle-{label}.txt'
        command = [sys.executable, '-m', 'ascii_tree', 'render', '--seed', str(state['seed']), '--mode', state['mode'],
                   '--width', str(width), '--height', str(height), '--yaw', str(state['yaw']), '--pitch', str(state['pitch']),
                   spec['hyper_flag'], str(state['hyper']), '--zoom', str(state['zoom']), '--time', str(state['time']), '--output', str(target)]
        proc = subprocess.run(command, cwd=root, capture_output=True, timeout=15)
        (out / f'oracle-{label}-stdout.bin').write_bytes(proc.stdout)
        (out / f'oracle-{label}-stderr.bin').write_bytes(proc.stderr)
        entry = dict(label=label, command=command, returncode=proc.returncode, output=str(target))
        report['oracles'].append(entry)
        if proc.returncode or not target.is_file():
            raise RuntimeError(f'Headless oracle {label} failed: {proc.returncode}')
        entry['sha256'] = digest(target)
        return target.read_bytes()

    def export(console, label, size, compare=True, expected=None, top=True):
        nonlocal export_no
        width, height = dimensions(size)
        existing = set(export_dir.glob('*.txt'))
        console.send(b'e')
        console.wait_for(lambda: bool(set(export_dir.glob('*.txt')) - existing), 5)
        created = sorted(set(export_dir.glob('*.txt')) - existing)
        if len(created) != 1:
            raise RuntimeError(f'Expected exactly one export for {label}; got {len(created)}')
        target = created[0]
        # Exclusive export creation precedes write completion. Wait for the full
        # expected rectangle, within the unchanged condition timeout.
        console.wait_for(lambda: bounded_ascii(target.read_bytes(), width, height)[0], 5)
        raw = target.read_bytes()
        shape, clean = bounded_ascii(raw, width, height)
        export_no += 1
        evidence = dict(label=label, file=str(target), sha256=digest(target), width=width, height=height, bytes=len(raw))
        if top:
            check(f'{label}: dimensions', shape, **evidence)
            check(f'{label}: printable ASCII and LF only', clean, **evidence)
        if compare:
            reference = oracle(label, width, height) if expected is None else expected
            match = raw == reference
            if top:
                check(f'{label}: exact state/oracle comparison', match, **evidence)
            else:
                report['embedded_3d'].append(dict(**evidence, shape_ok=shape, ascii_ok=clean, oracle_match=match))
            return raw, shape and clean and match
        return raw, shape and clean

    def wait_exit(console, label, codes):
        code = console.wait(5)
        check(f'{label}: accepted actual exit code', code in codes, returncode=code, accepted=codes)
        console.wait_for(lambda: b'\x1b[?25h' in bytes(console.output) and b'\x1b[?1049l' in bytes(console.output), 5)
        transcript = bytes(console.output)
        target = out / f'{label}-transcript.bin'
        target.write_bytes(transcript)
        restored = b'\x1b[?25h' in transcript and b'\x1b[?1049l' in transcript
        check(f'{label}: cursor and alternate-screen restoration', restored, transcript=str(target), sha256=digest(target))

    try:
        if not report['source_baseline_match_before']:
            raise RuntimeError('Frozen source inventory does not match before native execution')
        c = launch('controls')
        check('startup marker from actual native viewer', True)
        size = (100, 40)
        c.send(b'1')
        frame2, _ = export(c, '2d', size)
        c.send(b'2'); state['mode'] = '3d'
        frame3, _ = export(c, '3d', size)
        # The embedded round trip belongs to top-level check 7.
        c.send(b'\x1b[C\x1b[A')
        state['yaw'] += spec['yaw_step']; state['pitch'] += spec['pitch_step']
        rotated3, forward3 = export(c, '3d-right-up', size, top=False)
        c.send(b'\x1b[D\x1b[B')
        state['yaw'] -= spec['yaw_step']; state['pitch'] -= spec['pitch_step']
        restored3, reverse3 = export(c, '3d-left-down', size, top=False)
        report['checks'][6]['embedded_3d_changed'] = rotated3 != frame3
        report['checks'][6]['embedded_3d_restored'] = restored3 == frame3
        if not (forward3 and reverse3 and rotated3 != frame3 and restored3 == frame3):
            report['checks'][6]['status'] = 'fail'
        c.send(b'3'); state['mode'] = '4d'
        frame4, _ = export(c, '4d', size)
        check('three distinct mode frames of seed 42', len({frame2, frame3, frame4}) == 3)
        c.send(b']'); state['hyper'] += spec['hyper_step']
        export(c, 'xw-plus', size)
        c.send(b'['); state['hyper'] -= spec['hyper_step']
        export(c, 'xw-minus', size)
        c.send(b'\x1b[C\x1b[A')
        state['yaw'] += spec['yaw_step']; state['pitch'] += spec['pitch_step']
        rotated4, _ = export(c, '4d-right-up', size)
        c.send(b'+'); state['zoom'] *= 1.12
        export(c, 'zoom-plus', size)
        c.send(b'-'); state['zoom'] *= 1 / 1.12
        export(c, 'zoom-minus', size)
        start = len(c.output)
        c.send(b'h')
        c.wait_for(lambda: spec['help'] in bytes(c.output[start:]), 5)
        check('native help opens in new output', True)
        c.send(b'?')
        prior, _ = export(c, 'help-closed', size)
        c.send(b' '); time.sleep(0.45); c.send(b' ')
        animated, _ = export(c, 'animation-paused', size, compare=False)
        check('animation changed prior frame', animated != prior)
        time.sleep(0.15)
        export(c, 'paused-stable', size, expected=animated)
        c.send(b'r')
        state.update(yaw=25, pitch=spec['pitch'], hyper=0, zoom=1, time=0)
        export(c, 'reset', size)
        c.send(b'g'); state['seed'] += 1
        export(c, 'new-seed', size)
        for label, size in [('resize-narrow', (30, 12)), ('resize-minimal', (1, 1)), ('resize-restored', (100, 40))]:
            c.resize(*size)
            time.sleep(0.3)
            export(c, label, size)
        c.send(b'q')
        wait_exit(c, 'q', [0])
        c.close()
        for label, key, codes in [('escape', b'\x1b', [0]), ('ctrl-c', b'\x03', [0, 130])]:
            fresh = launch(label)
            fresh.send(key)
            wait_exit(fresh, label, codes)
            fresh.close()
        report['complete'] = check_no == 57
    except BaseException as exc:
        report['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        report['smoke_completion'] = 'fail'
    finally:
        for label, console in sessions:
            raw = bytes(console.output)
            path = out / f'{label}-transcript-final.bin'
            path.write_bytes(raw)
            report['sessions'].append({'label': label, 'transcript': str(path), 'sha256': digest(path), 'bytes': len(raw)})
            console.close()
        after = source_inventory(root, frozen_sources)
        report['source_after'] = after
        report['source_unchanged'] = before == after == dict(frozen_sources)
        report['executed_checks'] = check_no
        report['passed_checks'] = sum(c['status'] == 'pass' for c in report['checks'])
        report['failed_checks'] = sum(c['status'] == 'fail' for c in report['checks'])
        report['unexecuted_checks'] = 57 - check_no
        report['all_passed'] = report['complete'] and report['passed_checks'] == 57 and report['source_unchanged'] and report['error'] is None
        report.setdefault('smoke_completion', 'pass' if report['all_passed'] else 'fail')
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps({'report': str(out / 'report.json'), 'complete': report['complete'], 'passed': report['passed_checks'], 'executed': check_no, 'all_passed': report['all_passed']}))
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
