#!/usr/bin/env python3
"""Repeat normal navigation to the configured goal with an episode reset."""

import argparse
import math
import time

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseWithCovarianceStamped, Quaternion
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_srvs.srv import Trigger


def quaternion_from_yaw(yaw: float) -> Quaternion:
    q = Quaternion()
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q


class GoalValidator(Node):
    def __init__(self, x: float, y: float, yaw: float) -> None:
        super().__init__('eacr_goal_validator')
        self.x = x
        self.y = y
        self.yaw = yaw
        self._amcl_pose = None
        self._amcl_sub = self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self._amcl_callback, 10)
        self.reset_client = self.create_client(Trigger, '/reset_episode')
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

    def _amcl_callback(self, msg: PoseWithCovarianceStamped) -> None:
        self._amcl_pose = msg

    def _wait_future(self, future, timeout_sec: float) -> bool:
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)
        return future.done()

    def reset_and_wait_localization(self) -> tuple[bool, str]:
        if not self.reset_client.wait_for_service(timeout_sec=5.0):
            return False, 'reset service unavailable'
        future = self.reset_client.call_async(Trigger.Request())
        if not self._wait_future(future, 10.0):
            return False, 'reset service timed out'
        response = future.result()
        if response is None or not response.success:
            return False, response.message if response else 'reset failed'

        stable = 0
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if self._amcl_pose is None:
                continue
            p = self._amcl_pose.pose.pose.position
            distance = math.hypot(p.x + 2.0, p.y + 0.5)
            stable = stable + 1 if distance <= 0.25 else 0
            if stable >= 5:
                return True, 'AMCL stable at reset pose'
        return False, 'AMCL did not stabilize at reset pose'

    def navigate_once(self, timeout_sec: float) -> tuple[bool, int, float]:
        if not self.nav_client.wait_for_server(timeout_sec=10.0):
            return False, GoalStatus.STATUS_UNKNOWN, 0.0
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = self.x
        goal.pose.pose.position.y = self.y
        goal.pose.pose.orientation = quaternion_from_yaw(self.yaw)
        started = time.monotonic()
        send_future = self.nav_client.send_goal_async(goal)
        if not self._wait_future(send_future, 10.0):
            return False, GoalStatus.STATUS_UNKNOWN, time.monotonic() - started
        handle = send_future.result()
        if handle is None or not handle.accepted:
            return False, GoalStatus.STATUS_UNKNOWN, time.monotonic() - started
        result_future = handle.get_result_async()
        if not self._wait_future(result_future, timeout_sec):
            handle.cancel_goal_async()
            return False, GoalStatus.STATUS_UNKNOWN, time.monotonic() - started
        status = result_future.result().status
        return status == GoalStatus.STATUS_SUCCEEDED, status, time.monotonic() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--x', type=float, default=0.7508496046)
    parser.add_argument('--y', type=float, default=1.8354123831)
    parser.add_argument('--yaw', type=float, default=1.4751400097)
    parser.add_argument('--timeout', type=float, default=120.0)
    args = parser.parse_args()

    rclpy.init()
    node = GoalValidator(args.x, args.y, args.yaw)
    passed = 0
    try:
        for trial in range(1, args.trials + 1):
            reset_ok, reset_msg = node.reset_and_wait_localization()
            if not reset_ok:
                print(f'trial={trial} reset=FAIL detail={reset_msg}', flush=True)
                continue
            ok, status, duration = node.navigate_once(args.timeout)
            print(
                f'trial={trial} reset=OK navigation={"PASS" if ok else "FAIL"} '
                f'status={status} duration_sec={duration:.2f}',
                flush=True,
            )
            passed += int(ok)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    print(f'summary passed={passed} total={args.trials}', flush=True)
    return 0 if passed == args.trials else 1


if __name__ == '__main__':
    raise SystemExit(main())
