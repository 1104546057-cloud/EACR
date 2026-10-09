from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    SetLaunchConfiguration,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    headless = LaunchConfiguration('headless')
    use_rviz = LaunchConfiguration('use_rviz')
    rviz_gpu = LaunchConfiguration('rviz_gpu')
    rviz_config = LaunchConfiguration('rviz_config')
    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart = LaunchConfiguration('autostart')
    map_file = LaunchConfiguration('map')
    world_file = LaunchConfiguration('world')
    episode_config = LaunchConfiguration('episode_config')
    fault_scale = LaunchConfiguration('fault_scale')
    return LaunchDescription([
        DeclareLaunchArgument('headless', default_value='False'),
        DeclareLaunchArgument('use_rviz', default_value='True'),
        DeclareLaunchArgument('use_sim_time', default_value='True'),
        DeclareLaunchArgument('autostart', default_value='False'),
        DeclareLaunchArgument('fault_scale', default_value='1.0'),
        DeclareLaunchArgument(
            'rviz_gpu',
            default_value='1',
            description='DRI_PRIME renderer index for RViz; 1 selects the AMD renderer on this host.',
        ),
        DeclareLaunchArgument(
            'rviz_config',
            default_value=PathJoinSubstitution([
                FindPackageShare('eacr_sim'), 'rviz', 'eacr_minimal.rviz'
            ]),
            description='RViz display configuration file.',
        ),
        DeclareLaunchArgument(
            'map',
            default_value='/opt/ros/jazzy/share/nav2_bringup/maps/tb3_sandbox.yaml'),
        DeclareLaunchArgument(
            'world',
            default_value='/opt/ros/jazzy/share/nav2_minimal_tb3_sim/worlds/tb3_sandbox.sdf.xacro'),
        DeclareLaunchArgument(
            'episode_config',
            default_value=PathJoinSubstitution([
                FindPackageShare('eacr_sim'), 'config', 'episode.yaml'
            ])),
        GroupAction(
            scoped=True,
            actions=[
                # The included Nav2 launch file uses the same argument name.
                # Keep its RViz disabled while preserving this launch file's
                # use_rviz value for the renderer-selected node below.
                SetLaunchConfiguration('use_rviz', 'False'),
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(PathJoinSubstitution([
                        FindPackageShare('nav2_bringup'),
                        'launch', 'tb3_simulation_launch.py'
                    ])),
                    launch_arguments={
                        'headless': headless,
                        'use_rviz': 'False',
                        'use_sim_time': use_sim_time,
                        'autostart': autostart,
                        'map': map_file,
                        'world': world_file,
                    }.items(),
                ),
            ],
        ),
        Node(
            package='eacr_sim',
            executable='nav2_bringup_gate',
            name='nav2_bringup_gate',
            output='screen',
        ),
        Node(
            condition=IfCondition(use_rviz),
            package='rviz2',
            executable='rviz2',
            arguments=['-d', rviz_config],
            output='screen',
            parameters=[{'use_sim_time': use_sim_time}],
            additional_env={'DRI_PRIME': rviz_gpu},
        ),
        Node(
            package='eacr_sim',
            executable='episode_manager',
            name='episode_manager',
            output='screen',
            parameters=[episode_config],
        ),
        Node(
            package='eacr_sim',
            executable='episode_reset',
            name='episode_reset',
            output='screen',
            parameters=[episode_config],
        ),
        Node(
            package='eacr_sim',
            executable='eacr_localization_loop',
            name='eacr_localization_loop',
            output='screen',
            parameters=[episode_config],
        ),
        Node(
            package='eacr_sim',
            executable='fault_injector',
            name='fault_injector',
            output='screen',
            parameters=[episode_config, {'fault_scale': fault_scale}],
        ),
        Node(
            package='eacr_sim',
            executable='phase2_episode_runner',
            name='phase2_episode_runner',
            output='screen',
            parameters=[episode_config],
        ),
    ])
