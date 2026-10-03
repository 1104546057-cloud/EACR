#!/usr/bin/env python3
"""Repeat the four phase-two fault injection/rollback service checks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
PAIRS = (
    ("localization", "/inject_localization_fault", "/rollback_localization_fault"),
    ("costmap", "/inject_costmap_fault", "/rollback_costmap_fault"),
    ("planner", "/inject_planner_fault", "/rollback_planner_fault"),
    ("control", "/inject_control_fault", "/rollback_control_fault"),
)
RESET_SERVICE = "/reset_episode"


def call(service: str) -> tuple[bool, str]:
    completed = subprocess.run(
        ["ros2", "service", "call", service, "std_srvs/srv/Trigger", "{}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0 and "success=True" in output, output


def main() -> None:
    checks = []
    for family, inject_service, rollback_service in PAIRS:
        reset, reset_output = call(RESET_SERVICE)
        injected, inject_output = call(inject_service)
        rolled_back, rollback_output = call(rollback_service) if injected else (False, "inject failed")
        checks.append({
            "family": family,
            "reset_success": reset,
            "reset_output": reset_output,
            "inject_service": inject_service,
            "inject_success": injected,
            "inject_output": inject_output,
            "rollback_service": rollback_service,
            "rollback_success": rolled_back,
            "rollback_output": rollback_output,
        })
    result = {
        "checks": checks,
        "acceptance": {
            "all_resets_succeeded": all(item["reset_success"] for item in checks),
            "all_injections_succeeded": all(item["inject_success"] for item in checks),
            "all_rollbacks_succeeded": all(item["rollback_success"] for item in checks),
        },
    }
    output_path = WORKSPACE / "results" / "phase2_fault_injector_validation.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(result["acceptance"].values()):
        raise SystemExit("fault injector validation failed")


if __name__ == "__main__":
    main()
