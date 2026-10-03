"""Minimum ROS integration loop for one repeatable AMCL localization fault.

The node deliberately keeps simulator ground truth out of the online loop. It
injects a wrong AMCL initial pose through the same public ``/initialpose``
interface a user can use, collects AMCL/odometry evidence, calls the pure
Python EACR policy, executes one safe recovery action, verifies a stable AMCL
pose, and updates the experience model with belief-weighted responsibility.
"""

from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Optional

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Quaternion, Twist
from nav_msgs.msg import Odometry
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger

from eacr_core.belief import bayesian_update, posterior_after_outcome
from eacr_core.experience import ExperienceModel
from eacr_core.policy import PolicyWeights, choose_action
from eacr_core.records import EpisodeRecorder
from eacr_core.types import ActionSpec, Context, Outcome


def quaternion_from_yaw(yaw: float) -> Quaternion:
    msg = Quaternion()
    msg.z = math.sin(yaw / 2.0)
    msg.w = math.cos(yaw / 2.0)
    return msg


def yaw_from_quaternion(q: Quaternion) -> float:
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


class EacrLocalizationLoop(Node):
    """One-service minimum EACR localization-fault experiment."""

    def __init__(self) -> None:
        super().__init__('eacr_localization_loop')
        self.declare_parameter('initial_pose_x', -2.0)
        self.declare_parameter('initial_pose_y', -0.5)
        self.declare_parameter('initial_pose_yaw', 0.0)
        self.declare_parameter('fault_offset_x', 0.65)
        self.declare_parameter('fault_offset_y', -0.45)
        self.declare_parameter('fault_offset_yaw', 0.35)
        self.declare_parameter('evidence_wait_sec', 1.5)
        self.declare_parameter('recovery_wait_sec', 3.0)
        self.declare_parameter('stable_samples_required', 5)
        self.declare_parameter('stable_position_tolerance_m', 0.20)
        self.declare_parameter('stable_yaw_tolerance_rad', 0.25)
        self.declare_parameter('reset_before_episode', True)
        self.declare_parameter('random_seed', 20260926)
        self.declare_parameter('result_dir', '/home/hu/文档/ChatGPT/论文/eacr_ws/results')

        callback_group = ReentrantCallbackGroup()
        self._initial_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped, '/initialpose', 10)
        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self._amcl_sub = self.create_subscription(
            PoseWithCovarianceStamped,
            '/amcl_pose',
            self._amcl_callback,
            10,
            callback_group=callback_group,
        )
        self._odom_sub = self.create_subscription(
            Odometry,
            '/odom',
            self._odom_callback,
            10,
            callback_group=callback_group,
        )
        self._inject_srv = self.create_service(
            Trigger,
            '/inject_amcl_fault',
            self._inject_callback,
            callback_group=callback_group,
        )
        self._run_srv = self.create_service(
            Trigger,
            '/run_eacr_localization_episode',
            self._run_callback,
            callback_group=callback_group,
        )
        self._reset_client = self.create_client(
            Trigger, '/reset_episode', callback_group=callback_group)
        self._amcl_pose: Optional[PoseWithCovarianceStamped] = None
        self._odom: Optional[Odometry] = None
        self._model = ExperienceModel()
        self._seed_action_priors()
        self._episode_lock = threading.Lock()
        self._episode_index = 0
        self.get_logger().info(
            'EACR localization loop ready: /inject_amcl_fault and '
            '/run_eacr_localization_episode')

    def _amcl_callback(self, msg: PoseWithCovarianceStamped) -> None:
        if msg.header.frame_id in ('', 'map'):
            self._amcl_pose = msg

    def _odom_callback(self, msg: Odometry) -> None:
        self._odom = msg

    def _pose_message(self, x: float, y: float, yaw: float) -> PoseWithCovarianceStamped:
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = x
        msg.pose.pose.position.y = y
        msg.pose.pose.orientation = quaternion_from_yaw(yaw)
        msg.pose.covariance[0] = 0.25
        msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.10
        return msg

    def _publish_initial_pose(self, x: float, y: float, yaw: float, repeats: int = 3) -> None:
        msg = self._pose_message(x, y, yaw)
        for _ in range(repeats):
            self._initial_pose_pub.publish(msg)
            time.sleep(0.10)

    def _inject_fault(self) -> dict:
        x = float(self.get_parameter('initial_pose_x').value)
        y = float(self.get_parameter('initial_pose_y').value)
        yaw = float(self.get_parameter('initial_pose_yaw').value)
        offset = {
            'x': float(self.get_parameter('fault_offset_x').value),
            'y': float(self.get_parameter('fault_offset_y').value),
            'yaw': float(self.get_parameter('fault_offset_yaw').value),
        }
        self._publish_initial_pose(x + offset['x'], y + offset['y'], yaw + offset['yaw'])
        return {'type': 'amcl_initial_pose_offset', 'offset': offset}

    def _inject_callback(self, _request, response):
        fault = self._inject_fault()
        response.success = True
        response.message = json.dumps(fault, ensure_ascii=False)
        self.get_logger().warn(f'Injected repeatable AMCL fault: {response.message}')
        return response

    def _evidence(self) -> dict:
        initial_x = float(self.get_parameter('initial_pose_x').value)
        initial_y = float(self.get_parameter('initial_pose_y').value)
        initial_yaw = float(self.get_parameter('initial_pose_yaw').value)
        evidence = {
            'amcl_available': self._amcl_pose is not None,
            'odom_available': self._odom is not None,
            'amcl_covariance_xy': None,
            'amcl_distance_to_expected_start_m': None,
            'amcl_yaw_error_rad': None,
            'odom_speed_mps': None,
        }
        if self._amcl_pose is not None:
            pose = self._amcl_pose.pose.pose
            covariance = self._amcl_pose.pose.covariance
            evidence['amcl_covariance_xy'] = float(covariance[0] + covariance[7])
            evidence['amcl_distance_to_expected_start_m'] = float(
                math.hypot(pose.position.x - initial_x, pose.position.y - initial_y))
            evidence['amcl_yaw_error_rad'] = float(
                abs(math.atan2(math.sin(yaw_from_quaternion(pose.orientation) - initial_yaw),
                               math.cos(yaw_from_quaternion(pose.orientation) - initial_yaw))))
        if self._odom is not None:
            twist = self._odom.twist.twist
            evidence['odom_speed_mps'] = float(math.hypot(twist.linear.x, twist.linear.y))
        return evidence

    def _belief_from_evidence(self, evidence: dict) -> tuple[dict[str, float], dict[str, float]]:
        distance = evidence['amcl_distance_to_expected_start_m']
        covariance = evidence['amcl_covariance_xy']
        yaw_error = evidence['amcl_yaw_error_rad']
        if distance is None:
            distance = 0.0
        if covariance is None:
            covariance = 1.0
        if yaw_error is None:
            yaw_error = 0.0
        likelihood = {
            'localization_drift': min(0.98, 0.35 + 0.80 * min(1.0, distance)),
            'odom_tf_inconsistency': min(0.98, 0.30 + 0.35 * min(1.0, covariance)),
            'amcl_degeneracy': min(0.98, 0.35 + 0.45 * min(1.0, yaw_error)),
        }
        prior = {fault: 1.0 / 3.0 for fault in likelihood}
        return bayesian_update(prior, likelihood), likelihood

    def _actions(self) -> tuple[ActionSpec, ...]:
        return (
            ActionSpec('inspect_tf', cost=0.15, risk=0.05),
            ActionSpec('slow_observe', cost=0.35, risk=0.10),
            ActionSpec('relocalize_amcl', cost=0.65, risk=0.25),
        )

    def _seed_action_priors(self) -> None:
        """Install explicit action-observation priors for M0.

        These are domain priors, not successful test episodes.  Without them
        every unseen action has the same uniform outcome distribution and IG
        collapses to zero, making cost the only ranking signal.
        """
        context = Context(environment_bin='amcl_fault')
        faults = ('localization_drift', 'odom_tf_inconsistency', 'amcl_degeneracy')
        priors = {
            'inspect_tf': {
                'localization_drift': {'diagnostic_support': 0.35, 'diagnostic_conflict': 0.35, 'inconclusive': 0.30},
                'odom_tf_inconsistency': {'diagnostic_support': 0.80, 'diagnostic_conflict': 0.10, 'inconclusive': 0.10},
                'amcl_degeneracy': {'diagnostic_support': 0.25, 'diagnostic_conflict': 0.45, 'inconclusive': 0.30},
            },
            'slow_observe': {fault: {'diagnostic_support': 0.15, 'diagnostic_conflict': 0.15, 'inconclusive': 0.70} for fault in faults},
            'relocalize_amcl': {fault: {'recovery_success': 0.80, 'recovery_failure': 0.20} for fault in faults},
        }
        for action_id, by_fault in priors.items():
            for fault, outcomes in by_fault.items():
                belief = {candidate: float(candidate == fault) for candidate in faults}
                for outcome, probability in outcomes.items():
                    self._model.update(belief, context, action_id, outcome, outcome_weight=3.0 * probability)

    def _verify_recovery(self) -> tuple[bool, dict]:
        deadline = time.monotonic() + float(self.get_parameter('recovery_wait_sec').value)
        required = int(self.get_parameter('stable_samples_required').value)
        position_tolerance = float(self.get_parameter('stable_position_tolerance_m').value)
        yaw_tolerance = float(self.get_parameter('stable_yaw_tolerance_rad').value)
        stable_samples = 0
        while time.monotonic() < deadline:
            evidence = self._evidence()
            distance = evidence['amcl_distance_to_expected_start_m']
            yaw_error = evidence['amcl_yaw_error_rad']
            if (distance is not None and yaw_error is not None
                    and distance <= position_tolerance and yaw_error <= yaw_tolerance):
                stable_samples += 1
                if stable_samples >= required:
                    return True, evidence
            else:
                stable_samples = 0
            time.sleep(0.20)
        return False, self._evidence()

    def _execute(self, action_id: str) -> tuple[Outcome, bool, dict]:
        if action_id == 'inspect_tf':
            time.sleep(float(self.get_parameter('evidence_wait_sec').value))
            return Outcome.DIAGNOSTIC_SUPPORT, False, self._evidence()
        if action_id == 'slow_observe':
            zero = Twist()
            self._cmd_vel_pub.publish(zero)
            time.sleep(float(self.get_parameter('evidence_wait_sec').value))
            return Outcome.INCONCLUSIVE, False, self._evidence()
        if action_id == 'relocalize_amcl':
            x = float(self.get_parameter('initial_pose_x').value)
            y = float(self.get_parameter('initial_pose_y').value)
            yaw = float(self.get_parameter('initial_pose_yaw').value)
            self._publish_initial_pose(x, y, yaw, repeats=5)
            ok, evidence = self._verify_recovery()
            return (
                Outcome.RECOVERY_SUCCESS if ok else Outcome.RECOVERY_FAILURE,
                ok,
                evidence,
            )
        return Outcome.UNSAFE_OR_BLOCKED, False, self._evidence()

    @staticmethod
    def _outcome_likelihoods(action_id: str) -> dict[str, dict[str, float]]:
        """Observable outcome model used for the online belief update."""
        faults = ('localization_drift', 'odom_tf_inconsistency', 'amcl_degeneracy')
        if action_id == 'inspect_tf':
            values = {
                'localization_drift': {'diagnostic_support': 0.35, 'diagnostic_conflict': 0.35, 'inconclusive': 0.30},
                'odom_tf_inconsistency': {'diagnostic_support': 0.80, 'diagnostic_conflict': 0.10, 'inconclusive': 0.10},
                'amcl_degeneracy': {'diagnostic_support': 0.25, 'diagnostic_conflict': 0.45, 'inconclusive': 0.30},
            }
        elif action_id == 'slow_observe':
            values = {fault: {'diagnostic_support': 0.15, 'diagnostic_conflict': 0.15, 'inconclusive': 0.70} for fault in faults}
        else:
            values = {fault: {'recovery_success': 0.80, 'recovery_failure': 0.20} for fault in faults}
        return values

    def _reset_episode(self) -> tuple[bool, str]:
        if not self._reset_client.wait_for_service(timeout_sec=5.0):
            return False, 'reset_episode service is unavailable'
        future = self._reset_client.call_async(Trigger.Request())
        deadline = time.monotonic() + 15.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done():
            return False, 'reset_episode service timed out'
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - runtime service failure
            return False, f'reset_episode failed: {exc}'
        return bool(result.success), str(result.message)

    def _run_callback(self, _request, response):
        if not self._episode_lock.acquire(blocking=False):
            response.success = False
            response.message = 'an EACR episode is already running'
            return response
        try:
            self._episode_index += 1
            episode_id = self._episode_index
            result_dir = Path(str(self.get_parameter('result_dir').value))
            recorder = EpisodeRecorder(
                f'eacr_localization_episode_{episode_id:03d}',
                int(self.get_parameter('random_seed').value),
                result_dir,
            )
            reset_success = True
            reset_message = 'reset skipped by parameter'
            if bool(self.get_parameter('reset_before_episode').value):
                reset_success, reset_message = self._reset_episode()
                if not reset_success:
                    response.success = False
                    response.message = reset_message
                    return response
            recorder.record('episode_reset', success=reset_success, message=reset_message)
            injected = self._inject_fault()
            recorder.record('fault_injected', fault=injected)
            time.sleep(float(self.get_parameter('evidence_wait_sec').value))
            evidence_before = self._evidence()
            recorder.record('evidence_collected', phase='before_action', evidence=evidence_before)
            belief, likelihood = self._belief_from_evidence(evidence_before)
            recorder.record('belief_updated', belief=belief, likelihood_by_fault=likelihood)
            context = Context(environment_bin='amcl_fault')
            weights = PolicyWeights(minimum_utility=0.0)
            available = list(self._actions())
            decisions = []
            belief_trace = [{'phase': 'before_action', 'belief': dict(belief)}]
            action_outcome = Outcome.INCONCLUSIVE
            recovery_success = False
            evidence_after = evidence_before
            for _ in range(3):
                decision = choose_action(available, belief, context, self._model, weights)
                decisions.append(decision.as_dict())
                recorder.record('action_decision', decision=decision.as_dict())
                if decision.abstained or decision.selected_action is None:
                    action_outcome = Outcome.UNSAFE_OR_BLOCKED
                    break
                selected = decision.selected_action
                available = [action for action in available if action.action_id != selected]
                action_outcome, recovery_success, evidence_after = self._execute(selected)
                recorder.record(
                    'action_observed',
                    action_id=selected,
                    outcome=action_outcome.value,
                    recovery_success=recovery_success,
                    evidence=evidence_after,
                )
                self._model.update(
                    belief,
                    context,
                    selected,
                    action_outcome,
                    recovery_success=recovery_success if selected == 'relocalize_amcl' else None,
                )
                recorder.record(
                    'experience_updated',
                    action_id=selected,
                    outcome=action_outcome.value,
                    model=self._model.snapshot(),
                )
                likelihoods = self._outcome_likelihoods(selected)
                belief_after = posterior_after_outcome(belief, likelihoods, action_outcome)
                recorder.record(
                    'belief_updated_after_outcome',
                    belief_before=belief,
                    outcome=action_outcome.value,
                    likelihoods=likelihoods,
                    belief_after=belief_after,
                )
                belief = belief_after
                belief_trace.append({'phase': 'after_action', 'action_id': selected, 'outcome': action_outcome.value, 'belief': dict(belief)})
                if recovery_success:
                    break
                if not available:
                    break
            event_path, summary_path = recorder.write({
                'final_outcome': action_outcome.value,
                'verified_recovery': recovery_success,
                'selected_actions': [decision.get('selected_action') for decision in decisions],
            })
            result = {
                'episode_id': episode_id,
                'reset': {'success': reset_success, 'message': reset_message},
                'fault_injection': injected,
                'evidence_before': evidence_before,
                'likelihood_by_fault': likelihood,
                'belief_before_action': belief,
                'decisions': decisions,
                'final_outcome': action_outcome.value,
                'verified_recovery': recovery_success,
                'evidence_after': evidence_after,
                'experience': self._model.snapshot(),
                'belief_trace': belief_trace,
                'belief_changed_after_observation': any(
                    belief_trace[index]['belief'] != belief_trace[index - 1]['belief']
                    for index in range(1, len(belief_trace))
                ),
                'event_record': str(event_path),
                'summary_record': str(summary_path),
            }
            output_path = result_dir / f'eacr_localization_episode_{episode_id:03d}.json'
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            response.success = recovery_success
            response.message = json.dumps(
                {
                    'episode_id': episode_id,
                    'selected_actions': [
                        decision.get('selected_action') for decision in decisions
                    ],
                    'final_outcome': action_outcome.value,
                    'verified_recovery': recovery_success,
                    'result': str(output_path),
                },
                ensure_ascii=False,
            )
            self.get_logger().info(response.message)
            return response
        finally:
            self._episode_lock.release()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = EacrLocalizationLoop()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
