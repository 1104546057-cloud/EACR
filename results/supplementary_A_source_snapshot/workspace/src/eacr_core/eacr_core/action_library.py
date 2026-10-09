"""Phase-two safe action catalogue with executable metadata."""

from __future__ import annotations

from .types import ActionSpec


def default_action_library() -> tuple[ActionSpec, ...]:
    return (
        ActionSpec(
            "inspect_tf",
            cost=0.15,
            risk=0.05,
            description="Collect TF, AMCL covariance and odometry consistency evidence.",
            expected_observables=("amcl_pose", "odom", "tf_consistency"),
            max_duration_sec=5.0,
            fault_families=("localization", "control"),
        ),
        ActionSpec(
            "inspect_costmap",
            cost=0.18,
            risk=0.05,
            description="Inspect local/global costmap freshness and obstacle agreement.",
            expected_observables=("local_costmap", "global_costmap"),
            max_duration_sec=5.0,
            fault_families=("costmap", "planner"),
        ),
        ActionSpec(
            "inspect_planner",
            cost=0.20,
            risk=0.05,
            description="Check planner lifecycle and recent planning diagnostics.",
            expected_observables=("planner_state", "plan_result"),
            max_duration_sec=5.0,
            fault_families=("planner",),
        ),
        ActionSpec(
            "inspect_controller",
            cost=0.20,
            risk=0.05,
            description="Check controller lifecycle and command freshness.",
            expected_observables=("controller_state", "cmd_vel", "odom"),
            max_duration_sec=5.0,
            fault_families=("control",),
        ),
        ActionSpec(
            "slow_observe",
            cost=0.35,
            risk=0.10,
            description="Hold zero command and observe a short controlled window.",
            expected_observables=("amcl_pose", "odom", "scan"),
            max_duration_sec=8.0,
            fault_families=("localization", "costmap", "planner", "control"),
        ),
        ActionSpec(
            "relocalize_amcl",
            cost=0.65,
            risk=0.25,
            description="Publish the configured initial pose and verify AMCL stability.",
            expected_observables=("amcl_pose", "amcl_covariance"),
            max_duration_sec=15.0,
            rollback_action_id="restore_previous_pose",
            fault_families=("localization",),
        ),
        ActionSpec(
            "clear_costmaps",
            cost=0.45,
            risk=0.20,
            description="Clear Nav2 local and global costmaps, then verify freshness.",
            expected_observables=("local_costmap", "global_costmap"),
            max_duration_sec=10.0,
            rollback_action_id="restore_costmap_observation",
            fault_families=("costmap", "planner"),
        ),
        ActionSpec(
            "reconfigure_planner",
            cost=0.55,
            risk=0.25,
            description="Restore planner lifecycle and verify a fresh plan.",
            expected_observables=("planner_state", "plan_result"),
            max_duration_sec=15.0,
            rollback_action_id="deactivate_planner",
            fault_families=("planner",),
        ),
        ActionSpec(
            "reconfigure_controller",
            cost=0.55,
            risk=0.25,
            description="Restore controller lifecycle and verify command output.",
            expected_observables=("controller_state", "cmd_vel", "odom"),
            max_duration_sec=15.0,
            rollback_action_id="deactivate_controller",
            fault_families=("control",),
        ),
    )
