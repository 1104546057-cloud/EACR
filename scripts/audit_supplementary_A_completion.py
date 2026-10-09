#!/usr/bin/env python3
"""Verify the completed A matrix against its frozen seed/family protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / 'results/supplementary_protocol_A_v1.json'
RESULT_DIR = ROOT / 'results/supplementary_original_strong_rule'
OUTPUT_PATH = ROOT / 'results/supplementary_A_completion_audit.json'
AMENDMENT_PATH = ROOT / 'results/supplementary_A_execution_amendment_01.json'
SOURCE_SNAPSHOT_PATH = ROOT / 'results/supplementary_A_source_snapshot/manifest.json'
PROVENANCE_CORRECTION_PATH = ROOT / 'results/supplementary_A_source_provenance_correction_01.json'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    protocol = json.loads(PROTOCOL_PATH.read_text())
    expected = {
        (seed, family)
        for seed in protocol['seeds']
        for family in protocol['fault_families']
    }
    cell_paths = sorted(RESULT_DIR.glob('phase3_gazebo_eacr_strong_rule_*_*.json'))
    valid_by_key: dict[tuple[int, str], list[dict]] = {}
    invalid = []
    malformed = []
    errors = []
    family_counts = Counter()
    metadata_fields = {
        'baseline': protocol['baseline'],
        'fault_scale': protocol['fault_scale'],
        'fault_repetitions': protocol['fault_repetitions'],
        'actual_map_id': protocol['scene'],
        'experience_checkpoint': 'M_0',
        'experience_prior_mode': protocol['experience_prior_mode'],
        'use_belief_action_scope': protocol['use_belief_action_scope'],
        'online_experience_update': protocol['online_experience_update'],
        'resume_experience_state': protocol['resume_experience_state'],
        'experience_environment_bin': 'tb3_sandbox_gazebo',
    }

    for path in cell_paths:
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            malformed.append({'path': str(path.relative_to(ROOT)), 'error': str(exc)})
            continue
        episodes = record.get('episodes', [])
        family = episodes[0].get('fault_family') if episodes else None
        seed = record.get('seed')
        if record.get('protocol_compliant') is not True or record.get('infrastructure_failure') is True:
            invalid.append({
                'path': str(path.relative_to(ROOT)),
                'seed': seed,
                'fault_family': family,
                'protocol_compliant': record.get('protocol_compliant'),
                'infrastructure_failure': record.get('infrastructure_failure'),
                'protocol_gaps': record.get('protocol_gaps', []),
            })
            continue

        key = (seed, family)
        valid_by_key.setdefault(key, []).append({'path': path, 'record': record})
        family_counts[family] += 1
        for field, expected_value in metadata_fields.items():
            if record.get(field) != expected_value:
                errors.append({
                    'path': str(path.relative_to(ROOT)), 'field': field,
                    'expected': expected_value, 'observed': record.get(field),
                })
        if seed not in protocol['seeds'] or family not in protocol['fault_families']:
            errors.append({'path': str(path.relative_to(ROOT)), 'error': 'unexpected seed/family key', 'key': key})
        if len(episodes) != protocol['fault_repetitions']:
            errors.append({'path': str(path.relative_to(ROOT)), 'error': 'wrong episode count', 'count': len(episodes)})
        if any(
            episode.get('fault_family') != family
            or episode.get('episode_evidence_valid') is not True
            for episode in episodes
        ):
            errors.append({'path': str(path.relative_to(ROOT)), 'error': 'invalid episode evidence/family'})
        episode_ids = [episode.get('episode_id') for episode in episodes]
        if len(set(episode_ids)) != len(episode_ids):
            errors.append({'path': str(path.relative_to(ROOT)), 'error': 'duplicate episode IDs'})

    actual_unique = {key for key, entries in valid_by_key.items() if len(entries) == 1}
    duplicates = {
        f'{seed}/{family}': [entry['path'].relative_to(ROOT).as_posix() for entry in entries]
        for (seed, family), entries in valid_by_key.items() if len(entries) != 1
    }
    missing = sorted(expected - actual_unique)
    unexpected = sorted(set(valid_by_key) - expected)

    manual_log = RESULT_DIR / 'invalid_attempts.jsonl'
    manual_attempts = []
    if manual_log.exists():
        for line_number, line in enumerate(manual_log.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError as exc:
                errors.append({'path': str(manual_log.relative_to(ROOT)), 'line': line_number, 'error': str(exc)})
                continue
            manual_attempts.append({'line': line_number, 'attempt': value})

    amendment = json.loads(AMENDMENT_PATH.read_text()) if AMENDMENT_PATH.exists() else {}
    snapshot = json.loads(SOURCE_SNAPSHOT_PATH.read_text()) if SOURCE_SNAPSHOT_PATH.exists() else {}
    correction = json.loads(PROVENANCE_CORRECTION_PATH.read_text()) if PROVENANCE_CORRECTION_PATH.exists() else {}
    source_checks = {}
    for registered_path, registered_hash in protocol['source_sha256'].items():
        source_path = Path(registered_path)
        if not source_path.is_absolute():
            source_path = ROOT / source_path
        try:
            current_hash = sha256(source_path)
        except OSError:
            current_hash = None
        snapshot_entry = next((entry for entry in snapshot.get('entries', [])
                               if entry.get('registered_path') == registered_path), {})
        observed_hash = snapshot_entry.get('observed_at_snapshot_sha256', current_hash)
        amendment_execution_copy_matches = (
            registered_path == 'scripts/run_phase3_gazebo_matrix.py'
            and amendment.get('base_protocol_sha256') == sha256(PROTOCOL_PATH)
            and amendment.get('matrix_script', {}).get('frozen_protocol_sha256') == registered_hash
            and amendment.get('matrix_script', {}).get('current_sha256') == observed_hash
            and amendment.get('matrix_script', {}).get('method_policy_parameters_or_action_logic_changed') is False
        )
        correction_documents_mismatch = (
            registered_path == 'scripts/run_phase3_gazebo_matrix.py'
            and correction.get('correction_id') == 'eacr_supplementary_A_source_provenance_correction_01'
            and correction.get('exact_frozen_matrix_source_recovered') is False
            and correction.get('available_A_execution_snapshot_sha256') == observed_hash
            and snapshot_entry.get('observed_at_snapshot_sha256') == observed_hash
        )
        source_checks[registered_path] = {
            'registered_sha256': registered_hash,
            'observed_sha256': observed_hash,
            'current_workspace_sha256': current_hash,
            'observed_hash_source': 'A source snapshot' if snapshot_entry else 'current workspace fallback',
            'matches_registered': observed_hash == registered_hash,
            'amendment_execution_copy_matches': amendment_execution_copy_matches,
            'documented_unresolved_execution_source_mismatch': correction_documents_mismatch,
            'accepted_as_exact_source': observed_hash == registered_hash,
        }
    source_hash_errors = [path for path, check in source_checks.items() if not check['accepted_as_exact_source']]
    unresolved_source_hash_errors = [
        path for path, check in source_checks.items()
        if not check['accepted_as_exact_source']
        and not check['documented_unresolved_execution_source_mismatch']
    ]
    provenance_warnings = [
        path for path, check in source_checks.items()
        if check['documented_unresolved_execution_source_mismatch']
    ]

    data_complete = (
        len(actual_unique) == len(expected)
        and actual_unique == expected
        and not duplicates
        and not malformed
        and not errors
    )
    provenance_reconciled = (
        len(unresolved_source_hash_errors) == 0
        and all(check['accepted_as_exact_source'] or check['documented_unresolved_execution_source_mismatch']
                for check in source_checks.values())
    )
    complete = data_complete and provenance_reconciled
    result = {
        'audit_id': 'eacr_supplementary_A_completion_v1',
        'protocol_id': protocol['protocol_id'],
        'protocol_sha256': sha256(PROTOCOL_PATH),
        'matrix_script_sha256': sha256(ROOT / 'scripts/run_phase3_gazebo_matrix.py'),
        'analysis_script_sha256': sha256(ROOT / 'scripts/analyze_supplementary_A.py'),
        'registered_source_hash_checks': source_checks,
        'source_hash_errors': source_hash_errors,
        'unresolved_source_hash_errors': unresolved_source_hash_errors,
        'source_provenance_warnings': provenance_warnings,
        'all_registered_sources_match_exactly': not source_hash_errors,
        'data_complete_independent_of_source_provenance': data_complete,
        'source_provenance_reconciled': provenance_reconciled,
        'execution_amendment_id': amendment.get('amendment_id'),
        'expected_valid_cells': len(expected),
        'observed_valid_cells': sum(len(entries) for entries in valid_by_key.values()),
        'distinct_valid_cells': len(actual_unique),
        'expected_episodes': len(expected) * protocol['fault_repetitions'],
        'observed_valid_episodes': sum(len(item['record'].get('episodes', [])) for entries in valid_by_key.values() for item in entries),
        'valid_cells_by_family': dict(sorted(family_counts.items())),
        'protocol_invalid_cell_attempts': invalid,
        'protocol_invalid_cell_attempt_count': len(invalid),
        'manual_incomplete_attempts': manual_attempts,
        'manual_incomplete_attempt_count': len(manual_attempts),
        'malformed_cell_json': malformed,
        'missing_seed_family_keys': missing,
        'unexpected_seed_family_keys': unexpected,
        'duplicate_valid_keys': duplicates,
        'metadata_or_episode_errors': errors,
        'complete': complete,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(args.output)
    print(f"complete={complete} valid={result['observed_valid_cells']}/{result['expected_valid_cells']} "
          f"invalid_attempts={len(invalid)} malformed={len(malformed)}")
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
