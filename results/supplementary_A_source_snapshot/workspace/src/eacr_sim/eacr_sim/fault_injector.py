"""Repeatable and rollbackable phase-two fault injection adapters."""

from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Quaternion
from lifecycle_msgs.msg import Transition
from lifecycle_msgs.srv import ChangeState, GetState
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import GetParameters, SetParameters
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger


def quaternion_from_yaw(yaw: float) -> Quaternion:
    msg = Quaternion()
    msg.z = math.sin(yaw / 2.0)
    msg.w = math.cos(yaw / 2.0)
    return msg


class FaultInjector(Node):
    """Expose one service pair per supported fault family.

    Gazebo is used only to inject or roll back a fault. Its ground truth is not
    published to the EACR decision layer.
    """

    def __init__(self) -> None:
        super().__init__('eacr_fault_injector')
        self.declare_parameter('initial_pose_x', -2.0)
        self.declare_parameter('initial_pose_y', -0.5)
        self.declare_parameter('initial_pose_yaw', 0.0)
        self.declare_parameter('localization_offset_x', 0.65)
        self.declare_parameter('localization_offset_y', -0.45)
        self.declare_parameter('localization_offset_yaw', 0.35)
        self.declare_parameter('costmap_obstacle_model', 'eacr_fault_obstacle')
        self.declare_parameter('costmap_obstacle_x', 0.7508496046)
        self.declare_parameter('costmap_obstacle_y', 1.8354123831)
        self.declare_parameter('costmap_obstacle_size_m', 0.80)
        self.declare_parameter('planner_fault_tolerance', -1.0)
        self.declare_parameter('planner_fault_variant', 'invalid_plugin_list')
        self.declare_parameter('controller_fault_min_x_velocity_threshold', 10.0)
        self.declare_parameter('fault_scale', 1.0)
        self.declare_parameter('result_dir', '/home/hu/文档/ChatGPT/论文/eacr_ws/results')
        self.declare_parameter('world_name', 'default')

        group = ReentrantCallbackGroup()
        self._initial_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped, '/initialpose', 10)
        self._fault_service_handles: list = []
        for name, callback in (
            ('/inject_localization_fault', self._inject_localization),
            ('/rollback_localization_fault', self._rollback_localization),
            ('/inject_costmap_fault', self._inject_costmap),
            ('/rollback_costmap_fault', self._rollback_costmap),
            ('/inject_planner_fault', self._inject_planner),
            ('/rollback_planner_fault', self._rollback_planner),
            ('/inject_control_fault', self._inject_control),
            ('/rollback_control_fault', self._rollback_control),
        ):
            self._fault_service_handles.append(self.create_service(Trigger, name, callback, callback_group=group))
        self._planner_get = self.create_client(
            GetParameters, '/planner_server/get_parameters', callback_group=group)
        self._planner_set = self.create_client(
            SetParameters, '/planner_server/set_parameters', callback_group=group)
        self._planner_change_state = self.create_client(
            ChangeState, '/planner_server/change_state', callback_group=group)
        self._planner_get_state = self.create_client(
            GetState, '/planner_server/get_state', callback_group=group)
        self._controller_get = self.create_client(
            GetParameters, '/controller_server/get_parameters', callback_group=group)
        self._controller_set = self.create_client(
            SetParameters, '/controller_server/set_parameters', callback_group=group)
        self._global_costmap_get = self.create_client(
            GetParameters, '/global_costmap/global_costmap/get_parameters', callback_group=group)
        self._global_costmap_set = self.create_client(
            SetParameters, '/global_costmap/global_costmap/set_parameters', callback_group=group)
        self._local_costmap_get = self.create_client(
            GetParameters, '/local_costmap/local_costmap/get_parameters', callback_group=group)
        self._local_costmap_set = self.create_client(
            SetParameters, '/local_costmap/local_costmap/set_parameters', callback_group=group)
        self._original_parameters: dict[str, float] = {}
        self._original_costmap_parameters: dict[str, float] = {}
        self._original_planner_plugins: list[str] | None = None
        self.get_logger().info(
            'Fault injector ready: localization, costmap, planner, control inject/rollback pairs.')

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

    def _publish_pose(self, x: float, y: float, yaw: float, repeats: int = 4) -> None:
        msg = self._pose_message(x, y, yaw)
        for _ in range(repeats):
            self._initial_pose_pub.publish(msg)
            time.sleep(0.10)

    def _event(self, family: str, operation: str, success: bool, detail: str) -> None:
        result_dir = Path(str(self.get_parameter('result_dir').value))
        result_dir.mkdir(parents=True, exist_ok=True)
        path = result_dir / 'phase2_fault_injector.events.jsonl'
        event = {
            'time_unix': time.time(),
            'family': family,
            'operation': operation,
            'success': success,
            'detail': detail,
        }
        with path.open('a') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')

    def _respond(self, response, family: str, operation: str, success: bool, detail: str):
        response.success = success
        response.message = detail
        self._event(family, operation, success, detail)
        if success:
            self.get_logger().info(f'{family} {operation}: {detail}')
        else:
            self.get_logger().error(f'{family} {operation}: {detail}')
        return response

    def _inject_localization(self, _request, response):
        x = float(self.get_parameter('initial_pose_x').value)
        y = float(self.get_parameter('initial_pose_y').value)
        yaw = float(self.get_parameter('initial_pose_yaw').value)
        scale = float(self.get_parameter('fault_scale').value)
        dx = float(self.get_parameter('localization_offset_x').value) * scale
        dy = float(self.get_parameter('localization_offset_y').value) * scale
        dyaw = float(self.get_parameter('localization_offset_yaw').value) * scale
        self._publish_pose(x + dx, y + dy, yaw + dyaw)
        return self._respond(
            response,
            'localization',
            'inject',
            True,
            json.dumps({'offset_x': dx, 'offset_y': dy, 'offset_yaw': dyaw}),
        )

    def _rollback_localization(self, _request, response):
        x = float(self.get_parameter('initial_pose_x').value)
        y = float(self.get_parameter('initial_pose_y').value)
        yaw = float(self.get_parameter('initial_pose_yaw').value)
        self._publish_pose(x, y, yaw)
        return self._respond(response, 'localization', 'rollback', True, 'initial pose restored')

    def _gz_service(self, service: str, request_type: str, response_type: str, request: str) -> tuple[bool, str]:
        command = [
            'gz', 'service', '-s', service,
            '--reqtype', request_type,
            '--reptype', response_type,
            '--timeout', '3000',
            '--req', request,
        ]
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=6.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        output = (completed.stdout + completed.stderr).strip()
        return completed.returncode == 0 and 'data: true' in output, output or str(completed.returncode)

    def _inject_costmap(self, _request, response):
        # A costmap parameter fault is deterministic and observable by Nav2;
        # relying only on a Gazebo model does not guarantee sensor marking.
        values = []
        for key, getter, setter in (
            ('global', self._global_costmap_get, self._global_costmap_set),
            ('local', self._local_costmap_get, self._local_costmap_set),
        ):
            ok, original, detail = self._get_parameter(getter, 'footprint_padding')
            if not ok or original is None:
                return self._respond(response, 'costmap', 'inject', False, f'{key}: {detail}')
            scale = float(self.get_parameter('fault_scale').value)
            changed, reason = self._set_parameter(
                setter, 'footprint_padding', max(0.6, 2.0 * scale))
            if not changed:
                return self._respond(response, 'costmap', 'inject', False, f'{key}: {reason}')
            self._original_costmap_parameters[key] = original
            values.append(f'{key}: {detail} -> footprint_padding=2.0 ({reason})')
        return self._respond(response, 'costmap', 'inject', True, '; '.join(values))

    def _rollback_costmap(self, _request, response):
        details = []
        for key, setter in (
            ('global', self._global_costmap_set),
            ('local', self._local_costmap_set),
        ):
            if key not in self._original_costmap_parameters:
                return self._respond(response, 'costmap', 'rollback', False, f'no saved parameter for {key}')
            ok, reason = self._set_parameter(
                setter, 'footprint_padding', self._original_costmap_parameters[key])
            if not ok:
                return self._respond(response, 'costmap', 'rollback', False, f'{key}: {reason}')
            details.append(f'{key}: restored {self._original_costmap_parameters[key]}')
        self._original_costmap_parameters.clear()
        return self._respond(response, 'costmap', 'rollback', True, '; '.join(details))

    def _get_parameter(self, client, name: str) -> tuple[bool, float | None, str]:
        if not client.wait_for_service(timeout_sec=5.0):
            return False, None, 'get_parameters service unavailable'
        request = GetParameters.Request()
        request.names = [name]
        future = client.call_async(request)
        deadline = time.monotonic() + 10.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done():
            return False, None, 'get_parameters timed out'
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - runtime service failure
            return False, None, str(exc)
        if not result.values:
            return False, None, f'parameter not found: {name}'
        value = result.values[0]
        if value.type == ParameterType.PARAMETER_DOUBLE:
            return True, float(value.double_value), f'{name}={value.double_value}'
        if value.type == ParameterType.PARAMETER_INTEGER:
            return True, float(value.integer_value), f'{name}={value.integer_value}'
        return False, None, f'parameter is not numeric: {name}'

    def _get_string_array(self, client, name: str) -> tuple[bool, list[str] | None, str]:
        if not client.wait_for_service(timeout_sec=5.0):
            return False, None, 'get_parameters service unavailable'
        request = GetParameters.Request()
        request.names = [name]
        future = client.call_async(request)
        deadline = time.monotonic() + 10.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done() or future.result() is None or not future.result().values:
            return False, None, f'parameter not found: {name}'
        value = future.result().values[0]
        if value.type != ParameterType.PARAMETER_STRING_ARRAY:
            return False, None, f'parameter is not a string array: {name}'
        values = [str(item) for item in value.string_array_value]
        return True, values, f'{name}={values}'

    def _set_string_array(self, client, name: str, values: list[str]) -> tuple[bool, str]:
        if not client.wait_for_service(timeout_sec=5.0):
            return False, 'set_parameters service unavailable'
        parameter = Parameter()
        parameter.name = name
        parameter.value = ParameterValue(
            type=ParameterType.PARAMETER_STRING_ARRAY,
            string_array_value=values,
        )
        request = SetParameters.Request()
        request.parameters = [parameter]
        future = client.call_async(request)
        deadline = time.monotonic() + 10.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done() or future.result() is None or not future.result().results:
            return False, 'set_parameters failed'
        return bool(future.result().results[0].successful), str(future.result().results[0].reason)

    def _set_parameter(self, client, name: str, value: float) -> tuple[bool, str]:
        if not client.wait_for_service(timeout_sec=5.0):
            return False, 'set_parameters service unavailable'
        parameter = Parameter()
        parameter.name = name
        parameter.value = ParameterValue(
            type=ParameterType.PARAMETER_DOUBLE,
            double_value=float(value),
        )
        request = SetParameters.Request()
        request.parameters = [parameter]
        future = client.call_async(request)
        deadline = time.monotonic() + 10.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done():
            return False, 'set_parameters timed out'
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - runtime service failure
            return False, str(exc)
        if not result.results:
            return False, 'set_parameters returned no result'
        return bool(result.results[0].successful), str(result.results[0].reason)

    def _inject_parameter_fault(self, family: str, client_get, client_set, name: str, value: float) -> tuple[bool, str]:
        if family in self._original_parameters:
            return False, f'{family} fault already active; rollback before reinjection'
        ok, original, detail = self._get_parameter(client_get, name)
        if not ok or original is None:
            return False, detail
        ok, reason = self._set_parameter(client_set, name, value)
        if not ok:
            return False, f'{name}: set rejected; {reason}'
        verified, observed, readback = self._get_parameter(client_get, name)
        if not verified or observed is None or not math.isclose(observed, value, abs_tol=1e-6):
            self._set_parameter(client_set, name, original)
            return False, f'{name}: readback mismatch after set: {readback}; expected {value}'
        self._original_parameters[family] = original
        return True, f'{name}: {detail} -> {readback}'

    def _rollback_parameter_fault(self, family: str, client_get, client_set, name: str) -> tuple[bool, str]:
        if family not in self._original_parameters:
            return False, f'no saved parameter for {family}'
        original = self._original_parameters[family]
        ok, reason = self._set_parameter(client_set, name, original)
        if not ok:
            return False, f'{name}: restore rejected; {reason}'
        verified, observed, readback = self._get_parameter(client_get, name)
        if not verified or observed is None or not math.isclose(observed, original, abs_tol=1e-6):
            return False, f'{name}: rollback readback mismatch: {readback}; expected {original}'
        self._original_parameters.pop(family, None)
        return True, f'{name}: restored {readback}'

    def _inject_planner(self, _request, response):
        if str(self.get_parameter('planner_fault_variant').value) == 'deactivate_lifecycle':
            ok, detail = self._change_planner_state(Transition.TRANSITION_DEACTIVATE, 2)
            return self._respond(response, 'planner', 'inject', ok, detail)
        ok, original, detail = self._get_string_array(self._planner_get, 'planner_plugins')
        if not ok or original is None:
            return self._respond(response, 'planner', 'inject', False, detail)
        changed, reason = self._set_string_array(self._planner_set, 'planner_plugins', ['EacrInvalidPlanner'])
        if not changed:
            return self._respond(response, 'planner', 'inject', False, reason)
        self._original_planner_plugins = original
        return self._respond(response, 'planner', 'inject', True, f'{detail} -> planner_plugins=[EacrInvalidPlanner]')

    def _rollback_planner(self, _request, response):
        if str(self.get_parameter('planner_fault_variant').value) == 'deactivate_lifecycle':
            ok, detail = self._change_planner_state(Transition.TRANSITION_ACTIVATE, 3)
            return self._respond(response, 'planner', 'rollback', ok, detail)
        if self._original_planner_plugins is None:
            return self._respond(response, 'planner', 'rollback', False, 'no saved planner_plugins')
        original = self._original_planner_plugins
        ok, reason = self._set_string_array(self._planner_set, 'planner_plugins', original)
        if ok:
            self._original_planner_plugins = None
        return self._respond(response, 'planner', 'rollback', ok, f'planner_plugins restored {original}; {reason}')

    def _change_planner_state(self, transition_id: int, expected_state: int) -> tuple[bool, str]:
        if not self._planner_change_state.wait_for_service(timeout_sec=5.0):
            return False, 'planner lifecycle change_state service unavailable'
        request = ChangeState.Request()
        request.transition.id = transition_id
        future = self._planner_change_state.call_async(request)
        deadline = time.monotonic() + 10.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done() or future.result() is None or not future.result().success:
            return False, 'planner lifecycle transition failed'
        if not self._planner_get_state.wait_for_service(timeout_sec=3.0):
            return False, 'planner lifecycle readback unavailable'
        state_future = self._planner_get_state.call_async(GetState.Request())
        deadline = time.monotonic() + 5.0
        while not state_future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not state_future.done() or state_future.result() is None:
            return False, 'planner lifecycle readback timed out'
        state = int(state_future.result().current_state.id)
        return state == expected_state, f'planner lifecycle state={state}, expected={expected_state}'

    def _inject_control(self, _request, response):
        scale = float(self.get_parameter('fault_scale').value)
        value = float(self.get_parameter('controller_fault_min_x_velocity_threshold').value) * scale
        ok, detail = self._inject_parameter_fault(
            'control', self._controller_get, self._controller_set,
            'min_x_velocity_threshold', value)
        return self._respond(response, 'control', 'inject', ok, detail)

    def _rollback_control(self, _request, response):
        ok, detail = self._rollback_parameter_fault(
            'control', self._controller_get, self._controller_set, 'min_x_velocity_threshold')
        return self._respond(response, 'control', 'rollback', ok, detail)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FaultInjector()
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
