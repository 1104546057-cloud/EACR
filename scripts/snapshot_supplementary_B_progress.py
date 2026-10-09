#!/usr/bin/env python3
"""Write a read-only integrity snapshot for an in-progress supplementary B method.

This helper does not alter experiment records or the frozen B protocol. It uses
the same validity predicate as the final B analyzer and is intended for interim
handoffs while the matrix dispatcher is running.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from analyze_supplementary_B import FAMILIES, valid_record

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'results/supplementary_protocol_B_v1.json'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--method', choices=('static_m0', 'frozen_m50', 'strong_rule'),
                        default='static_m0')
    args = parser.parse_args()

    protocol = json.loads(PROTOCOL.read_text())
    method = protocol['methods'][args.method]
    result_dir = ROOT / method['result_dir']
    expected = protocol['expected_run']
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    malformed: list[dict[str, str]] = []
    duplicate_keys: list[dict[str, Any]] = []
    family_summary: dict[str, dict[str, Any]] = defaultdict(lambda: {
        'episodes': 0,
        'behavior_failed': 0,
        'repair_action_success': 0,
        'strict_success': 0,
        'pre_action_nav_success': 0,
        'actions': Counter(),
    })

    for seed in protocol['seeds']:
        for family in FAMILIES:
            accepted: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]] = []
            paths = sorted(result_dir.glob(
                f"phase3_gazebo_{method['baseline']}_{seed}_*.json"))
            for path in paths:
                try:
                    record = json.loads(path.read_text())
                    rows = record.get('episodes', [])
                except (OSError, ValueError) as exc:
                    relative = str(path.relative_to(ROOT))
                    if not any(item['path'] == relative for item in malformed):
                        malformed.append({'path': relative, 'error': str(exc)})
                    continue
                candidate_family = rows[0].get('fault_family') if rows else None
                if candidate_family != family:
                    continue
                checked = valid_record(
                    path, method=method, method_id=args.method,
                    seed=seed, family=family, expected=expected,
                )
                if checked is None:
                    excluded.append({
                        'path': str(path.relative_to(ROOT)),
                        'sha256': sha256(path),
                        'seed': seed,
                        'fault_family': family,
                        'reason': 'protocol_invalid_or_metadata_mismatch',
                        'protocol_compliant': record.get('protocol_compliant'),
                        'protocol_gaps': record.get('protocol_gaps', []),
                        'invalid_episodes': [
                            {
                                'episode_id': row.get('episode_id'),
                                'fault_family': row.get('fault_family'),
                                'episode_evidence_valid': row.get('episode_evidence_valid'),
                                'details': row.get('details'),
                            }
                            for row in rows
                            if row.get('episode_evidence_valid') is not True
                        ],
                    })
                else:
                    accepted.append((path, record, rows))

            if not accepted:
                continue
            if len(accepted) > 1:
                duplicate_keys.append({
                    'seed': seed,
                    'fault_family': family,
                    'paths': [str(row[0].relative_to(ROOT)) for row in accepted],
                })
            chosen_path, _record, rows = accepted[0]
            actions = Counter(str(row.get('selected_action')) for row in rows)
            cell = {
                'path': str(chosen_path.relative_to(ROOT)),
                'sha256': sha256(chosen_path),
                'seed': seed,
                'fault_family': family,
                'episodes': len(rows),
                'behavior_failed': sum(
                    row.get('fault_behavior_observed') is True for row in rows),
                'repair_action_success': sum(
                    bool(row.get('recovery_success')) for row in rows),
                'strict_success': sum(bool(row.get('episode_success')) for row in rows),
                'pre_action_nav_success': sum(
                    row.get('fault_navigation_status') == 4 for row in rows),
                'actions': dict(actions),
            }
            selected.append(cell)
            summary = family_summary[family]
            summary['episodes'] += len(rows)
            summary['behavior_failed'] += cell['behavior_failed']
            summary['repair_action_success'] += cell['repair_action_success']
            summary['strict_success'] += cell['strict_success']
            summary['pre_action_nav_success'] += cell['pre_action_nav_success']
            summary['actions'].update(str(row.get('selected_action')) for row in rows)
            for extra_path, _extra_record, _extra_rows in accepted[1:]:
                excluded.append({
                    'path': str(extra_path.relative_to(ROOT)),
                    'sha256': sha256(extra_path),
                    'seed': seed,
                    'fault_family': family,
                    'reason': 'extra_valid_attempt_not_selected',
                })

    manual_log = result_dir / 'invalid_attempts.jsonl'
    manual_entries: list[dict[str, Any]] = []
    if manual_log.is_file():
        for line_no, line in enumerate(manual_log.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                attempt = json.loads(line)
            except ValueError:
                manual_entries.append({'line': line_no, 'invalid_log_json': line})
                continue
            manual_entries.append({'line': line_no, 'attempt': attempt})

    raw_paths = sorted(result_dir.glob(f"phase3_gazebo_{method['baseline']}_*.json"))
    for path in raw_paths:
        try:
            json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            if not any(item['path'] == str(path.relative_to(ROOT)) for item in malformed):
                malformed.append({'path': str(path.relative_to(ROOT)), 'error': str(exc)})

    source_hash_mismatches = []
    for relative, expected_hash in protocol.get('source_sha256', {}).items():
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected_hash:
            source_hash_mismatches.append(relative)

    previous = sorted(result_dir.glob('progress_audit_*.json'))
    prior_hashes: dict[str, str] = {}
    if previous:
        try:
            prior = json.loads(previous[-1].read_text())
            prior_hashes = {row['path']: row['sha256']
                            for row in prior.get('selected_valid_records', [])}
        except (OSError, ValueError, KeyError, TypeError):
            prior_hashes = {}
    selected_hashes = {row['path']: row['sha256'] for row in selected}
    prior_hash_mismatches = [
        path for path, digest in prior_hashes.items()
        if selected_hashes.get(path) != digest
    ]
    disk_hash_mismatches = [
        row['path'] for row in selected
        if sha256(ROOT / row['path']) != row['sha256']
    ]

    now = datetime.now().astimezone()
    version = 1
    for path in previous:
        try:
            snapshot = json.loads(path.read_text())
            old_id = str(snapshot.get('snapshot_id', ''))
            if old_id.rsplit('_v', 1)[-1].isdigit():
                version = max(version, int(old_id.rsplit('_v', 1)[-1]) + 1)
        except (OSError, ValueError):
            continue
    snapshot_id = f'eacr_transfer_{args.method}_progress_audit_v{version}'
    data = {
        'snapshot_id': snapshot_id,
        'captured_local': now.isoformat(timespec='seconds'),
        'supplementary_protocol_id': protocol.get('protocol_id'),
        'supplementary_protocol_sha256': sha256(PROTOCOL),
        'runner_protocol_id': 'eacr_phase3_v1',
        'scope_note': ('Interim integrity snapshot only; not final inference. '
                       'Final analysis requires all paired methods across the 10 frozen seeds.'),
        'method': method['baseline'],
        'checkpoint': method['experience_checkpoint'],
        'actual_map_id': expected.get('actual_map_id'),
        'valid_cell_count': len(selected),
        'expected_cell_count': len(protocol['seeds']) * len(FAMILIES),
        'invalid_attempt_count': len(excluded) - sum(
            item.get('reason') == 'extra_valid_attempt_not_selected' for item in excluded
        ) + len(manual_entries),
        'duplicate_valid_seed_family_keys': duplicate_keys,
        'family_episode_summary': {
            family: {**summary, 'actions': dict(summary['actions'])}
            for family, summary in family_summary.items()
        },
        'selected_valid_records': selected,
        'excluded_attempts': excluded,
        'manual_invalid_attempt_entries': manual_entries,
        'malformed_files': malformed,
        'raw_file_count': len(raw_paths),
        'integrity_checks': {
            'protocol_source_hash_count': len(protocol.get('source_sha256', {})),
            'protocol_source_hash_mismatches': source_hash_mismatches,
            'prior_selected_hash_mismatches': prior_hash_mismatches,
            'selected_file_hash_mismatches': disk_hash_mismatches,
        },
    }
    stamp = now.strftime('%Y%m%dT%H%M%S')
    output = result_dir / f'progress_audit_{stamp}.json'
    while output.exists():
        stamp = datetime.now().astimezone().strftime('%Y%m%dT%H%M%S%f')
        output = result_dir / f'progress_audit_{stamp}.json'
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({
        'snapshot': str(output.relative_to(ROOT)),
        'captured_local': data['captured_local'],
        'valid_cell_count': data['valid_cell_count'],
        'expected_cell_count': data['expected_cell_count'],
        'invalid_attempt_count': data['invalid_attempt_count'],
        'raw_file_count': data['raw_file_count'],
        'malformed_files': malformed,
        'duplicate_keys': duplicate_keys,
        'integrity_checks': data['integrity_checks'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
