"""Start Nav2 lifecycle managers only after simulator odometry is available."""

from __future__ import annotations

import rclpy
from nav2_msgs.srv import ManageLifecycleNodes
from nav_msgs.msg import Odometry
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node


class Nav2BringupGate(Node):
    def __init__(self) -> None:
        super().__init__('nav2_bringup_gate')
        group = ReentrantCallbackGroup()
        self._odom_seen = False
        self._started = False
        self._localization = self.create_client(
            ManageLifecycleNodes, '/lifecycle_manager_localization/manage_nodes', callback_group=group)
        self._navigation = self.create_client(
            ManageLifecycleNodes, '/lifecycle_manager_navigation/manage_nodes', callback_group=group)
        self.create_subscription(Odometry, '/odom', self._odom_callback, 10, callback_group=group)
        self._timer = self.create_timer(1.0, self._tick, callback_group=group)
        self.get_logger().info('Nav2 bringup gate waiting for simulator odometry.')

    def _odom_callback(self, _msg: Odometry) -> None:
        self._odom_seen = True

    def _tick(self) -> None:
        if self._started or not self._odom_seen:
            return
        if not self._localization.service_is_ready() or not self._navigation.service_is_ready():
            return
        self._started = True
        request = ManageLifecycleNodes.Request()
        request.command = ManageLifecycleNodes.Request.STARTUP
        future = self._localization.call_async(request)
        future.add_done_callback(self._localization_done)

    def _localization_done(self, future) -> None:
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - runtime ROS failure
            self.get_logger().error(f'Localization lifecycle startup failed: {exc}')
            self._started = False
            return
        if not result.success:
            self.get_logger().error('Localization lifecycle manager rejected startup.')
            self._started = False
            return
        request = ManageLifecycleNodes.Request()
        request.command = ManageLifecycleNodes.Request.STARTUP
        future = self._navigation.call_async(request)
        future.add_done_callback(self._navigation_done)

    def _navigation_done(self, future) -> None:
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover
            self.get_logger().error(f'Navigation lifecycle startup failed: {exc}')
            return
        if result.success:
            self.get_logger().info('Nav2 localization and navigation are active.')
        else:
            self.get_logger().error('Navigation lifecycle manager rejected startup.')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Nav2BringupGate()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
