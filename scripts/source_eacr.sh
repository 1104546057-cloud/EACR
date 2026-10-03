#!/usr/bin/env bash
# Source ROS2 and the isolated eacr_sim overlay in the current workspace.
set -eo pipefail
workspace_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
source "$workspace_dir/install/local_setup.bash"
export AMENT_PREFIX_PATH="$workspace_dir/install/eacr_core:$workspace_dir/install/eacr_sim:${AMENT_PREFIX_PATH:-}"
export EACR_WS="$workspace_dir"
echo "EACR environment ready: $EACR_WS"
