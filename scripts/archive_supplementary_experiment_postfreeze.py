#!/usr/bin/env python3
"""Create the final archive with explicit post-freeze pilot/report amendments.

The B-protocol archive script is kept byte-for-byte frozen. This wrapper adds
the separately inventoried transfer pilot JSONs and the report-rendering
amendment, validates their hashes, and delegates archive creation/verification
to the frozen implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import archive_supplementary_experiment as frozen


ROOT = Path(__file__).resolve().parents[1]
PILOT_INVENTORY = ROOT / 'results/supplementary_pilot_raw_inventory_v1.json'
REPORT_AMENDMENT = ROOT / 'results/supplementary_report_rendering_amendment_01.json'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def postfreeze_inputs() -> tuple[list[Path], list[str]]:
    errors: list[str] = []
    additions: set[Path] = set()
    for manifest_path in (PILOT_INVENTORY, REPORT_AMENDMENT):
        if not manifest_path.is_file():
            errors.append(f'post-freeze archive record missing: {manifest_path.relative_to(ROOT)}')
            continue
        additions.add(manifest_path)

    if PILOT_INVENTORY.is_file():
        try:
            inventory = json.loads(PILOT_INVENTORY.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f'pilot raw inventory is unreadable: {exc}')
            inventory = {}
        expected_files = inventory.get('files', [])
        if inventory.get('missing_directories'):
            errors.append(f'pilot inventory records missing directories: {inventory["missing_directories"]}')
        if len(expected_files) != inventory.get('file_count'):
            errors.append('pilot inventory file_count does not match its file list')
        total_size = 0
        for item in expected_files:
            path = ROOT / item['path']
            if not path.is_file():
                errors.append(f'inventoried pilot raw file missing: {item["path"]}')
                continue
            size = path.stat().st_size
            digest = sha256(path)
            total_size += size
            if size != item.get('size_bytes') or digest != item.get('sha256'):
                errors.append(f'inventoried pilot raw file size/hash mismatch: {item["path"]}')
            additions.add(path)
        if total_size != inventory.get('total_size_bytes'):
            errors.append('pilot inventory total_size_bytes does not match the current files')

    if REPORT_AMENDMENT.is_file():
        try:
            amendment = json.loads(REPORT_AMENDMENT.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f'report-rendering amendment is unreadable: {exc}')
            amendment = {}
        script_path = ROOT / amendment.get('postfreeze_renderer_path', '')
        if not script_path.is_file():
            errors.append('post-freeze report renderer named by the amendment is missing')
        elif sha256(script_path) != amendment.get('postfreeze_renderer_sha256'):
            errors.append('post-freeze report renderer hash differs from its amendment')
        else:
            additions.add(script_path)
        protocol = json.loads(frozen.B_PROTOCOL.read_text())
        expected_frozen = protocol.get('source_sha256', {}).get('scripts/render_supplementary_report.py')
        frozen_renderer = ROOT / 'scripts/render_supplementary_report.py'
        if expected_frozen and sha256(frozen_renderer) != expected_frozen:
            errors.append('frozen report renderer no longer matches the B-protocol hash')

    return frozen.unique_files(additions), errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='check all gates and input hashes without creating an archive')
    args = parser.parse_args()

    errors, a, b, _ap, bp = frozen.completion_errors()
    extra_paths, extra_errors = postfreeze_inputs()
    errors.extend(extra_errors)
    if args.dry_run:
        print(f'completion_gate_passed={not errors}')
        for error in errors:
            print('INCOMPLETE:', error)
        if a and b and bp and not extra_errors:
            inputs = set(frozen.collect_inputs(a, b, bp))
            inputs.update(extra_paths)
            print(f'archive_input_files={len(frozen.unique_files(inputs))}')
            print(f'postfreeze_addition_files={len(extra_paths)}')
        return
    if errors:
        raise SystemExit('Refusing to archive incomplete experiment:\n- ' + '\n- '.join(errors))
    inputs = set(frozen.collect_inputs(a, b, bp))
    inputs.update(extra_paths)
    ordered = frozen.unique_files(inputs)
    output = frozen.choose_archive_path()
    print(json.dumps(frozen.create_archive(ordered, output, a, b), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
