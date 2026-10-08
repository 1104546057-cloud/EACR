#!/usr/bin/env python3
"""Count confirmatory cells using the frozen aggregate record rules."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


def _aggregate():
    path = Path(__file__).resolve().parents[1] / "scripts" / "aggregate_phase4_final.py"
    spec = importlib.util.spec_from_file_location("phase4_final_aggregate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: phase4_final_count_cells.py METHOD RESULT_DIR", file=sys.stderr)
        return 2
    method, result_dir = sys.argv[1], Path(sys.argv[2])
    module = _aggregate()
    if method not in module.METHODS:
        print(f"unknown method {method}", file=sys.stderr)
        return 2
    repo = Path(__file__).resolve().parents[1]
    excluded: Counter[str] = Counter()
    found: dict[tuple[int, str], str] = {}
    if result_dir.is_dir():
        for path in sorted(result_dir.glob("phase3_gazebo_*.json")):
            if path.name == "phase3_gazebo_dispatch.json":
                continue
            try:
                item = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                excluded["unreadable"] += 1
                continue
            record = module._valid_record(path, item, repo, excluded)
            if record is None or record["method"] != method:
                continue
            found[(record["seed"], record["fault_family"])] = path.name
    expected = {(seed, family) for seed in module.SEEDS for family in module.FAMILIES}
    missing = sorted(expected - set(found))
    print(f"valid={len(found)}")
    print("missing=" + ",".join(f"{seed}:{family}" for seed, family in missing))
    print("excluded=" + json.dumps(dict(excluded), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
