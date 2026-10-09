#!/usr/bin/env python3
"""Create and verify a non-overwriting archive after the full A/B protocol passes."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

from render_supplementary_report import validate_complete

ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / 'backups'
A_AGG = ROOT / 'results/supplementary_A_aggregate.json'
B_AGG = ROOT / 'results/supplementary_B_aggregate.json'
A_PROTOCOL = ROOT / 'results/supplementary_protocol_A_v1.json'
B_PROTOCOL = ROOT / 'results/supplementary_protocol_B_v1.json'
REPORT = ROOT / 'docs/EACR_补充实验结果报告.md'
GEOMETRY = ROOT / 'results/supplementary_transfer_geometry_audit.json'

FILES = (
    'docs/EACR_补充实验接手笔记_2026-10-08.md',
    'docs/EACR_补充实验结果报告.md',
    'scripts/analyze_supplementary_A.py',
    'scripts/analyze_supplementary_B.py',
    'scripts/audit_supplementary_A_completion.py',
    'scripts/snapshot_supplementary_A_sources.py',
    'scripts/render_supplementary_report.py',
    'scripts/archive_supplementary_experiment.py',
    'scripts/audit_supplementary_transfer_geometry.py',
    'scripts/audit_supplementary_original.py',
    'scripts/source_eacr.sh',
    'scripts/run_phase3_gazebo_matrix.py',
    'src/eacr_core/eacr_core/action_library.py',
    'src/eacr_core/eacr_core/baselines.py',
    'src/eacr_sim/eacr_sim/phase3_gazebo_runner.py',
    'src/eacr_sim/eacr_sim/fault_injector.py',
    'src/eacr_sim/launch/eacr_episode.launch.py',
    'src/eacr_sim/config/episode.yaml',
    'src/eacr_sim/config/episode_transfer_courtyard.yaml',
    'src/eacr_sim/maps/transfer_courtyard.yaml',
    'src/eacr_sim/maps/transfer_courtyard.pgm',
    'src/eacr_sim/worlds/transfer_courtyard.sdf.xacro',
    'src/eacr_core/package.xml',
    'src/eacr_core/setup.py',
    'src/eacr_sim/package.xml',
    'src/eacr_sim/setup.py',
    'results/phase2_fault_injector.events.jsonl',
    'results/phase4_final_aggregate.json',
    'results/supplementary_original_audit.json',
    'results/supplementary_original_audit.md',
    'results/supplementary_protocol_A_v1.json',
    'results/supplementary_protocol_B_v1.json',
    'results/supplementary_A_execution_amendment_01.json',
    'results/supplementary_A_source_provenance_correction_01.json',
    'results/supplementary_A_source_snapshot/manifest.json',
    'results/supplementary_A_completion_audit.json',
    'results/supplementary_A_pairing_metadata_audit.json',
    'results/supplementary_A_costmap_readback_audit.json',
    'results/supplementary_nav2_bt_audit.json',
    'results/supplementary_transfer_geometry_audit.json',
    'results/supplementary_transfer_checkpoint_audit.json',
    'results/supplementary_A_aggregate.json',
    'results/supplementary_B_aggregate.json',
)
DIRS = (
    'results/supplementary_A_source_snapshot',
    'results/supplementary_original_strong_rule',
    'results/supplementary_transfer_static_m0',
    'results/supplementary_transfer_m50',
    'results/supplementary_transfer_strong_rule',
    'results/supplementary_transfer_events',
    'results/supplementary_pilot_original',
    'scripts',
    'src',
)
LOG_GLOBS = ('results/supplementary_A_*.log', 'results/supplementary_B_*.log', 'results/supplementary_pilot_transfer*.log')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_files(paths: set[Path]) -> list[Path]:
    return sorted((p for p in paths if p.is_file() and not p.is_symlink()
                   and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.pyo'}),
                  key=lambda p: str(p.relative_to(ROOT)))


def collect_inputs(a: dict[str, Any], b: dict[str, Any], b_protocol: dict[str, Any]) -> list[Path]:
    found: set[Path] = {ROOT / relative for relative in FILES}
    for relative in DIRS:
        directory = ROOT / relative
        if directory.exists():
            found.update(p for p in directory.rglob('*') if p.is_file())
    for pattern in LOG_GLOBS:
        found.update(ROOT.glob(pattern))
    # Include all selected raw records, including the original Static/M50 files
    # referenced by the paired analyses.
    for aggregate in (a, b):
        for cell in aggregate.get('selected_cells', []):
            path = ROOT / cell['path']
            if path.is_file():
                found.add(path)
    pilot_report = b_protocol.get('engineering_pilot', {}).get('report_path')
    if pilot_report:
        pilot_path = ROOT / pilot_report
        if pilot_path.is_file():
            found.add(pilot_path)
    return unique_files(found)


def completion_errors() -> tuple[list[str], dict[str, Any] | None, dict[str, Any] | None,
                                  dict[str, Any] | None, dict[str, Any] | None]:
    errors: list[str] = []
    try:
        a = json.loads(A_AGG.read_text())
        b = json.loads(B_AGG.read_text())
        ap = json.loads(A_PROTOCOL.read_text())
        bp = json.loads(B_PROTOCOL.read_text())
    except (OSError, ValueError) as exc:
        return [f'missing or unreadable aggregate/protocol: {exc}'], None, None, None, None
    try:
        validate_complete(a, b, ap, bp)
    except Exception as exc:
        errors.append(f'A/B completeness gate: {exc}')
    if not REPORT.is_file():
        errors.append(f'final Markdown report missing: {REPORT.relative_to(ROOT)}')
    else:
        content = REPORT.read_text()
        if a.get('protocol_sha256') not in content or b.get('protocol_sha256') not in content:
            errors.append('final report does not contain both aggregate protocol hashes')
    if not GEOMETRY.is_file():
        errors.append(f'transfer geometry audit missing: {GEOMETRY.relative_to(ROOT)}')
    else:
        try:
            geometry = json.loads(GEOMETRY.read_text())
            if geometry.get('static_checks_pass') is not True:
                errors.append('transfer geometry static checks are not passing')
        except ValueError:
            errors.append('transfer geometry audit JSON is malformed')
    pilot_report = bp.get('engineering_pilot', {}).get('report_path')
    if not pilot_report or not (ROOT / pilot_report).is_file():
        errors.append('B engineering pilot report path missing or file not found')
    required = [ROOT / name for name in FILES]
    required += [ROOT / 'results/supplementary_transfer_static_m0',
                 ROOT / 'results/supplementary_transfer_m50',
                 ROOT / 'results/supplementary_transfer_strong_rule']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        errors.append('required archive inputs missing: ' + ', '.join(missing))
    return errors, a, b, ap, bp


def choose_archive_path() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base = BACKUP_DIR / f'eacr_supplementary_{stamp}.tar.gz'
    candidate = base
    suffix = 1
    while candidate.exists() or candidate.with_suffix(candidate.suffix + '.sha256').exists():
        candidate = BACKUP_DIR / f'eacr_supplementary_{stamp}_{suffix:02d}.tar.gz'
        suffix += 1
    return candidate


def create_archive(inputs: list[Path], output: Path, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    manifest = {
        'archive_id': 'eacr_supplementary_final_v1',
        'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'a_protocol_sha256': a.get('protocol_sha256'),
        'b_protocol_sha256': b.get('protocol_sha256'),
        'files': [],
    }
    for path in inputs:
        data = path.read_bytes()
        manifest['files'].append({
            'path': str(path.relative_to(ROOT)), 'size_bytes': len(data),
            'sha256': sha256_bytes(data),
        })
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz', compresslevel=6) as archive:
        for path in inputs:
            archive.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
        info = tarfile.TarInfo('archive_manifest.json')
        info.size = len(manifest_data)
        info.mtime = int(dt.datetime.now().timestamp())
        archive.addfile(info, io.BytesIO(manifest_data))
    digest = sha256_bytes(output.read_bytes())
    sidecar = output.with_suffix(output.suffix + '.sha256')
    sidecar.write_text(f'{digest}  {output.name}\n')
    verify_archive(output)
    try:
        archive_label = str(output.relative_to(ROOT))
    except ValueError:
        archive_label = str(output)
    return {'archive': archive_label, 'sha256': digest,
            'file_count': len(inputs), 'size_bytes': output.stat().st_size}


def verify_archive(path: Path) -> None:
    with tarfile.open(path, 'r:gz') as archive:
        manifest_member = archive.extractfile('archive_manifest.json')
        if manifest_member is None:
            raise ValueError('archive manifest missing')
        manifest = json.loads(manifest_member.read())
        for item in manifest['files']:
            member = archive.extractfile(item['path'])
            if member is None:
                raise ValueError(f'archive member missing: {item["path"]}')
            data = member.read()
            if len(data) != item['size_bytes'] or sha256_bytes(data) != item['sha256']:
                raise ValueError(f'archive member hash/size mismatch: {item["path"]}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='show completion gate and input inventory without creating an archive')
    args = parser.parse_args()
    errors, a, b, _ap, bp = completion_errors()
    if args.dry_run:
        print(f'completion_gate_passed={not errors}')
        for error in errors:
            print('INCOMPLETE:', error)
        if a and b and bp:
            inputs = collect_inputs(a, b, bp)
            print(f'currently_available_files={len(inputs)}')
        return
    if errors:
        raise SystemExit('Refusing to archive incomplete experiment:\n- ' + '\n- '.join(errors))
    inputs = collect_inputs(a, b, bp)
    output = choose_archive_path()
    print(json.dumps(create_archive(inputs, output, a, b), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
