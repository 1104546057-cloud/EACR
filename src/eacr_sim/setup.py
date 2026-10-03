from setuptools import setup

package_name = 'eacr_sim'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/eacr_episode.launch.py']),
        ('share/' + package_name + '/config', ['config/episode.yaml']),
        ('share/' + package_name + '/config', ['config/map_profiles.yaml']),
        ('share/' + package_name + '/rviz', ['rviz/eacr_minimal.rviz']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={
        'console_scripts': [
            'episode_manager = eacr_sim.episode_manager:main',
            'episode_reset = eacr_sim.episode_reset:main',
            'eacr_localization_loop = eacr_sim.eacr_localization_loop:main',
            'fault_injector = eacr_sim.fault_injector:main',
            'phase2_episode_runner = eacr_sim.phase2_episode_runner:main',
            'phase3_gazebo_runner = eacr_sim.phase3_gazebo_runner:main',
            'nav2_bringup_gate = eacr_sim.nav2_bringup_gate:main',
        ],
    },
)
