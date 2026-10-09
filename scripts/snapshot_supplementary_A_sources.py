#!/usr/bin/env python3
"""Preserve the available A source snapshot before B modifies shared code.

Existing files are never overwritten.  The manifest distinguishes protocol
hash matches from the actual execution copy, since the A matrix dispatcher has
an unresolved provenance mismatch documented in its correction record.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'results/supplementary_protocol_A_v1.json'
AMENDMENT = ROOT / 'results/supplementary_A_execution_amendment_01.json'
DEST = ROOT / 'results/supplementary_A_source_snapshot'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    amendment = json.loads(AMENDMENT.read_text())
    DEST.mkdir(parents=True, exist_ok=True)
    records = []
    for registered_path, registered_hash in protocol['source_sha256'].items():
        source = Path(registered_path)
        if not source.is_absolute():
            source = ROOT / source
            snapshot_rel = Path('workspace') / Path(registered_path)
        else:
            snapshot_rel = Path('system') / source.relative_to('/')
        if not source.is_file():
            raise SystemExit(f'missing frozen source: {source}')
        snapshot = DEST / snapshot_rel
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not snapshot.exists():
            shutil.copy2(source, snapshot)
        content = snapshot.read_bytes()
        observed_hash = digest(content)
        current_hash = digest(source.read_bytes())
        records.append({
            'registered_path': registered_path,
            'snapshot_path': snapshot.relative_to(ROOT).as_posix(),
            'registered_sha256': registered_hash,
            'observed_at_snapshot_sha256': observed_hash,
            'matches_protocol_hash': observed_hash == registered_hash,
            'matches_current_source': observed_hash == current_hash,
        })

    manifest = {
        'snapshot_id': 'eacr_supplementary_A_sources_v1',
        'protocol_id': protocol['protocol_id'],
        'protocol_sha256': digest(PROTOCOL.read_bytes()),
        'execution_amendment_id': amendment.get('amendment_id'),
        'entries': records,
        'provenance_correction': 'results/supplementary_A_source_provenance_correction_01.json',
        'matrix_script_exact_frozen_source_recovered': False,
        'matrix_script_execution_copy_sha256': next(
            row['observed_at_snapshot_sha256'] for row in records
            if row['registered_path'] == 'scripts/run_phase3_gazebo_matrix.py'
        ),
    }
    manifest_path = DEST / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(manifest_path)
    mismatches = [row['registered_path'] for row in records if not row['matches_protocol_hash']]
    print(f'snapshotted={len(records)} protocol sources; protocol_hash_mismatches={mismatches}')


if __name__ == '__main__':
    main()
