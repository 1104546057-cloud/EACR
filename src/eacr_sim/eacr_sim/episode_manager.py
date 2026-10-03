import math
from typing import Optional

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseWithCovarianceStamped, Quaternion
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node


def quaternion_from_yaw(yaw: float) -> Quaternion:
    q = Quaternion()
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q


class EpisodeManager(Node):
    """Initialize AMCL and send a deterministic goal for one episode.

    Ground truth is intentionally not subscribed to. It is reserved for the
    simulator and offline evaluation; this node only uses AMCL feedback.
    """

    def __init__(self) -> None:
        super().__init__('episode_manager')
        self.declare_parameter('initial_pose_x', -2.0)
        self.declare_parameter('initial_pose_y', -0.5)
        self.declare_parameter('initial_pose_yaw', 0.0)
        self.declare_parameter('goal_pose_x', 2.0)
        self.declare_parameter('goal_pose_y', 0.5)
        self.declare_parameter('goal_pose_yaw', 0.0)
        self.declare_parameter('auto_send_goal', False)
        self.declare_parameter('publish_period_sec', 1.0)
        self.declare_parameter('stable_samples_required', 5)
        self.declare_parameter('stable_position_tolerance_m', 0.15)
        self.declare_parameter('stable_yaw_tolerance_rad', 0.20)
        self.declare_parameter('navigation_startup_delay_sec', 8.0)
        self.declare_parameter('goal_timeout_sec', 120.0)

        self._initial_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped, '/initialpose', 10)
        self._amcl_sub = self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self._amcl_callback, 10)
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._lifecycle_clients = [
            self.create_client(GetState, '/controller_server/get_state'),
            self.create_client(GetState, '/bt_navigator/get_state'),
        ]
        period = float(self.get_parameter('publish_period_sec').value)
        self._timer = self.create_timer(period, self._publish_initial_pose)
        self._stable_samples = 0
        self._goal_sent = False
        self._stable_since = None
        self._checking_nav2 = False
        self._ready_logged = False
        self._initial_pose_locked = False
        self._last_amcl_pose: Optional[PoseWithCovarianceStamped] = None
        self._started_at = self.get_clock().now()
        self.get_logger().info('Episode manager started; publishing deterministic AMCL initial pose.')

    def _initial_pose_message(self) -> PoseWithCovarianceStamped:
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = float(self.get_parameter('initial_pose_x').value)
        msg.pose.pose.position.y = float(self.get_parameter('initial_pose_y').value)
        msg.pose.pose.orientation = quaternion_from_yaw(
            float(self.get_parameter('initial_pose_yaw').value))
        msg.pose.covariance[0] = 0.25
        msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.10
        return msg

    def _publish_initial_pose(self) -> None:
        if self._goal_sent:
            return
        if not self._initial_pose_locked:
            self._initial_pose_pub.publish(self._initial_pose_message())
        if (self._stable_since is not None and
                (self.get_clock().now() - self._stable_since).nanoseconds >=
                int(float(self.get_parameter('navigation_startup_delay_sec').value) * 1e9)):
            if bool(self.get_parameter('auto_send_goal').value):
                self._check_nav2_active()
            elif not self._ready_logged:
                self._ready_logged = True
                self._initial_pose_locked = True
                self._timer.cancel()
                self.get_logger().info(
                    'AMCL is stable; automatic goal sending is disabled. '
                    'The system is ready for a user-provided goal.')

    def _check_nav2_active(self) -> None:
        if self._goal_sent or self._checking_nav2:
            return
        self._checking_nav2 = True
        if not all(client.service_is_ready() for client in self._lifecycle_clients):
            self._checking_nav2 = False
            return
        requests = [client.call_async(GetState.Request()) for client in self._lifecycle_clients]
        remaining = len(requests)
        states = []

        def collect(future):
            nonlocal remaining
            try:
                states.append(future.result().current_state.id)
            except Exception as exc:  # pragma: no cover - runtime service failure
                self.get_logger().debug(f'Nav2 lifecycle query failed: {exc}')
            remaining -= 1
            if remaining == 0:
                self._checking_nav2 = False
                if len(states) == len(requests) and all(state == 3 for state in states):
                    self._send_goal()

        for request in requests:
            request.add_done_callback(collect)

    def _amcl_callback(self, msg: PoseWithCovarianceStamped) -> None:
        if self._goal_sent:
            return
        if msg.header.frame_id not in ('map', ''):
            return
        self._last_amcl_pose = msg
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        ix = float(self.get_parameter('initial_pose_x').value)
        iy = float(self.get_parameter('initial_pose_y').value)
        distance = math.hypot(x - ix, y - iy)
        tolerance = float(self.get_parameter('stable_position_tolerance_m').value)
        if distance <= tolerance:
            self._stable_samples += 1
            if (self._stable_samples >= int(self.get_parameter('stable_samples_required').value)
                    and self._stable_since is None):
                self._stable_since = self.get_clock().now()
                self._initial_pose_locked = True
        else:
            self._stable_samples = 0
            self._stable_since = None

    def _send_goal(self) -> None:
        if self._goal_sent:
            return
        self._goal_sent = True
        self._timer.cancel()
        if not self._nav_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('navigate_to_pose action server is not available.')
            return
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(self.get_parameter('goal_pose_x').value)
        goal.pose.pose.position.y = float(self.get_parameter('goal_pose_y').value)
        goal.pose.pose.orientation = quaternion_from_yaw(
            float(self.get_parameter('goal_pose_yaw').value))
        self.get_logger().info('AMCL is stable; sending deterministic navigation goal.')
        future = self._nav_client.send_goal_async(goal)
        future.add_done_callback(self._goal_response_callback)

    def _goal_response_callback(self, future) -> None:
        handle = future.result()
        if not handle or not handle.accepted:
            self.get_logger().error('Navigation goal was rejected.')
            return
        self.get_logger().info('Navigation goal accepted; waiting for result.')
        result_future = handle.get_result_async()
        result_future.add_done_callback(self._goal_result_callback)

    def _goal_result_callback(self, future) -> None:
        result = future.result()
        status = result.status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info('Episode navigation succeeded.')
        else:
            self.get_logger().warn(f'Episode navigation finished with status {status}.')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = EpisodeManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
