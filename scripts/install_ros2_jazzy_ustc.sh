#!/usr/bin/env bash
set -euo pipefail

ROS_DISTRO_NAME="jazzy"
ROS_APT_MIRROR="https://mirrors.ustc.edu.cn/ros2/ubuntu"
ROS_KEY_URL="https://raw.githubusercontent.com/ros/rosdistro/master/ros.key"
ROS_KEYRING="/usr/share/keyrings/ros-archive-keyring.gpg"
ROS_SOURCE_FILE="/etc/apt/sources.list.d/ros2.list"

if [[ "$(. /etc/os-release && printf '%s' "$VERSION_CODENAME")" != "noble" ]]; then
  echo "This installer requires Ubuntu 24.04 (noble)." >&2
  exit 1
fi

if [[ "$(dpkg --print-architecture)" != "amd64" ]]; then
  echo "This installer currently targets amd64." >&2
  exit 1
fi

echo "Installing prerequisites..."
sudo apt-get update
sudo apt-get install -y curl gnupg2 software-properties-common
sudo add-apt-repository -y universe

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

echo "Installing the ROS repository signing key..."
curl -4 -fsSL "$ROS_KEY_URL" -o "$tmp_dir/ros.key"
gpg --dearmor --yes --output "$tmp_dir/ros-archive-keyring.gpg" "$tmp_dir/ros.key"
sudo install -m 0644 "$tmp_dir/ros-archive-keyring.gpg" "$ROS_KEYRING"

echo "Configuring the USTC ROS 2 mirror..."
printf 'deb [arch=amd64 signed-by=%s] %s noble main\n' "$ROS_KEYRING" "$ROS_APT_MIRROR" \
  | sudo tee "$ROS_SOURCE_FILE" >/dev/null

echo "Installing ROS 2 Jazzy, Nav2, Gazebo integration, and minimal TurtleBot simulation..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ros-jazzy-desktop \
  ros-dev-tools \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-nav2-minimal-tb3-sim \
  ros-jazzy-ros-gz

if ! grep -Fq 'source /opt/ros/jazzy/setup.bash' "$HOME/.bashrc"; then
  printf '\nsource /opt/ros/jazzy/setup.bash\n' >> "$HOME/.bashrc"
fi

echo "Initializing rosdep..."
if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  sudo rosdep init
fi
rosdep update

echo "Installation complete. Open a new terminal or run:"
echo "source /opt/ros/${ROS_DISTRO_NAME}/setup.bash"
echo "ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False"
