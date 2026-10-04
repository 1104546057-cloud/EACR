#!/usr/bin/env python3
"""Dispatch the frozen Gazebo matrix without merging invalid episodes."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]


def record_matches_resume(item: dict, args) -> bool:
    """Return whether an existing JSON already satisfies this matrix cell.

    Training JSON written before resume_experience_state was recorded stores
    null. The checkpoint builder treats a missing or null value as false, and
    --resume must do the same. A strict comparison with false would rerun
    protocol-valid planner cells.
    """
    episodes = item.get('episodes', [])
    if not episodes:
        return False
    expected_snapshot = (
        args.experience_snapshot_template.format(
            checkpoint=args.experience_checkpoint, seed=item.get('seed'),
        ) if args.experience_snapshot_template else None
    )
    stored_resume = bool(item.get('resume_experience_state'))
    return (
        item.get('protocol_compliant') is True
        and len(episodes) == max(1, args.fault_repetitions)
        and all(row.get('episode_evidence_valid') for row in episodes)
        and item.get('experience_checkpoint') == args.experience_checkpoint
        and item.get('experience_prior_mode') == args.experience_prior_mode
        and item.get('use_belief_action_scope') == args.use_belief_action_scope
        and float(item.get('fault_scale', float('nan'))) == args.fault_scale
        and int(item.get('fault_repetitions', -1)) == max(1, args.fault_repetitions)
        and item.get('online_experience_update') == (not args.no_online_experience_update)
        and stored_resume == bool(args.resume_experience_state)
        and item.get('experience_snapshot_path') == expected_snapshot
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='append')
    parser.add_argument('--seed', action='append', type=int)
    parser.add_argument('--fault-family', action='append')
    parser.add_argument('--timeout-sec', type=int, default=180)
    parser.add_argument('--goal-timeout-sec', type=float, default=60.0)
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--result-dir', type=Path, default=WORKSPACE / 'results')
    parser.add_argument('--experience-checkpoint', default='M_0', choices=['M_0', 'M_20', 'M_50'])
    parser.add_argument('--experience-prior-mode', default='domain', choices=['domain', 'weak_shared_m0'])
    parser.add_argument('--fault-repetitions', type=int, default=1)
    parser.add_argument('--experience-environment-bin', default='tb3_sandbox_gazebo')
    parser.add_argument('--use-belief-action-scope', action='store_true')
    parser.add_argument('--fault-scale', type=float, default=1.0)
    parser.add_argument('--experience-snapshot-template', default='',
                        help='Optional snapshot path template with {checkpoint} and {seed}.')
    parser.add_argument('--no-online-experience-update', action='store_true')
    parser.add_argument('--resume-experience-state', action='store_true',
                        help='Explicitly warm-start a run from its saved state; disabled for paired experiments.')
    parser.add_argument('--resume', action='store_true', help='skip cells that already have a valid record')
    args = parser.parse_args()
    if args.experience_checkpoint in {'M_20', 'M_50'} and not args.experience_snapshot_template:
        parser.error(f'{args.experience_checkpoint} requires --experience-snapshot-template')
    baselines = args.baseline or [
        'rule_based_recovery', 'bayesian_fixed_recovery',
        'ig_without_evolving_experience', 'eacr_static', 'eacr_evolving',
    ]
    seeds = args.seed or [20260926, 20260927, 20260928, 20260929, 20260930]
    families = args.fault_family or ['localization', 'costmap', 'planner', 'control']
    runs = []
    existing_valid = set()
    if args.resume:
        for path in args.result_dir.glob('phase3_gazebo_*.json'):
            try:
                item = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if record_matches_resume(item, args):
                episodes = item.get('episodes', [])
                existing_valid.add((item.get('baseline'), item.get('seed'), episodes[0].get('fault_family')))
    for baseline in baselines:
        for seed in seeds:
            for family in families:
                if (baseline, seed, family) in existing_valid:
                    print(f'skip existing valid {baseline} seed={seed} family={family}', flush=True)
                    runs.append({'baseline': baseline, 'seed': seed, 'fault_family': family,
                                 'returncode': 0, 'skipped_existing_valid': True,
                                 'attempts': 0, 'protocol_ok': True})
                    continue
                print(f'start {baseline} seed={seed} family={family}', flush=True)
                ros_command = ' '.join(shlex.quote(item) for item in [
                    'ros2', 'run', 'eacr_sim', 'phase3_gazebo_runner', '--ros-args',
                    '-p', f'baseline:={baseline}', '-p', f'random_seed:={seed}',
                    '-p', f'fault_family_filter:={family}',
                    '-p', f'max_episodes:={max(1, args.fault_repetitions)}',
                    '-p', f'goal_timeout_sec:={args.goal_timeout_sec}',
                    '-p', f'experience_checkpoint:={args.experience_checkpoint}',
                    '-p', f'experience_prior_mode:={args.experience_prior_mode}',
                    '-p', f'fault_repetitions:={max(1, args.fault_repetitions)}',
                    '-p', f'experience_environment_bin:={args.experience_environment_bin}',
                    '-p', f'use_belief_action_scope:={str(args.use_belief_action_scope).lower()}',
                    '-p', f'fault_scale:={args.fault_scale}',
                    '-p', f'online_experience_update:={str(not args.no_online_experience_update).lower()}',
                    '-p', f'resume_experience_state:={str(args.resume_experience_state).lower()}',
                    '-p', f'result_dir:={args.result_dir}',
                ])
                if args.experience_snapshot_template:
                    snapshot = args.experience_snapshot_template.format(
                        checkpoint=args.experience_checkpoint, seed=seed,
                    )
                    ros_command += ' ' + ' '.join(shlex.quote(item) for item in [
                        '-p', f'experience_snapshot_path:={snapshot}',
                    ])
                if baseline in {'eacr_evolving', 'full_eacr'}:
                    state_path = args.result_dir / f'phase3_experience_{baseline}_{seed}.json'
                    ros_command += ' ' + ' '.join(shlex.quote(item) for item in ['-p', f'experience_state_path:={state_path}'])
                command = ['bash', '-lc', f'source scripts/source_eacr.sh && exec {ros_command}']
                returncode, stdout, stderr = 124, '', ''
                attempts = 0
                protocol_ok = False
                while attempts <= max(0, args.retries):
                    attempts += 1
                    before = set(args.result_dir.glob(f'phase3_gazebo_{baseline}_{seed}_*.json'))
                    process = None
                    try:
                        # Put each ROS invocation in its own process group.  A
                        # timeout must reap ros2, the executable wrapper, and
                        # any child node together; otherwise stale runners can
                        # survive into the next paired cell.
                        process = subprocess.Popen(
                            command, cwd=WORKSPACE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True,
                        )
                        try:
                            stdout, stderr = process.communicate(timeout=args.timeout_sec)
                            returncode = process.returncode
                        except subprocess.TimeoutExpired as exc:
                            returncode = 124
                            # TimeoutExpired may expose bytes even with
                            # text=True.  The subsequent communicate() gives
                            # the full captured output, so do not concatenate
                            # the partial exception payload with its tail.
                            try:
                                os.killpg(process.pid, signal.SIGTERM)
                                stdout, stderr = process.communicate(timeout=10)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, signal.SIGKILL)
                                stdout, stderr = process.communicate()
                    except BaseException:
                        # Ctrl-C and unexpected Python errors must not leave a
                        # detached ROS runner operating on the same Gazebo.
                        if process is not None and process.poll() is None:
                            try:
                                os.killpg(process.pid, signal.SIGTERM)
                                process.communicate(timeout=10)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, signal.SIGKILL)
                                process.communicate()
                        raise
                    after = set(args.result_dir.glob(f'phase3_gazebo_{baseline}_{seed}_*.json')) - before
                    for path in after:
                        try:
                            item = json.loads(path.read_text())
                            episodes = item.get('episodes', [])
                            if (
                                record_matches_resume(item, args)
                                and item.get('baseline') == baseline
                                and item.get('seed') == seed
                                and episodes[0].get('fault_family') == family
                                and all(row.get('fault_family') == family for row in episodes)
                            ):
                                protocol_ok = True
                                break
                        except (OSError, json.JSONDecodeError):
                            continue
                    if protocol_ok or returncode != 0 and attempts > args.retries:
                        break
                runs.append({
                    'baseline': baseline,
                    'seed': seed,
                    'fault_family': family,
                    'returncode': returncode,
                    'stdout_tail': stdout[-1000:],
                    'stderr_tail': stderr[-1000:],
                    'attempts': attempts,
                    'protocol_ok': protocol_ok,
                })
    output = args.result_dir / 'phase3_gazebo_dispatch.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        'protocol_id': 'eacr_phase3_v1',
        'baselines': baselines,
        'seeds': seeds,
        'fault_families': families,
        'experience_checkpoint': args.experience_checkpoint,
        'experience_prior_mode': args.experience_prior_mode,
        'fault_repetitions': max(1, args.fault_repetitions),
        'experience_environment_bin': args.experience_environment_bin,
        'use_belief_action_scope': args.use_belief_action_scope,
        'fault_scale': args.fault_scale,
        'online_experience_update': not args.no_online_experience_update,
        'resume_experience_state': args.resume_experience_state,
        'runs': runs,
        'completed_runs': sum(row['returncode'] == 0 for row in runs),
        'total_runs': len(runs),
    }, ensure_ascii=False, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
