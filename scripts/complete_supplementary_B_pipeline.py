#!/usr/bin/env python3
"""Resume incomplete frozen B cells after the first-pass matrix exits.

This helper never changes the frozen protocol or runner. It waits for the
currently running serial matrix to finish, then uses the same --resume matrix
command to fill missing cells in Frozen M50 and the strong-rule arm. Once both
methods have 40 protocol-valid cells, it analyzes B, renders the post-freeze
report, and creates a verified archive through the post-freeze archive gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'results/supplementary_protocol_B_v1.json'
EXPECTED_PROTOCOL_SHA256 = 'f4733a592d392320e67394faf21b251a56c701573f5a85745f3b13d41f48e964'
SNAPSHOT_SCRIPT = ROOT / 'scripts/snapshot_supplementary_B_progress.py'
MATRIX_SCRIPT = ROOT / 'scripts/run_phase3_gazebo_matrix.py'
ORCHESTRATION_LOG = ROOT / 'results/supplementary_transfer_m50/resume_orchestration.jsonl'
METHOD_ORDER = ('frozen_m50', 'strong_rule')
FAMILIES = ('localization', 'costmap', 'planner', 'control')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def log_event(event: str, **data: Any) -> None:
    row = {
        'time_local': datetime.now().astimezone().isoformat(timespec='seconds'),
        'event': event,
        **data,
    }
    ORCHESTRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ORCHESTRATION_LOG.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()
    print(json.dumps(row, ensure_ascii=False), flush=True)


def proc_cmdline(pid: int) -> tuple[str, str] | None:
    proc = Path('/proc') / str(pid)
    try:
        fields = (proc / 'stat').read_text().split()
        if len(fields) > 2 and fields[2] == 'Z':
            return None
        raw = (proc / 'cmdline').read_bytes()
    except (OSError, IndexError):
        return None
    if not raw:
        return None
    return raw.replace(b'\0', b' ').decode(errors='replace').strip(), fields[2]


def active_matrix_processes() -> list[tuple[int, str]]:
    active: list[tuple[int, str]] = []
    self_pid = os.getpid()
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == self_pid:
            continue
        row = proc_cmdline(pid)
        if row is None:
            continue
        cmdline, _state = row
        if 'scripts/run_phase3_gazebo_matrix.py' in cmdline:
            active.append((pid, cmdline))
    return active


def wait_for_first_pass(parent_pid: int, poll_sec: float) -> None:
    log_event('waiting_for_first_pass', parent_pid=parent_pid)
    while True:
        parent = proc_cmdline(parent_pid)
        if parent is not None:
            cmdline, _state = parent
            if ('scripts/run_phase3_gazebo_matrix.py' in cmdline and
                    'supplementary_transfer_strong_rule' in cmdline):
                time.sleep(poll_sec)
                continue
        active = active_matrix_processes()
        if active:
            log_event('waiting_for_matrix_processes', processes=[p for p, _ in active])
            time.sleep(poll_sec)
            continue
        break
    log_event('first_pass_matrix_exited')


def load_protocol() -> dict[str, Any]:
    if sha256(PROTOCOL) != EXPECTED_PROTOCOL_SHA256:
        raise RuntimeError('Frozen B protocol SHA-256 mismatch; refusing to resume.')
    protocol = json.loads(PROTOCOL.read_text())
    expected_methods = set(METHOD_ORDER) | {'static_m0'}
    if set(protocol.get('methods', {})) != expected_methods:
        raise RuntimeError('Frozen B protocol method set differs from the expected three arms.')
    if len(protocol.get('seeds', [])) != 10 or len(set(protocol['seeds'])) != 10:
        raise RuntimeError('Frozen B protocol must contain exactly 10 unique seeds.')
    if len(FAMILIES) != 4:
        raise RuntimeError('Internal fault-family set is malformed.')
    for method_id in METHOD_ORDER:
        method = protocol['methods'][method_id]
        snapshot_path = method.get('experience_snapshot_path')
        snapshot_hash = method.get('experience_snapshot_sha256')
        if snapshot_path:
            path = Path(snapshot_path)
            if not path.is_file() or sha256(path) != snapshot_hash:
                raise RuntimeError(f'{method_id} frozen experience snapshot hash mismatch.')
    return protocol


def current_audit(method_id: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(SNAPSHOT_SCRIPT), '--method', method_id],
        cwd=ROOT, text=True, capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Progress audit failed for {method_id}: {result.stderr[-2000:]}')
    try:
        audit = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Progress audit emitted invalid JSON for {method_id}.') from exc
    checks = audit.get('integrity_checks', {})
    if (checks.get('protocol_source_hash_mismatches') or
            checks.get('prior_selected_hash_mismatches') or
            checks.get('selected_file_hash_mismatches') or
            audit.get('duplicate_valid_seed_family_keys') or
            audit.get('malformed_files')):
        raise RuntimeError(f'Integrity audit failed for {method_id}: {audit}')
    return audit


def matrix_command(protocol: dict[str, Any], method_id: str) -> list[str]:
    expected = protocol['expected_run']
    method = protocol['methods'][method_id]
    goal = expected['goal']
    pose = expected['initial_pose']
    command = [
        sys.executable, str(MATRIX_SCRIPT),
        '--timeout-sec', '1200',
        '--goal-timeout-sec', str(expected['goal_timeout_sec']),
        '--goal-x', str(goal['x']), '--goal-y', str(goal['y']), '--goal-yaw', str(goal['yaw']),
        '--initial-pose-x', str(pose['x']), '--initial-pose-y', str(pose['y']),
        '--initial-pose-yaw', str(pose['yaw']),
        '--actual-map-id', expected['actual_map_id'],
        '--retries', '2',
        '--experience-prior-mode', expected['experience_prior_mode'],
        '--fault-repetitions', str(expected['fault_repetitions']),
        '--experience-environment-bin', expected['experience_environment_bin'],
        '--use-belief-action-scope',
        '--fault-scale', str(expected['fault_scale']),
        '--no-online-experience-update', '--resume',
    ]
    for seed in protocol['seeds']:
        command.extend(['--seed', str(seed)])
    for family in FAMILIES:
        command.extend(['--fault-family', family])
    command.extend([
        '--baseline', method['baseline'],
        '--experience-checkpoint', method['experience_checkpoint'],
        '--result-dir', method['result_dir'],
    ])
    if method_id == 'frozen_m50':
        template = method['experience_snapshot_path'].replace(
            method['experience_checkpoint'], '{checkpoint}',
        )
        command.extend(['--experience-snapshot-template', template])
    return command


def matrix_pass(protocol: dict[str, Any], method_id: str, pass_number: int) -> int:
    method = protocol['methods'][method_id]
    result_dir = ROOT / method['result_dir']
    result_dir.mkdir(parents=True, exist_ok=True)
    log_path = result_dir / f'matrix_resume_pass_{pass_number:02d}.log'
    command = matrix_command(protocol, method_id)
    shell_command = 'source scripts/source_eacr.sh && exec ' + shlex.join(command)
    log_event('resume_pass_started', method=method_id, pass_number=pass_number,
              command=command, log=str(log_path.relative_to(ROOT)))
    with log_path.open('w', encoding='utf-8') as stream:
        result = subprocess.run(
            ['bash', '-lc', shell_command], cwd=ROOT,
            stdout=stream, stderr=subprocess.STDOUT, text=True,
        )
    dispatch = result_dir / 'phase3_gazebo_dispatch.json'
    if dispatch.is_file():
        archived_dispatch = result_dir / f'phase3_gazebo_dispatch_resume_pass_{pass_number:02d}.json'
        shutil.copy2(dispatch, archived_dispatch)
    log_event('resume_pass_finished', method=method_id, pass_number=pass_number,
              returncode=result.returncode,
              dispatch=(str(archived_dispatch.relative_to(ROOT)) if dispatch.is_file() else None))
    return result.returncode


def preserve_first_pass_dispatch(protocol: dict[str, Any], method_id: str) -> None:
    result_dir = ROOT / protocol['methods'][method_id]['result_dir']
    source = result_dir / 'phase3_gazebo_dispatch.json'
    destination = result_dir / 'phase3_gazebo_dispatch_first_pass.json'
    if destination.is_file():
        return
    if source.is_file():
        shutil.copy2(source, destination)
        log_event('first_pass_dispatch_preserved', method=method_id,
                  path=str(destination.relative_to(ROOT)))


def finalize(protocol: dict[str, Any]) -> None:
    commands = [
        ('analyze_B', [sys.executable, 'scripts/analyze_supplementary_B.py'],
         ROOT / 'results/supplementary_B_analysis.log'),
        ('render_report', [sys.executable, 'scripts/render_supplementary_report_postfreeze.py'],
         ROOT / 'results/supplementary_B_report_rendering.log'),
    ]
    for label, command, log_path in commands:
        log_event('finalizer_started', step=label)
        with log_path.open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                    stderr=subprocess.STDOUT, text=True)
        log_event('finalizer_finished', step=label, returncode=result.returncode,
                  log=str(log_path.relative_to(ROOT)))
        if result.returncode != 0:
            raise RuntimeError(f'{label} failed; inspect {log_path.relative_to(ROOT)}')

    dry_run = subprocess.run(
        [sys.executable, 'scripts/archive_supplementary_experiment_postfreeze.py', '--dry-run'],
        cwd=ROOT, text=True, capture_output=True,
    )
    (ROOT / 'results/supplementary_B_archive_dry_run.log').write_text(
        dry_run.stdout + dry_run.stderr, encoding='utf-8',
    )
    log_event('archive_dry_run', returncode=dry_run.returncode,
              output=(dry_run.stdout + dry_run.stderr).strip())
    if dry_run.returncode != 0 or 'completion_gate_passed=True' not in dry_run.stdout:
        raise RuntimeError('Post-freeze archive dry-run did not pass; archive was not created.')
    archive = subprocess.run(
        [sys.executable, 'scripts/archive_supplementary_experiment_postfreeze.py'],
        cwd=ROOT, text=True, capture_output=True,
    )
    (ROOT / 'results/supplementary_B_archive_creation.log').write_text(
        archive.stdout + archive.stderr, encoding='utf-8',
    )
    log_event('archive_created', returncode=archive.returncode,
              output=(archive.stdout + archive.stderr).strip())
    if archive.returncode != 0:
        raise RuntimeError('Post-freeze archive creation/verification failed.')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait-pid', type=int, required=True,
                        help='PID of the outer serial matrix shell to wait for.')
    parser.add_argument('--poll-sec', type=float, default=30.0)
    parser.add_argument('--max-passes', type=int, default=6)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    protocol = load_protocol()

    if args.dry_run:
        for method_id in METHOD_ORDER:
            result_dir = ROOT / protocol['methods'][method_id]['result_dir']
            snapshots = sorted(result_dir.glob('progress_audit_*.json'))
            if snapshots:
                audit = json.loads(snapshots[-1].read_text())
                count = audit.get('valid_cell_count')
            else:
                count = 0
            print(json.dumps({
                'method': method_id,
                'valid_cells_in_latest_audit': count,
                'target_cells': len(protocol['seeds']) * len(FAMILIES),
                'planned_command': matrix_command(protocol, method_id),
            }, ensure_ascii=False))
        return 0

    wait_for_first_pass(args.wait_pid, args.poll_sec)
    for method_id in METHOD_ORDER:
        preserve_first_pass_dispatch(protocol, method_id)
    for method_id in METHOD_ORDER:
        finished = False
        for pass_number in range(1, args.max_passes + 1):
            audit = current_audit(method_id)
            count = int(audit['valid_cell_count'])
            log_event('method_audit', method=method_id, pass_number=pass_number - 1,
                      valid_cells=count, target=audit['expected_cell_count'],
                      invalid_attempts=audit['invalid_attempt_count'])
            if count == int(audit['expected_cell_count']):
                finished = True
                break
            if count > int(audit['expected_cell_count']):
                raise RuntimeError(f'{method_id} has more selected cells than expected.')
            matrix_pass(protocol, method_id, pass_number)
        if not finished:
            audit = current_audit(method_id)
            if int(audit['valid_cell_count']) != int(audit['expected_cell_count']):
                log_event('method_incomplete_after_max_passes', method=method_id,
                          valid_cells=audit['valid_cell_count'],
                          target=audit['expected_cell_count'],
                          max_passes=args.max_passes)
                return 2
    finalize(protocol)
    log_event('pipeline_complete')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        log_event('pipeline_error', error=repr(exc))
        raise
