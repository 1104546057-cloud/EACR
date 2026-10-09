#!/usr/bin/env python3
"""Validate and summarize the frozen transfer-scene engineering pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRONG_DIR = ROOT / 'results/supplementary_pilot_transfer_v5'
M50_DIR = ROOT / 'results/supplementary_pilot_transfer_v5_m50'
M50_PATH = ROOT / 'results/phase4_experience_evolving_full_M_50.json'
BT_AUDIT_PATH = ROOT / 'results/supplementary_nav2_bt_audit.json'
BT_PATH = Path('/opt/ros/jazzy/share/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml')
NAV2_PARAMS = ROOT / 'src/eacr_sim/config/nav2_transfer_courtyard.yaml'
OUT = ROOT / 'results/supplementary_B_engineering_pilot.json'
SEED = 1876543211
FAMILY_ACTION = {
    'localization': 'relocalize_amcl',
    'control': 'reconfigure_controller',
    'planner': 'reconfigure_planner',
    'costmap': 'clear_costmaps',
}
EXPECTED_PARAMETER = {
    'localization': ('amcl_distance_to_start_m', 0.35),
    'control': ('min_x_velocity_threshold', 1.0),
    'planner': ('planner_allow_unknown', False),
    'costmap': ('footprint_padding', 0.5),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_one(directory: Path, baseline: str) -> tuple[Path, dict]:
    paths = sorted(directory.glob(f'phase3_gazebo_{baseline}_{SEED}_*.json'))
    if len(paths) != 1:
        raise ValueError(f'expected one pilot record in {directory}, got {len(paths)}')
    return paths[0], json.loads(paths[0].read_text())


def evidence_effect(family: str, episode: dict) -> bool:
    evidence = episode.get('online_evidence') or {}
    params = evidence.get('nav2_parameters') or {}
    if family == 'localization':
        value = evidence.get('amcl_distance_to_start_m')
        return isinstance(value, (int, float)) and float(value) > 0.35
    name, threshold = EXPECTED_PARAMETER[family]
    value = params.get(name)
    if family == 'planner':
        return value is False
    return isinstance(value, (int, float)) and float(value) > float(threshold)


def main() -> None:
    strong_path, strong = load_one(STRONG_DIR, 'eacr_strong_rule')
    m50_path, m50 = load_one(M50_DIR, 'eacr_evolving')
    if strong.get('seed') != SEED or m50.get('seed') != SEED:
        raise ValueError('pilot seed metadata mismatch')
    strong_rows = {row.get('fault_family'): row for row in strong.get('episodes', [])}
    if set(strong_rows) != set(FAMILY_ACTION):
        raise ValueError(f'incomplete strong-rule pilot families: {sorted(strong_rows)}')
    if len(m50.get('episodes', [])) != 1 or m50['episodes'][0].get('fault_family') != 'planner':
        raise ValueError('M50 key-hit pilot must contain one planner episode')

    per_family = {}
    for family, expected_action in FAMILY_ACTION.items():
        row = strong_rows[family]
        per_family[family] = {
            'nominal_navigation_status': row.get('nominal_navigation_status'),
            'pre_fault_costmap_clear': row.get('pre_fault_costmap_clear'),
            'fault_navigation_status': row.get('fault_navigation_status'),
            'fault_behavior_observed': row.get('fault_behavior_observed'),
            'fault_effect_observed': row.get('fault_effect_observed'),
            'online_evidence_confirms_injection': evidence_effect(family, row),
            'selected_action': row.get('selected_action'),
            'expected_action': expected_action,
            'recovery_success': row.get('recovery_success'),
            'rollback_success': row.get('rollback_success'),
            'recovery_navigation_status': row.get('recovery_navigation_status'),
            'episode_success': row.get('episode_success'),
            'episode_evidence_valid': row.get('episode_evidence_valid'),
            'inject_detail': row.get('details', {}).get('inject'),
            'recovery_detail': row.get('details', {}).get('recovery'),
        }

    planner = strong_rows['planner']
    m50_episode = m50['episodes'][0]
    planner_key = (
        'planner_failure|tb3_sandbox|goal_nav|navigating|'
        'tb3_sandbox_gazebo|nav2_jazzy|reconfigure_planner'
    )
    matched_entry = m50_episode.get('experience_before_episode', {}).get(planner_key)
    m50_snapshot_sha = sha256(M50_PATH)
    bt_audit = json.loads(BT_AUDIT_PATH.read_text())
    bt_hash_matches = sha256(BT_PATH) == bt_audit.get('sha256')
    params_text = NAV2_PARAMS.read_text()
    params_are_transfer_profile = (
        'plugins: ["static_layer", "inflation_layer"]' in params_text
        and 'plugins: ["voxel_layer", "inflation_layer"]' in params_text
    )
    checks = {
        'normal_navigation': all(row.get('nominal_navigation_status') == 4 for row in strong_rows.values()),
        'episode_reset': all(
            row.get('reset_success') is True
            and row.get('nominal_reset_success') is True
            and all((row.get('pre_fault_costmap_clear') or {}).values())
            for row in strong_rows.values()
        ),
        'fault_injection': all(row.get('inject_success') is True for row in strong_rows.values()),
        'online_evidence': all(evidence_effect(family, strong_rows[family]) for family in FAMILY_ACTION),
        # At least one predeclared planner fault produced an independent Nav2
        # abort and a valid-planner NO_VALID_PATH probe. Other families are
        # separately recorded and may show parameter repair without behavior failure.
        'behavioral_effect': (
            planner.get('fault_behavior_observed') is True
            and planner.get('fault_navigation_status') == 6
            and planner.get('planner_probe_error_code') == 208
        ),
        'rollback': all(
            row.get('recovery_success') is True and row.get('rollback_success') is True
            for row in strong_rows.values()
        ),
        'post_action_recovery': all(row.get('recovery_navigation_status') == 4 for row in strong_rows.values()),
        'm50_experience_key_hit': (
            m50.get('experience_checkpoint') == 'M_50'
            and m50.get('experience_environment_bin') == 'tb3_sandbox_gazebo'
            and m50.get('actual_map_id') == 'transfer_courtyard'
            and m50.get('experience_snapshot_sha256') == m50_snapshot_sha
            and matched_entry is not None
            and m50_episode.get('fault_behavior_observed') is True
            and m50_episode.get('episode_success') is True
            and m50.get('online_experience_update') is False
        ),
        'nav2_bt_audit': (
            bt_hash_matches
            and bt_audit.get('cannot_infer_executed_recovery_nodes_without_trace') is True
            and params_are_transfer_profile
        ),
    }
    all_pilot_passed = all(checks.values())
    result = {
        'pilot_id': 'eacr_supplementary_B_engineering_pilot_v1',
        'status': 'passed' if all_pilot_passed else 'failed',
        'seed': SEED,
        'registered_utc': '2026-10-08T16:20:02Z',
        'checks': checks,
        'strong_rule_record': str(strong_path.relative_to(ROOT)),
        'm50_key_hit_record': str(m50_path.relative_to(ROOT)),
        'm50_snapshot_path': str(M50_PATH.relative_to(ROOT)),
        'm50_snapshot_sha256': m50_snapshot_sha,
        'm50_training_context_key_verified': planner_key,
        'm50_training_context_entry': matched_entry,
        'm50_pilot_predicted_recovery_probability': m50_episode.get('predicted_recovery_probability'),
        'nav2_bt_audit_path': str(BT_AUDIT_PATH.relative_to(ROOT)),
        'nav2_bt_sha256': bt_audit.get('sha256'),
        'nav2_bt_hash_matches_installed_file': bt_hash_matches,
        'nav2_transfer_params_path': str(NAV2_PARAMS.relative_to(ROOT)),
        'nav2_transfer_params_sha256': sha256(NAV2_PARAMS),
        'nav2_transfer_global_costmap_plugins': ['static_layer', 'inflation_layer'],
        'nav2_transfer_local_costmap_plugins': ['voxel_layer', 'inflation_layer'],
        'per_family': per_family,
        'behavioral_failure_summary': {
            'families_with_pre_action_navigation_failure': [
                family for family, row in strong_rows.items() if row.get('fault_behavior_observed') is True
            ],
            'families_with_parameter_or_sensor_effect': [
                family for family, row in strong_rows.items() if row.get('fault_effect_observed') is True
            ],
            'interpretation': (
                'Control was correctly detected and its parameter rollback and post-action navigation '
                'succeeded, although its pre-action navigation still succeeded. This is reported as '
                'configuration repair, not behavior-failure recovery.'
            ),
        },
        'failed_design_attempts_excluded_from_evaluation': [
            {
                'path': 'results/supplementary_pilot_transfer_v2',
                'reason': 'global obstacle layer had already observed the unknown goal region before planner fault injection; fault navigation and valid-planner probe still succeeded',
            },
            {
                'path': 'results/supplementary_pilot_transfer_v3',
                'reason': 'clearing costmaps did not remove the global obstacle layer knowledge; planner fault remained configuration-only',
            },
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(OUT)
    print('status=', result['status'], 'checks=', checks)
    if not all_pilot_passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
