#!/usr/bin/env python3
"""Aggregate the preregistered EACR evolving-vs-static protocol.

This intentionally does not touch the frozen phase-3 aggregate.  It keeps
intervention success (the recovery service actually restored the faulted
component) separate from sustained navigation success (the post-recovery
navigation action succeeded), then computes paired deltas on shared cells.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path


def _files(inputs: list[Path]) -> list[Path]:
    found: set[Path] = set()
    for root in inputs:
        if root.is_file() and root.name.endswith('.json'):
            found.add(root)
        elif root.is_dir():
            found.update(root.rglob('phase3_gazebo_*.json'))
    return sorted(found)


def _method(item: dict) -> str | None:
    if item.get('baseline') == 'eacr_static':
        return 'eacr_static_m0'
    if item.get('baseline') != 'eacr_evolving':
        return None
    checkpoint = str(item.get('experience_checkpoint', 'M_0'))
    if checkpoint in {'M_20', 'M_50'}:
        # Keep method identifiers stable with the preregistered comparison
        # names (eacr_evolving_m20 / eacr_evolving_m50).
        return f'eacr_evolving_{checkpoint.lower().replace("_", "")}'
    return 'eacr_evolving_online_m0' if item.get('online_experience_update', True) else 'eacr_evolving_m0_frozen'


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _cell_metrics(item: dict) -> dict[str, float | None]:
    rows = item.get('episodes', [])
    action = [bool(row.get('recovery_success', False)) for row in rows]
    sustained = [bool(row.get('episode_success', False)) for row in rows]
    mttr = [float(row['recovery_navigation_duration_sec']) for row in rows
            if row.get('episode_success') and row.get('recovery_navigation_duration_sec') is not None]
    cost = [float(row['intervention_cost']) for row in rows if row.get('intervention_cost') is not None]
    probes = [bool(str(row.get('selected_action', '')).startswith('inspect')) and not bool(row.get('episode_success', False))
              for row in rows]
    return {
        'intervention_recovery_rate': _mean([float(x) for x in action]),
        'sustained_recovery_rate': _mean([float(x) for x in sustained]),
        'mttr_sec': _mean(mttr),
        'intervention_cost_mean': _mean(cost),
        'useless_probe_rate': _mean([float(x) for x in probes]),
        'episode_count': float(len(rows)),
    }


def _bootstrap_ci(values: list[float], seed: int = 20261002, draws: int = 20000) -> list[float | None]:
    if not values:
        return [None, None]
    if len(values) == 1:
        return [values[0], values[0]]
    rng = random.Random(seed)
    estimates = []
    for _ in range(draws):
        sample = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(sum(sample) / len(sample))
    estimates.sort()
    return [estimates[int(0.025 * (len(estimates) - 1))], estimates[int(0.975 * (len(estimates) - 1))]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', action='append', type=Path, required=True,
                        help='Result JSON file or directory; may be repeated.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    records = []
    excluded = defaultdict(int)
    for path in _files(args.input):
        try:
            item = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            excluded['unreadable'] += 1
            continue
        method = _method(item)
        rows = item.get('episodes', [])
        if method is None:
            excluded['unrecognised_baseline'] += 1
            continue
        if item.get('protocol_compliant') is not True or item.get('infrastructure_failure'):
            excluded['noncompliant_or_infrastructure'] += 1
            continue
        if not rows or not all(row.get('episode_evidence_valid') for row in rows):
            excluded['invalid_episode_evidence'] += 1
            continue
        family = rows[0].get('fault_family')
        seed = item.get('seed')
        if seed is None or family is None or len({row.get('fault_family') for row in rows}) != 1:
            excluded['missing_paired_key'] += 1
            continue
        records.append({'path': str(path), 'method': method, 'seed': int(seed),
                        'fault_family': str(family), 'metrics': _cell_metrics(item),
                        'fault_scale': item.get('fault_scale'),
                        'prior_mode': item.get('experience_prior_mode'),
                        'action_scope': item.get('use_belief_action_scope')})

    # Keep the newest run for a duplicated method/seed/family cell.
    latest: dict[tuple[str, int, str], dict] = {}
    for record in records:
        key = (record['method'], record['seed'], record['fault_family'])
        old = latest.get(key)
        if old is None or Path(record['path']).stat().st_mtime_ns >= Path(old['path']).stat().st_mtime_ns:
            latest[key] = record
    records = list(latest.values())

    by_method: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_method[record['method']].append(record)
    aggregate = {}
    metric_names = ('intervention_recovery_rate', 'sustained_recovery_rate',
                    'mttr_sec', 'intervention_cost_mean', 'useless_probe_rate')
    for method, cells in sorted(by_method.items()):
        aggregate[method] = {
            'cell_count': len(cells),
            'episode_count': int(sum(int(c['metrics']['episode_count'] or 0) for c in cells)),
            'metrics': {
                name: _mean([float(c['metrics'][name]) for c in cells if c['metrics'][name] is not None])
                for name in metric_names
            },
            'cells': sorted(cells, key=lambda c: (c['seed'], c['fault_family'])),
        }

    paired = []
    static = {(c['seed'], c['fault_family']): c for c in by_method.get('eacr_static_m0', [])}
    for evolving_method in ('eacr_evolving_online_m0', 'eacr_evolving_m20', 'eacr_evolving_m50'):
        evolving = {(c['seed'], c['fault_family']): c for c in by_method.get(evolving_method, [])}
        keys = sorted(set(static) & set(evolving))
        for metric in metric_names:
            deltas = []
            for key in keys:
                a = static[key]['metrics'][metric]
                b = evolving[key]['metrics'][metric]
                if a is not None and b is not None:
                    deltas.append(float(b) - float(a))
            paired.append({
                'comparison': f'{evolving_method} minus eacr_static_m0',
                'metric': metric,
                'paired_cell_count': len(deltas),
                'mean_delta': _mean(deltas),
                'bootstrap_95ci': _bootstrap_ci(deltas),
                'direction_better_for_evolving': metric in {'intervention_recovery_rate', 'sustained_recovery_rate'}
                    and (_mean(deltas) is not None and _mean(deltas) > 0)
                    or metric in {'mttr_sec', 'intervention_cost_mean', 'useless_probe_rate'}
                    and (_mean(deltas) is not None and _mean(deltas) < 0),
            })

    result = {
        'protocol_id': 'eacr_evolving_advantage_v1',
        'source_files': [r['path'] for r in sorted(records, key=lambda r: r['path'])],
        'valid_cell_count': len(records),
        'excluded_counts': dict(excluded),
        'methods': aggregate,
        'paired_comparisons': paired,
        'acceptance': {
            'paired_static_cells_available': bool(static),
            'has_repeated_episodes': all(c['metrics']['episode_count'] and c['metrics']['episode_count'] > 1 for c in records),
            'all_records_scope_consistent': len({r['action_scope'] for r in records}) <= 1,
            'all_records_prior_consistent': len({r['prior_mode'] for r in records}) <= 1,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('valid_cell_count', 'excluded_counts', 'acceptance')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
