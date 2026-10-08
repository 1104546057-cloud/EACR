"""Run one reproducible phase-three baseline against the real Nav2 stack."""

from __future__ import annotations

import json
import hashlib
import math
import time
from pathlib import Path

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseWithCovarianceStamped, Quaternion
from rcl_interfaces.msg import ParameterType
from rcl_interfaces.srv import GetParameters
from nav2_msgs.action import NavigateToPose
from nav2_msgs.action import ComputePathToPose
from nav2_msgs.srv import ClearEntireCostmap
from lifecycle_msgs.srv import GetState
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger

from eacr_core.action_library import default_action_library
from eacr_core.baselines import BayesianFixedRecoveryPolicy, RuleBasedPolicy
from eacr_core.experience import ExperienceModel
from eacr_core.policy import PolicyWeights, choose_action
from eacr_core.scenario import DEFAULT_FAULT_SPECS, FaultSequence
from eacr_core.types import Context, Outcome


def quaternion_from_yaw(yaw: float) -> Quaternion:
    q = Quaternion()
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q


class Phase3GazeboRunner(Node):
    """Execute a baseline through the actual reset, fault and Nav2 interfaces."""

    def __init__(self) -> None:
        super().__init__('phase3_gazebo_runner')
        self.declare_parameter('baseline', 'eacr_evolving')
        self.declare_parameter('random_seed', 20260926)
        self.declare_parameter('result_dir', '/home/hu/文档/ChatGPT/论文/eacr_ws/results')
        self.declare_parameter('goal_x', 0.7508496046)
        self.declare_parameter('goal_y', 1.8354123831)
        self.declare_parameter('goal_yaw', 1.4751400097)
        self.declare_parameter('goal_timeout_sec', 60.0)
        self.declare_parameter('max_episodes', 4)
        self.declare_parameter('fault_family_filter', '')
        self.declare_parameter('experience_state_path', '')
        self.declare_parameter('resume_experience_state', False)
        self.declare_parameter('experience_snapshot_path', '')
        self.declare_parameter('experience_checkpoint', 'M_0')
        self.declare_parameter('experience_prior_mode', 'domain')
        self.declare_parameter('online_experience_update', True)
        self.declare_parameter('fault_repetitions', 1)
        self.declare_parameter('experience_environment_bin', 'tb3_sandbox_gazebo')
        self.declare_parameter('use_belief_action_scope', False)
        self.declare_parameter('fault_scale', 1.0)
        self.declare_parameter('auto_run', True)
        group = ReentrantCallbackGroup()
        self._reset = self.create_client(Trigger, '/reset_episode', callback_group=group)
        self._injectors = {
            family: self.create_client(Trigger, f'/inject_{family}_fault', callback_group=group)
            for family in ('localization', 'costmap', 'planner', 'control')
        }
        self._rollback = {
            family: self.create_client(Trigger, f'/rollback_{family}_fault', callback_group=group)
            for family in ('localization', 'costmap', 'planner', 'control')
        }
        self._nav = ActionClient(self, NavigateToPose, 'navigate_to_pose', callback_group=group)
        self._planner_probe_client = ActionClient(self, ComputePathToPose, 'compute_path_to_pose', callback_group=group)
        self._lifecycle = (
            self.create_client(GetState, '/controller_server/get_state', callback_group=group),
            self.create_client(GetState, '/bt_navigator/get_state', callback_group=group),
        )
        self._clear_costmaps = (
            self.create_client(ClearEntireCostmap, '/global_costmap/clear_entirely_global_costmap', callback_group=group),
            self.create_client(ClearEntireCostmap, '/local_costmap/clear_entirely_local_costmap', callback_group=group),
        )
        self._diagnostic_parameters = {
            'footprint_padding': (
                self.create_client(GetParameters, '/global_costmap/global_costmap/get_parameters', callback_group=group),
                'footprint_padding',
            ),
            'planner_plugins': (
                self.create_client(GetParameters, '/planner_server/get_parameters', callback_group=group),
                'planner_plugins',
            ),
            'min_x_velocity_threshold': (
                self.create_client(GetParameters, '/controller_server/get_parameters', callback_group=group),
                'min_x_velocity_threshold',
            ),
        }
        self._actions = default_action_library()
        self._experience = ExperienceModel()
        self._experience_context = Context(
            environment_bin=str(self.get_parameter('experience_environment_bin').value)
        )
        faults = {name: 0.25 for name in ('localization_drift', 'costmap_blockage', 'planner_failure', 'controller_failure')}
        prior_mode = str(self.get_parameter('experience_prior_mode').value)
        if prior_mode == 'weak_shared_m0':
            self._experience.seed_weak_prior(faults, self._experience_context, [action.action_id for action in self._actions])
        else:
            self._experience.seed_domain_prior(faults, self._experience_context, [action.action_id for action in self._actions])
        snapshot_path = str(self.get_parameter('experience_snapshot_path').value).strip()
        self._snapshot_path = snapshot_path or None
        checkpoint = str(self.get_parameter('experience_checkpoint').value)
        if checkpoint in {'M_20', 'M_50'} and not snapshot_path:
            raise ValueError(f'{checkpoint} requires experience_snapshot_path')
        self._loaded_snapshot_sha256 = None
        if snapshot_path:
            snapshot_file = Path(snapshot_path)
            snapshot_bytes = snapshot_file.read_bytes()
            self._experience = ExperienceModel.from_snapshot(json.loads(snapshot_bytes))
            self._loaded_snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        state_path = str(self.get_parameter('experience_state_path').value).strip()
        if state_path and not snapshot_path and bool(self.get_parameter('resume_experience_state').value):
            try:
                state_file = Path(state_path)
                if state_file.exists():
                    self._experience = ExperienceModel.from_snapshot(json.loads(state_file.read_text()))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.get_logger().warning(f'Ignoring invalid experience state: {exc}')
        self._amcl_pose: PoseWithCovarianceStamped | None = None
        self._amcl_seen_at = 0.0
        self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self._amcl_callback, 10,
            callback_group=group)
        self._timer = self.create_timer(2.0, self._start_once, callback_group=group)
        self._started = False

    def _amcl_callback(self, msg: PoseWithCovarianceStamped) -> None:
        if msg.header.frame_id in ('', 'map'):
            self._amcl_pose = msg
            self._amcl_seen_at = time.monotonic()

    def _online_belief(self, after_monotonic: float) -> tuple[dict[str, float], dict]:
        """Use only online AMCL evidence; the injected family is not an input."""
        deadline = time.monotonic() + 3.0
        while self._amcl_seen_at <= after_monotonic and time.monotonic() < deadline:
            time.sleep(0.05)
        faults = ('localization_drift', 'costmap_blockage', 'planner_failure', 'controller_failure')
        scores = {fault: 1.0 for fault in faults}
        fresh = self._amcl_pose is not None and self._amcl_seen_at > after_monotonic
        evidence = {
            'amcl_available': self._amcl_pose is not None,
            'amcl_fresh_after_injection': fresh,
            'amcl_distance_to_start_m': None,
            'nav2_parameters': {},
        }
        if fresh and self._amcl_pose is not None:
            pose = self._amcl_pose.pose.pose.position
            distance = math.hypot(pose.x + 2.0, pose.y + 0.5)
            evidence['amcl_distance_to_start_m'] = distance
            if distance > 0.35:
                scores['localization_drift'] *= 7.0
        for label, (client, name) in self._diagnostic_parameters.items():
            evidence['nav2_parameters'][label] = self._read_parameter(client, name)
        padding = evidence['nav2_parameters'].get('footprint_padding')
        plugins = evidence['nav2_parameters'].get('planner_plugins')
        threshold = evidence['nav2_parameters'].get('min_x_velocity_threshold')
        if isinstance(padding, float) and padding > 0.5:
            scores['costmap_blockage'] *= 9.0
        if isinstance(plugins, list) and 'GridBased' not in plugins:
            scores['planner_failure'] *= 9.0
        if isinstance(threshold, float) and threshold > 1.0:
            scores['controller_failure'] *= 9.0
        total = sum(scores.values())
        belief = {fault: score / total for fault, score in scores.items()}
        return belief, evidence

    @staticmethod
    def _read_parameter(client, name: str) -> float | list[str] | None:
        if not client.wait_for_service(timeout_sec=2.0):
            return None
        request = GetParameters.Request()
        request.names = [name]
        future = client.call_async(request)
        deadline = time.monotonic() + 3.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done() or future.result() is None or not future.result().values:
            return None
        value = future.result().values[0]
        if value.type == ParameterType.PARAMETER_DOUBLE:
            return float(value.double_value)
        if value.type == ParameterType.PARAMETER_STRING_ARRAY:
            return list(value.string_array_value)
        return None

    def _start_once(self) -> None:
        if self._started:
            return
        self._started = True
        self._timer.cancel()
        self._run()

    def _call(self, client, label: str, timeout: float = 30.0) -> tuple[bool, str]:
        if not client.wait_for_service(timeout_sec=8.0):
            return False, f'{label}: service unavailable'
        future = client.call_async(Trigger.Request())
        deadline = time.monotonic() + timeout
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done():
            return False, f'{label}: timeout'
        try:
            result = future.result()
            return bool(result.success), str(result.message)
        except Exception as exc:  # pragma: no cover - runtime ROS failure
            return False, f'{label}: {exc}'

    def _send_goal(self) -> tuple[int | None, float, str]:
        if not self._nav2_active():
            return None, 0.0, 'nav2_inactive'
        if not self._nav.wait_for_server(timeout_sec=10.0):
            return None, 0.0, 'action_server_unavailable'
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(self.get_parameter('goal_x').value)
        goal.pose.pose.position.y = float(self.get_parameter('goal_y').value)
        goal.pose.pose.orientation = quaternion_from_yaw(float(self.get_parameter('goal_yaw').value))
        started = time.monotonic()
        send_future = self._nav.send_goal_async(goal)
        deadline = time.monotonic() + 10.0
        while not send_future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not send_future.done() or send_future.result() is None:
            return None, time.monotonic() - started, 'goal_send_timeout'
        handle = send_future.result()
        if not handle.accepted:
            return GoalStatus.STATUS_UNKNOWN, time.monotonic() - started, 'goal_rejected'
        result_future = handle.get_result_async()
        deadline = time.monotonic() + float(self.get_parameter('goal_timeout_sec').value)
        while not result_future.done() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not result_future.done():
            cancel_future = handle.cancel_goal_async()
            cancel_deadline = time.monotonic() + 5.0
            while not cancel_future.done() and time.monotonic() < cancel_deadline:
                time.sleep(0.05)
            while not result_future.done() and time.monotonic() < cancel_deadline:
                time.sleep(0.05)
            status = int(result_future.result().status) if result_future.done() else GoalStatus.STATUS_UNKNOWN
            reason = 'navigation_timeout' if result_future.done() else 'navigation_timeout_cancel_unconfirmed'
            return status, time.monotonic() - started, reason
        return int(result_future.result().status), time.monotonic() - started, 'completed'

    def _planner_probe(self) -> tuple[bool, int | None, str]:
        """Ask planner for a path with an invalid planner id.

        This is an explicit planner-channel probe.  It is used only while the
        planner fault is injected and is recorded separately from navigation.
        """
        if not self._nav2_active() or not self._planner_probe_client.wait_for_server(timeout_sec=5.0):
            return False, None, 'planner_action_unavailable'
        goal = ComputePathToPose.Goal()
        goal.goal.header.frame_id = 'map'
        goal.goal.header.stamp = self.get_clock().now().to_msg()
        goal.goal.pose.position.x = float(self.get_parameter('goal_x').value)
        goal.goal.pose.position.y = float(self.get_parameter('goal_y').value)
        goal.goal.pose.orientation = quaternion_from_yaw(float(self.get_parameter('goal_yaw').value))
        goal.planner_id = 'EacrInvalidPlanner'
        future = self._planner_probe_client.send_goal_async(goal)
        deadline = time.monotonic() + 8.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done() or future.result() is None or not future.result().accepted:
            return False, None, 'planner_probe_rejected'
        result_future = future.result().get_result_async()
        deadline = time.monotonic() + 12.0
        while not result_future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not result_future.done():
            return False, None, 'planner_probe_timeout'
        result = result_future.result().result
        return result.error_code == ComputePathToPose.Result.INVALID_PLANNER, int(result.error_code), result.error_msg

    def _nav2_active(self) -> bool:
        for client in self._lifecycle:
            if not client.wait_for_service(timeout_sec=2.0):
                return False
            future = client.call_async(GetState.Request())
            deadline = time.monotonic() + 3.0
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not future.done() or future.result() is None or future.result().current_state.id != 3:
                return False
        return True

    def _clear_costmaps_after_recovery(self) -> None:
        for client in self._clear_costmaps:
            if not client.wait_for_service(timeout_sec=3.0):
                continue
            future = client.call_async(ClearEntireCostmap.Request())
            deadline = time.monotonic() + 5.0
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.05)

    def _choose(self, baseline: str, belief: dict[str, float]):
        context = self._experience_context
        if baseline == 'rule_based_recovery':
            return RuleBasedPolicy().choose(self._actions)
        if baseline == 'bayesian_fixed_recovery':
            return BayesianFixedRecoveryPolicy().choose(self._actions, belief)
        weights = PolicyWeights(
            information_gain=0.0 if baseline in {'ig_without_evolving_experience', 'without_information_gain'} else 1.0,
            recovery_gain=0.0 if baseline == 'without_recovery_utility' else 1.0,
            uncertainty=0.0 if baseline == 'without_model_uncertainty' else 0.4,
            risk_limit=1.0 if baseline == 'without_risk_constraint' else 0.40,
        )
        actions = self._actions
        if bool(self.get_parameter('use_belief_action_scope').value) and belief:
            family_by_fault = {
                'localization_drift': 'localization',
                'costmap_blockage': 'costmap',
                'planner_failure': 'planner',
                'controller_failure': 'control',
            }
            dominant_fault = max(belief, key=belief.get)
            dominant_family = family_by_fault.get(dominant_fault)
            if dominant_family:
                scoped = tuple(
                    action for action in self._actions
                    if dominant_family in action.fault_families
                    or action.action_id == 'slow_observe'
                )
                if scoped:
                    actions = scoped
        return choose_action(actions, belief, context, self._experience, weights)

    def _run(self) -> None:
        baseline = str(self.get_parameter('baseline').value)
        seed = int(self.get_parameter('random_seed').value)
        repetitions = max(1, int(self.get_parameter('fault_repetitions').value))
        repeated_specs = tuple(
            spec for _ in range(repetitions) for spec in DEFAULT_FAULT_SPECS
        )
        sequence = FaultSequence.from_specs(repeated_specs, seed=seed, episode_prefix=f'phase3_gazebo_{seed}')
        rows = []
        nav2_ready = self._nav2_active()
        family_filter = str(self.get_parameter('fault_family_filter').value).strip()
        events = tuple(event for event in sequence.events if not family_filter or event.fault.family.value == family_filter)
        for event in events[:int(self.get_parameter('max_episodes').value)]:
            family = event.fault.family
            nominal_reset_ok, nominal_reset_detail = self._call(self._reset, 'nominal_reset')
            nominal_status, nominal_duration, nominal_reason = self._send_goal() if nominal_reset_ok else (None, 0.0, 'reset_failed')
            nominal_valid = nominal_status == GoalStatus.STATUS_SUCCEEDED
            # A reset can race the AMCL/Nav2 settling window after a previous
            # episode. Retry the paired nominal trial once after a fresh reset;
            # the final record still requires an actually succeeded nominal
            # navigation and keeps the retry auditable.
            nominal_attempts = 1
            if not nominal_valid and nominal_reset_ok:
                retry_reset_ok, retry_reset_detail = self._call(self._reset, 'nominal_retry_reset')
                if retry_reset_ok:
                    nominal_attempts = 2
                    nominal_status, retry_duration, retry_reason = self._send_goal()
                    nominal_duration += retry_duration
                    nominal_reason = f'retry_after_{nominal_reason}:{retry_reason}'
                    nominal_reset_detail = f'{nominal_reset_detail}; retry: {retry_reset_detail}'
                    nominal_valid = nominal_status == GoalStatus.STATUS_SUCCEEDED
            reset_ok, reset_detail = self._call(self._reset, 'fault_reset')
            injection_started = time.monotonic()
            inject_ok, inject_detail = (
                self._call(self._injectors[family.value], 'inject')
                if reset_ok and nominal_valid else (False, 'nominal navigation or reset failed')
            )
            injection_confirmed = inject_ok
            belief, online_evidence = self._online_belief(injection_started)
            if baseline == 'without_belief_update':
                belief = {fault: 0.25 for fault in (
                    'localization_drift', 'costmap_blockage',
                    'planner_failure', 'controller_failure',
                )}
                online_evidence['belief_update_ablation'] = 'uniform_belief'
            fault_status, fault_duration, fault_reason = self._send_goal() if inject_ok else (None, 0.0, 'inject_failed')
            planner_probe_observed = None
            planner_probe_error_code = None
            if family.value == 'planner' and inject_ok:
                planner_probe_observed, planner_probe_error_code, planner_probe_detail = self._planner_probe()
            else:
                planner_probe_detail = 'not_applicable'
            decision = self._choose(baseline, belief) if inject_ok else None
            action_id = decision.selected_action if decision else None
            context = self._experience_context
            predicted_recovery_probability = (
                self._experience.recovery_probability(belief, context, action_id)
                if action_id else None
            )
            # Recovery actions are represented by the corresponding rollback
            # service so the experiment remains reversible and auditable.
            recovery_ok = False
            recovery_detail = 'no recovery action'
            expected_recovery = {
                'relocalize_amcl': 'localization',
                'clear_costmaps': 'costmap',
                'reconfigure_planner': 'planner',
                'reconfigure_controller': 'control',
            }
            if action_id in expected_recovery and expected_recovery[action_id] == family.value:
                recovery_ok, recovery_detail = self._call(self._rollback[family.value], 'recovery')
                inject_ok = False if recovery_ok else inject_ok
            elif action_id in expected_recovery:
                recovery_detail = f'{action_id} does not target the active fault; no recovery was applied'
            # End-to-end time from the start of fault injection to the
            # completion of a successful recovery intervention.  Failed or
            # diagnostic actions are right-censored and recorded as null.
            time_to_recovery_sec = (
                time.monotonic() - injection_started if recovery_ok else None
            )
            if inject_ok:
                rollback_ok, rollback_detail = self._call(self._rollback[family.value], 'rollback')
            else:
                rollback_ok, rollback_detail = True, 'already rolled back by recovery'
            if rollback_ok:
                self._clear_costmaps_after_recovery()
                time.sleep(2.0)
            # Every baseline gets the same post-intervention navigation trial.
            # A mismatched action is recorded as a recovery failure, but it
            # must not silently remove the paired recovery observation.
            recovery_status, recovery_duration, recovery_reason = (
                self._send_goal() if reset_ok and rollback_ok
                else (None, 0.0, 'recovery_not_executed')
            )
            fault_behavior_observed = nominal_valid and (
                fault_status == GoalStatus.STATUS_ABORTED or fault_reason == 'navigation_timeout'
            )
            fault_effect_observed = fault_behavior_observed
            fault_effect_reason = 'navigation_abort_or_timeout' if fault_behavior_observed else 'no_behavioral_failure'
            if family.value == 'localization':
                # Localization faults can leave Nav2 moving while AMCL is
                # already inconsistent with the reset pose.  Count that
                # paired sensor effect explicitly instead of requiring an
                # unrelated navigation abort.
                distance = online_evidence.get('amcl_distance_to_start_m')
                localization_shift = isinstance(distance, (int, float)) and float(distance) > 0.35
                fault_effect_observed = bool(fault_effect_observed or localization_shift)
                if localization_shift:
                    fault_effect_reason = 'amcl_displacement_over_threshold'
            elif family.value == 'costmap':
                padding = online_evidence.get('nav2_parameters', {}).get('footprint_padding')
                parameter_changed = isinstance(padding, (int, float)) and float(padding) > 0.5
                fault_effect_observed = bool(fault_effect_observed or parameter_changed)
                if parameter_changed and not fault_behavior_observed:
                    fault_effect_reason = 'costmap_footprint_padding_readback'
            if family.value == 'planner':
                plugins = online_evidence.get('nav2_parameters', {}).get('planner_plugins')
                planner_configuration_changed = (
                    isinstance(plugins, list) and 'GridBased' not in plugins
                )
                fault_effect_observed = bool(
                    fault_behavior_observed or planner_configuration_changed
                )
                if planner_configuration_changed:
                    fault_effect_reason = 'planner_plugins_readback'
            if family.value == 'control':
                threshold = online_evidence.get('nav2_parameters', {}).get('min_x_velocity_threshold')
                parameter_changed = isinstance(threshold, (int, float)) and float(threshold) > 1.0
                fault_effect_observed = bool(fault_effect_observed or parameter_changed)
                if parameter_changed and not fault_behavior_observed:
                    fault_effect_reason = 'controller_threshold_readback'
            success = fault_effect_observed and recovery_status == GoalStatus.STATUS_SUCCEEDED and recovery_ok and rollback_ok
            experience_before = self._experience.snapshot()
            episode_evidence_valid = bool(
                nav2_ready and nominal_valid and reset_ok and injection_confirmed
                and fault_effect_observed and rollback_ok
                and recovery_status is not None
            )
            update_experience = bool(
                bool(self.get_parameter('online_experience_update').value)
                and baseline in {'eacr_evolving', 'full_eacr'}
                and episode_evidence_valid and decision and action_id
            )
            if update_experience:
                self._experience.update(
                    belief, self._experience_context, action_id,
                    Outcome.RECOVERY_SUCCESS if success else Outcome.RECOVERY_FAILURE,
                    recovery_success=success,
                )
            rows.append({
                'episode_id': event.episode_id,
                'fault_family': family.value,
                'fault_id': event.fault.fault_id,
                'reset_success': reset_ok,
                'nominal_reset_success': nominal_reset_ok,
                'nominal_navigation_status': nominal_status,
                'nominal_navigation_duration_sec': nominal_duration,
                'nominal_navigation_reason': nominal_reason,
                'nominal_navigation_attempts': nominal_attempts,
                'nominal_navigation_valid': nominal_valid,
                'inject_success': injection_confirmed,
                'selected_action': action_id,
                'online_evidence': online_evidence,
                'belief_before_action': belief,
                'decision': decision.as_dict() if decision else None,
                'predicted_recovery_probability': predicted_recovery_probability,
                'intervention_cost': next(
                    (float(action.cost) for action in self._actions if action.action_id == action_id),
                    None,
                ),
                'recovery_success': recovery_ok,
                'time_to_recovery_sec': time_to_recovery_sec,
                'rollback_success': rollback_ok,
                'fault_navigation_status': fault_status,
                'fault_navigation_duration_sec': fault_duration,
                'fault_navigation_reason': fault_reason,
                'fault_effect_observed': fault_effect_observed,
                'fault_behavior_observed': fault_behavior_observed,
                'fault_effect_reason': fault_effect_reason,
                'planner_probe_observed': planner_probe_observed,
                'planner_probe_error_code': planner_probe_error_code,
                'planner_probe_detail': planner_probe_detail,
                'recovery_navigation_status': recovery_status,
                'recovery_navigation_duration_sec': recovery_duration,
                'recovery_navigation_reason': recovery_reason,
                'episode_success': success,
                'experience_after_episode': self._experience.snapshot(),
                'experience_before_episode': experience_before,
                'experience_updated_online': update_experience,
                'episode_evidence_valid': episode_evidence_valid,
                'details': {
                    'nominal_reset': nominal_reset_detail,
                    'reset': reset_detail,
                    'inject': inject_detail,
                    'recovery': recovery_detail,
                    'rollback': rollback_detail,
                },
            })
        structural_complete = bool(
            nav2_ready and rows and all(
                row['episode_evidence_valid']
                for row in rows
            )
        )
        result = {
            'protocol_id': 'eacr_phase3_v1',
            'gazebo_observation_adapter': True,
            'synthetic_dry_run': False,
            'baseline': baseline,
            'seed': seed,
            'experience_checkpoint': str(self.get_parameter('experience_checkpoint').value),
            'experience_snapshot_path': self._snapshot_path,
            'experience_snapshot_sha256': self._loaded_snapshot_sha256,
            'experience_prior_mode': str(self.get_parameter('experience_prior_mode').value),
            'online_experience_update': bool(self.get_parameter('online_experience_update').value),
            'resume_experience_state': bool(self.get_parameter('resume_experience_state').value),
            'fault_repetitions': repetitions,
            'experience_environment_bin': str(self.get_parameter('experience_environment_bin').value),
            'use_belief_action_scope': bool(self.get_parameter('use_belief_action_scope').value),
            'fault_scale': float(self.get_parameter('fault_scale').value),
            'goal': {'x': self.get_parameter('goal_x').value, 'y': self.get_parameter('goal_y').value, 'yaw': self.get_parameter('goal_yaw').value},
            'episodes': rows,
            'recovery_success_rate': sum(float(row['episode_success']) for row in rows) / len(rows),
            'fault_effect_observed_rate': sum(float(row['fault_effect_observed']) for row in rows) / len(rows),
            'nav2_ready_at_start': nav2_ready,
            'infrastructure_failure': not nav2_ready,
            'protocol_compliant': structural_complete,
            'protocol_gaps': [] if structural_complete else ['paired episode evidence incomplete'],
        }
        state_path = str(self.get_parameter('experience_state_path').value).strip()
        if state_path and baseline in {'eacr_evolving', 'full_eacr'}:
            state_file = Path(state_path)
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(self._experience.snapshot(), ensure_ascii=False, indent=2) + '\n')
            result['experience_state_path'] = str(state_file)
        run_id = time.time_ns()
        result['run_id'] = run_id
        output = Path(str(self.get_parameter('result_dir').value)) / f'phase3_gazebo_{baseline}_{seed}_{run_id}.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        self.get_logger().info(f'Gazebo phase-three result: {output}')
        self.create_timer(0.2, rclpy.shutdown)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Phase3GazeboRunner()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
