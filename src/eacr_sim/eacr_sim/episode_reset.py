import math
import subprocess
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from rclpy.node import Node
from std_srvs.srv import Trigger


def quaternion_from_yaw(yaw: float):
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)


class EpisodeReset(Node):
    """Reset the Gazebo robot and AMCL state to the deterministic episode start."""

    def __init__(self) -> None:
        super().__init__('episode_reset')
        self.declare_parameter('initial_pose_x', -2.0)
        self.declare_parameter('initial_pose_y', -0.5)
        self.declare_parameter('initial_pose_yaw', 0.0)
        self.declare_parameter('robot_model_name', 'turtlebot3_waffle')
        self.declare_parameter('robot_z', 0.01)
        self.declare_parameter('settle_sec', 2.0)
        self.declare_parameter('use_world_model_reset', True)

        self._initial_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped, '/initialpose', 10)
        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self._reset_srv = self.create_service(
            Trigger, '/reset_episode', self._reset_callback)
        self.get_logger().info(
            'Episode reset ready: call /reset_episode to restore the deterministic start pose.')

    def _set_gazebo_pose(self) -> tuple[bool, str]:
        x = float(self.get_parameter('initial_pose_x').value)
        y = float(self.get_parameter('initial_pose_y').value)
        yaw = float(self.get_parameter('initial_pose_yaw').value)
        z = float(self.get_parameter('robot_z').value)
        model = str(self.get_parameter('robot_model_name').value)
        qz, qw = quaternion_from_yaw(yaw)
        request = (
            f'name: "{model}", '
            f'position: {{x: {x}, y: {y}, z: {z}}}, '
            f'orientation: {{x: 0.0, y: 0.0, z: {qz}, w: {qw}}}'
        )
        command = [
            'gz', 'service', '-s', '/world/default/set_pose',
            '--reqtype', 'gz.msgs.Pose',
            '--reptype', 'gz.msgs.Boolean',
            '--timeout', '2000',
            '--req', request,
        ]
        try:
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True, timeout=5.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f'Gazebo set_pose failed: {exc}'
        output = (completed.stdout + completed.stderr).strip()
        if completed.returncode != 0 or 'data: true' not in output:
            return False, f'Gazebo set_pose failed: {output or completed.returncode}'
        return True, output

    def _reset_world_models(self) -> tuple[bool, str]:
        """Reset model state and simulator plugins without resetting simulation time."""
        command = [
            'gz', 'service', '-s', '/world/default/control',
            '--reqtype', 'gz.msgs.WorldControl',
            '--reptype', 'gz.msgs.Boolean',
            '--timeout', '3000',
            '--req', 'reset: {model_only: true}',
        ]
        try:
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True, timeout=6.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f'Gazebo model reset failed: {exc}'
        output = (completed.stdout + completed.stderr).strip()
        if completed.returncode != 0 or 'data: true' not in output:
            return False, f'Gazebo model reset failed: {output or completed.returncode}'
        return True, output

    def _publish_zero_velocity(self) -> None:
        zero = Twist()
        for _ in range(3):
            self._cmd_vel_pub.publish(zero)
            time.sleep(0.05)

    def _publish_initial_pose(self) -> None:
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = float(self.get_parameter('initial_pose_x').value)
        msg.pose.pose.position.y = float(self.get_parameter('initial_pose_y').value)
        qz, qw = quaternion_from_yaw(
            float(self.get_parameter('initial_pose_yaw').value))
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw
        msg.pose.covariance[0] = 0.25
        msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.10
        self._initial_pose_pub.publish(msg)

    def _reset_callback(self, _request, response):
        if bool(self.get_parameter('use_world_model_reset').value):
            ok, detail = self._reset_world_models()
        else:
            ok, detail = self._set_gazebo_pose()
        if not ok:
            response.success = False
            response.message = detail
            self.get_logger().error(detail)
            return response

        self._publish_zero_velocity()
        self._publish_initial_pose()
        settle = float(self.get_parameter('settle_sec').value)
        if settle > 0.0:
            time.sleep(settle)
        response.success = True
        response.message = (
            'Episode reset to '
            f"({self.get_parameter('initial_pose_x').value}, "
            f"{self.get_parameter('initial_pose_y').value}, "
            f"{self.get_parameter('initial_pose_yaw').value}).")
        self.get_logger().info(response.message)
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = EpisodeReset()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
