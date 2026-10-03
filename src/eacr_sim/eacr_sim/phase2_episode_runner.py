"""ROS runner for a reset-isolated phase-two fault matrix."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Optional

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger

from eacr_core.records import EpisodeRecorder
from eacr_core.scenario import DEFAULT_FAULT_SPECS, FaultSequence


class Phase2EpisodeRunner(Node):
    """Run all phase-two fault families with reset isolation and records."""

    def __init__(self) -> None:
        super().__init__('phase2_episode_runner')
        self.declare_parameter('random_seed', 20260926)
        self.declare_parameter('evidence_wait_sec', 1.0)
        self.declare_parameter('result_dir', '/home/hu/文档/ChatGPT/论文/eacr_ws/results')
        self.declare_parameter('costmap_obstacle_x', 0.7508496046)
        self.declare_parameter('costmap_obstacle_y', 1.8354123831)
        group = ReentrantCallbackGroup()
        self._reset = self.create_client(Trigger, '/reset_episode', callback_group=group)
        self._fault_services = {
            'localization': (
                self.create_client(Trigger, '/inject_localization_fault', callback_group=group),
                self.create_client(Trigger, '/rollback_localization_fault', callback_group=group),
            ),
            'costmap': (
                self.create_client(Trigger, '/inject_costmap_fault', callback_group=group),
                self.create_client(Trigger, '/rollback_costmap_fault', callback_group=group),
            ),
            'planner': (
                self.create_client(Trigger, '/inject_planner_fault', callback_group=group),
                self.create_client(Trigger, '/rollback_planner_fault', callback_group=group),
            ),
            'control': (
                self.create_client(Trigger, '/inject_control_fault', callback_group=group),
                self.create_client(Trigger, '/rollback_control_fault', callback_group=group),
            ),
        }
        self._amcl: Optional[PoseWithCovarianceStamped] = None
        self._odom: Optional[Odometry] = None
        self._global_costmap: Optional[OccupancyGrid] = None
        self._local_costmap: Optional[OccupancyGrid] = None
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self._amcl_callback, 10, callback_group=group)
        self.create_subscription(Odometry, '/odom', self._odom_callback, 10, callback_group=group)
        self.create_subscription(OccupancyGrid, '/global_costmap/costmap', self._global_costmap_callback, 10, callback_group=group)
        self.create_subscription(OccupancyGrid, '/local_costmap/costmap', self._local_costmap_callback, 10, callback_group=group)
        self._run = self.create_service(
            Trigger, '/run_phase2_fault_matrix', self._run_callback, callback_group=group)
        self.get_logger().info('Phase-two episode runner ready: /run_phase2_fault_matrix')

    def _amcl_callback(self, msg: PoseWithCovarianceStamped) -> None:
        self._amcl = msg

    def _odom_callback(self, msg: Odometry) -> None:
        self._odom = msg

    def _global_costmap_callback(self, msg: OccupancyGrid) -> None:
        self._global_costmap = msg

    def _local_costmap_callback(self, msg: OccupancyGrid) -> None:
        self._local_costmap = msg

    @staticmethod
    def _occupied_count(msg: Optional[OccupancyGrid]) -> Optional[int]:
        if msg is None:
            return None
        return sum(1 for value in msg.data if value >= 50)

    @staticmethod
    def _target_occupied(msg: Optional[OccupancyGrid], x: float, y: float) -> Optional[bool]:
        if msg is None or msg.info.resolution <= 0.0:
            return None
        col = int((x - msg.info.origin.position.x) / msg.info.resolution)
        row = int((y - msg.info.origin.position.y) / msg.info.resolution)
        if col < 0 or row < 0 or col >= msg.info.width or row >= msg.info.height:
            return None
        radius = 2
        values = []
        for yy in range(max(0, row - radius), min(msg.info.height, row + radius + 1)):
            for xx in range(max(0, col - radius), min(msg.info.width, col + radius + 1)):
                values.append(msg.data[yy * msg.info.width + xx])
        return any(value >= 50 for value in values)

    def _evidence(self) -> dict:
        result = {
            'amcl_available': self._amcl is not None,
            'odom_available': self._odom is not None,
            'amcl_covariance_xy': None,
            'odom_speed_mps': None,
            'amcl_xy': None,
            'global_costmap_occupied': self._occupied_count(self._global_costmap),
            'local_costmap_occupied': self._occupied_count(self._local_costmap),
            'global_costmap_target_occupied': self._target_occupied(
                self._global_costmap,
                float(self.get_parameter('costmap_obstacle_x').value),
                float(self.get_parameter('costmap_obstacle_y').value),
            ),
            'local_costmap_target_occupied': self._target_occupied(
                self._local_costmap,
                float(self.get_parameter('costmap_obstacle_x').value),
                float(self.get_parameter('costmap_obstacle_y').value),
            ),
        }
        if self._amcl is not None:
            self._last_amcl_xy = (float(self._amcl.pose.pose.position.x), float(self._amcl.pose.pose.position.y))
            result['amcl_xy'] = list(self._last_amcl_xy)
            result['amcl_covariance_xy'] = float(
                self._amcl.pose.covariance[0] + self._amcl.pose.covariance[7])
        if self._odom is not None:
            twist = self._odom.twist.twist
            result['odom_speed_mps'] = float(math.hypot(twist.linear.x, twist.linear.y))
        return result

    def _call(self, client, label: str) -> tuple[bool, str]:
        if not client.wait_for_service(timeout_sec=8.0):
            return False, f'{label}: service unavailable'
        future = client.call_async(Trigger.Request())
        deadline = time.monotonic() + 30.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done():
            return False, f'{label}: timeout'
        try:
            response = future.result()
        except Exception as exc:  # pragma: no cover - runtime service failure
            return False, f'{label}: {exc}'
        return bool(response.success), str(response.message)

    def _run_callback(self, _request, response):
        seed = int(self.get_parameter('random_seed').value)
        sequence = FaultSequence.from_specs(DEFAULT_FAULT_SPECS, seed=seed, episode_prefix='phase2')
        result_dir = Path(str(self.get_parameter('result_dir').value))
        matrix = []
        for event in sequence.events:
            recorder = EpisodeRecorder(event.episode_id, seed, result_dir)
            reset_ok, reset_detail = self._call(self._reset, 'reset')
            recorder.record('episode_reset', success=reset_ok, message=reset_detail)
            if not reset_ok:
                matrix.append({'episode_id': event.episode_id, 'fault_family': event.fault.family.value, 'reset_success': False})
                continue
            time.sleep(float(self.get_parameter('evidence_wait_sec').value))
            before = self._evidence()
            recorder.record('evidence_collected', phase='before_fault', evidence=before)
            inject_client, rollback_client = self._fault_services[event.fault.family.value]
            inject_ok, inject_detail = self._call(inject_client, 'inject')
            recorder.record('fault_injected', family=event.fault.family.value, success=inject_ok, detail=inject_detail)
            time.sleep(float(self.get_parameter('evidence_wait_sec').value))
            during = self._evidence()
            effect_observed = None
            effect_reason = 'not_checked'
            if event.fault.family.value == 'localization' and before['amcl_xy'] and during['amcl_xy']:
                effect_observed = math.dist(before['amcl_xy'], during['amcl_xy']) > 0.20
                effect_reason = 'amcl_displacement_over_threshold'
            elif event.fault.family.value == 'costmap':
                global_delta = None
                local_delta = None
                if before['global_costmap_occupied'] is not None and during['global_costmap_occupied'] is not None:
                    global_delta = during['global_costmap_occupied'] - before['global_costmap_occupied']
                if before['local_costmap_occupied'] is not None and during['local_costmap_occupied'] is not None:
                    local_delta = during['local_costmap_occupied'] - before['local_costmap_occupied']
                before_target = before['global_costmap_target_occupied'] or before['local_costmap_target_occupied']
                during_target = during['global_costmap_target_occupied'] or during['local_costmap_target_occupied']
                effect_observed = bool(inject_ok and during_target and not before_target)
                effect_reason = 'target_cell_transition_free_to_occupied'
            elif event.fault.family.value in ('planner', 'control'):
                # The injector includes a parameter readback in its response.  A
                # successful readback is the observable effect for this stage;
                # navigation outcome testing remains a stage-three experiment.
                # Parameter readback proves configuration mutation only.  It
                # is intentionally not accepted as a planner/controller
                # behavior effect; that requires a NavigateToPose trial.
                effect_observed = False
                effect_reason = 'requires_navigation_action_outcome'
            recorder.record('evidence_collected', phase='during_fault', evidence=during)
            recorder.record('fault_effect_check', observed=effect_observed, reason=effect_reason)
            rollback_ok, rollback_detail = self._call(rollback_client, 'rollback') if inject_ok else (False, 'inject failed')
            recorder.record('fault_rollback', success=rollback_ok, detail=rollback_detail)
            time.sleep(float(self.get_parameter('evidence_wait_sec').value))
            after = self._evidence()
            recorder.record('evidence_collected', phase='after_rollback', evidence=after)
            event_path, summary_path = recorder.write({
                'fault_family': event.fault.family.value,
                'inject_success': inject_ok,
                'rollback_success': rollback_ok,
                'effect_observed': effect_observed,
                'effect_reason': effect_reason,
            })
            matrix.append({
                'episode_id': event.episode_id,
                'fault_family': event.fault.family.value,
                'fault_id': event.fault.fault_id,
                'reset_success': reset_ok,
                'inject_success': inject_ok,
                'rollback_success': rollback_ok,
                'effect_observed': effect_observed,
                'effect_reason': effect_reason,
                'events': str(event_path),
                'summary': str(summary_path),
            })
        result = {
            'seed': seed,
            'sequence': sequence.as_dict(),
            'episodes': matrix,
            'acceptance': {
                'all_resets_succeeded': all(item.get('reset_success', False) for item in matrix),
                'all_injections_succeeded': all(item.get('inject_success', False) for item in matrix),
                'all_rollbacks_succeeded': all(item.get('rollback_success', False) for item in matrix),
                'all_effect_checks_completed': all(item.get('effect_observed') is not None for item in matrix),
                'all_effect_checks_passed': all(item.get('effect_observed') is True for item in matrix),
                'decision_traces_reconstructable': False,
            },
        }
        output_path = result_dir / 'phase2_fault_matrix.json'
        result_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        response.success = all(result['acceptance'].values())
        response.message = json.dumps({'result': str(output_path), 'acceptance': result['acceptance']}, ensure_ascii=False)
        self.get_logger().info(response.message)
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Phase2EpisodeRunner()
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
