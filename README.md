# EACR Simulation Workspace

Primary platform:

- Ubuntu 24.04
- ROS 2 Jazzy
- Nav2 Jazzy
- Gazebo Harmonic through `ros_gz`
- Nav2 minimal TurtleBot 3 simulation

## Bootstrap

Run from this directory:

```bash
bash scripts/install_ros2_jazzy_ustc.sh
```

The installer uses the USTC ROS 2 mirror because `packages.ros.org` is not
reachable from the current network. It does not install or configure a proxy.

## First acceptance gate

After installation:

```bash
source /opt/ros/jazzy/setup.bash
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False
```

EACR ROS integration starts only after Gazebo, RViz, AMCL, planner, and
controller are all running in the official simulation.

Pure Python `eacr_core` work may proceed independently and must not import
`rclpy` or `rospy`.

## Automated episode smoke run

After building `eacr_sim`, source its isolated overlay:

```bash
source scripts/source_eacr.sh
ros2 launch eacr_sim eacr_episode.launch.py \
  headless:=False \
  use_rviz:=True \
  rviz_gpu:=1
```

The episode manager publishes `/initialpose`, waits for AMCL stability, and
sends a configured `NavigateToPose` goal only when `auto_send_goal` is enabled.
By default it only initializes AMCL and waits for a user-provided goal. It
never subscribes to Gazebo ground truth.

The current primary map is the official `tb3_sandbox` map. Its map and Gazebo
world are passed explicitly to the launch file so later map profiles can be
added without changing the episode manager.

## Goal validation and episode reset

The currently recorded goal is:

```text
x   = 0.7508496046
y   = 1.8354123831
yaw = 1.4751400097 rad
```

The goal was selected in RViz, checked against the occupancy map, and reached
successfully in three reset-and-navigate trials. To repeat the validation:

```bash
source scripts/source_eacr.sh
python3 scripts/validate_goal.py --trials 3
```

The launch also provides a deterministic reset service. It resets Gazebo model
state without resetting simulation time, publishes the AMCL initial pose, and
waits briefly for the next episode:

```bash
source scripts/source_eacr.sh
ros2 service call /reset_episode std_srvs/srv/Trigger '{}'
```

## First localization-fault EACR loop

The launch includes the ROS adapter for the first single-fault loop. It keeps
the decision logic in the ROS-independent `eacr_core` package and exposes:

```bash
source scripts/source_eacr.sh
ros2 service call /inject_amcl_fault std_srvs/srv/Trigger '{}'
ros2 service call /run_eacr_localization_episode std_srvs/srv/Trigger '{}'
```

The second service records evidence, belief, action ranking, recovery
verification, and the updated experience model under `results/`.

## Phase-two fault injection validation

Phase two currently keeps LLM/RAG out of the paper and focuses on reproducible
fault infrastructure. Start the simulation, then run:

```bash
source scripts/source_eacr.sh
python3 scripts/validate_fault_injectors.py
```

The validator checks injection and rollback for localization, costmap, planner,
and control faults and writes `results/phase2_fault_injector_validation.json`.

To run the reset-isolated four-fault matrix inside the live simulation:

```bash
source scripts/source_eacr.sh
ros2 service call /run_phase2_fault_matrix std_srvs/srv/Trigger '{}'
```

This writes `results/phase2_fault_matrix.json` and one event record per episode.

The shared-sequence baseline smoke runner is:

```bash
python3 scripts/run_phase2_experiment.py
```

It validates record reconstruction and fair seed/sequence sharing; its
synthetic outcome output is not a navigation performance result.

RViz is launched with the EACR configuration at
`src/eacr_sim/rviz/eacr_minimal.rviz`. On the current dual-GPU host,
`rviz_gpu:=1` selects the AMD renderer and avoids the previous RViz crash
path. Set `use_rviz:=False` when only the Gazebo/Nav2 simulation is needed.
