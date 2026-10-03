# EACR 仿真部署工作记录 v0.1

更新时间：2026-09-26

## 1. 部署目标

主仿真平台固定为 Ubuntu 24.04、ROS 2 Jazzy、Nav2 Jazzy、Gazebo Harmonic、ros_gz 和 Nav2 minimal TurtleBot 3。现有 ROS1 无人车没有迁移或修改。

## 2. 已完成的系统部署

- Ubuntu 24.04.5 LTS（noble），amd64；
- 内存约 14 GB；`/` 可用空间约 300 GB；`/home` 可用空间约 110 GB；
- ROS2 镜像：中科大镜像可用，清华返回 403，阿里云可作为备用；
- ROS 软件源文件：`/etc/apt/sources.list.d/ros2.list`；
- 已安装：`ros-jazzy-desktop`、`ros-jazzy-navigation2`、`ros-jazzy-nav2-bringup`、`ros-jazzy-nav2-minimal-tb3-sim`、`ros-jazzy-ros-gz`、`ros-dev-tools`、`rosdep`；
- Gazebo 版本：`Gazebo Sim 8.15.0`；
- `rosdep init` 和 `rosdep update` 已完成，缓存位于 `/home/hu/.ros/rosdep/sources.cache`。

## 3. 已创建的部署文件

- [EACR_仿真平台从零部署计划_v0.1.md](../EACR_仿真平台从零部署计划_v0.1.md)：平台选型、阶段门禁、目录规划、Ground Truth 边界和实验路线；
- [install_ros2_jazzy_ustc.sh](../scripts/install_ros2_jazzy_ustc.sh)：配置中科大镜像并安装 ROS2、Nav2、Gazebo bridge、minimal TB3 和 rosdep；
- [README.md](../README.md)：workspace 使用说明；
- [source_eacr.sh](../scripts/source_eacr.sh)：加载 ROS2 和当前 isolated workspace overlay。
- `src/eacr_sim/config/map_profiles.yaml`：当前主地图和未来 open/corridor/cluttered 地图的配置入口。

安装脚本不保存或读取系统密码。

## 4. 已创建的 ROS2 package

目录：`eacr_ws/src/eacr_sim/`。

文件包括：`package.xml`、`setup.py`、`setup.cfg`、`resource/eacr_sim`、`eacr_sim/episode_manager.py`、`config/episode.yaml`、`rviz/eacr_minimal.rviz` 和 `launch/eacr_episode.launch.py`。

`episode_manager.py` 当前能够：

- 向 `/initialpose` 发布 AMCL 初始位姿；
- 订阅 `/amcl_pose` 并判断定位稳定；
- 检查 `/controller_server/get_state` 和 `/bt_navigator/get_state`；
- 等待 Nav2 lifecycle 节点 active；
- 自动发送 `NavigateToPose` 目标；
- 不订阅或使用 Gazebo Ground Truth。

当前默认 `auto_send_goal` 为 `false`。AMCL 稳定后会锁定初始位姿并停止重复发布，等待用户提供目标。

`eacr_episode.launch.py` 组合官方 `nav2_bringup/tb3_simulation_launch.py` 和 episode manager，并支持 `headless`、`use_rviz`、`rviz_gpu`、`rviz_config` 参数。为便于选择图形渲染器，Nav2 默认 RViz 由 EACR launch 关闭，随后按 EACR 参数单独启动。

## 5. 坐标配置现状

当前初始位姿为官方 TB3 默认生成位姿：`(-2.0, -0.5, 0.0)`。

当前目标为 ` (2.0, 0.5, 0.0)`，这是临时占位值，尚未完成路径可达性验证，不能作为正式实验目标。当前 `auto_send_goal` 已设为 `false`，系统不会自动发送这个占位目标。后续需要先确认地图 free 区域、Nav2 路径可达性和重复导航稳定性。

## 6. 已完成的验证

执行 `colcon build --packages-select eacr_sim` 已成功。

官方 Nav2 仿真已启动过，Gazebo、ros_gz bridge、robot_state_publisher、AMCL、map server、planner、controller、behavior server、BT navigator 和 costmap 均能启动。

自动 episode 日志已确认：

```text
Episode manager started; publishing deterministic AMCL initial pose.
AMCL is stable; sending deterministic navigation goal.
Navigation goal accepted; waiting for result.
controller_server: Received a goal.
controller_server: Passing new path to controller.
```

这证明自动初始位姿和 AMCL 稳定判断链路已经打通。目标点由用户确认后再启用自动发送。

## 7. 已知问题

1. 临时目标未经验证，暂时不能用于论文实验；
2. RViz 的旧崩溃已通过 AMD 渲染器和精简配置规避；地图显示仍会打印一条非致命 GLSL 链接提示，见第 14 节；
3. workspace 使用 isolated install，建议通过 `source scripts/source_eacr.sh` 加载环境；
4. 测试用 timeout 曾留下仿真进程，已清理。

## 8. 尚未完成

第一阶段的 `eacr_core`、evidence collector、belief update、Beta/Dirichlet
experience model、information gain、动作评分、安全过滤、Gazebo episode reset、
AMCL 故障注入和 EACR 恢复动作已经完成。第二阶段正在完善多故障 episode runner、
baseline 和实验隔离；Strong LLM、RAG、MiniLLM 和 ROS1 adapter 不属于本文当前范围。

## 9. 下一步

继续完成第二阶段的多故障 episode runner、统一结果重建和 baseline 对比。

当前原则：先完成可回滚的故障与记录基础设施，再开展第二阶段的重复实验。

## 10. 外部仓库评估

### 10.1 Bosch Research rosbag-fault-injection

仓库地址：[boschresearch/rosbag-fault-injection](https://github.com/boschresearch/rosbag-fault-injection)。该仓库用于 ROS2 rosbag 的记录、故障修改、回放和绘图，支持按 Topic、消息类型、故障类型、开始时间、持续时间和随机种子配置故障。

对 EACR 的适用方式：

- 用于生成可重复的离线传感器或消息故障数据集；
- 用于 rosbag 回放、监测器评价和传统方法基线；
- 借鉴其随机种子、时间窗口、Topic 选择和 YAML 配置设计；
- 不作为 EACR 在线闭环的唯一故障注入器。

原因是 EACR 需要“执行干预—环境变化—重新观测—验证结果—更新经验—改变后续动作选择”的在线闭环。rosbag 修改和回放适合作为离线实验支路，不能替代仿真运行时的在线故障注入。

该仓库的开发容器基于较旧的 ROS2 Galactic，不能直接照搬到当前的 ROS2 Jazzy 环境。后续如果需要使用，优先提取配置和注入逻辑，放在 `eacr_ws/tools/third_party/` 或单独的离线实验目录中，不把它作为当前主 workspace 的运行时依赖。

### 10.2 explainable_ROS

仓库地址：[Dsobh/explainable_ROS](https://github.com/Dsobh/explainable_ROS)。该仓库通过 Topic/日志监控、RAG、嵌入模型、重排序模型和 LLM/VLM 对机器人行为进行解释，并包含 ROS2 消息和 bringup 结构。

对 EACR 的适用方式：

- 参考其 Topic 和日志监控节点；
- 为证据采集器提供日志筛选和上下文整理思路；
- 后期作为 Strong LLM 的候选故障假设或候选动作生成模块；
- 生成实验后的行为解释和故障分析报告。

它不包含 EACR 所需的 belief 更新、干预效用评分、信息增益、安全约束、干预结果模型和在线经验更新。因此当前不把它放进 EACR 核心决策路径。它还依赖 `llama_ros`、嵌入/重排序模型和 CUDA，过早接入会增加部署复杂度。

后期推荐的接口关系为：

```text
日志 / Topic / 图像
        ↓
证据筛选与解释模块（可选 explainable_ROS）
        ↓
Strong LLM 生成候选假设或候选动作（可选）
        ↓
EACR belief、信息增益、代价、风险和安全过滤
        ↓
最终恢复动作
```

LLM 或解释模块只提供候选信息和上下文，不直接绕过 EACR 的安全过滤和最终动作选择。

## 11. 两个仓库与当前研究架构的关系

EACR 主实验仍采用：

```text
Gazebo / Nav2
        ↓
在线证据采集
        ↓
EACR belief 与责任判断
        ↓
安全约束下的恢复动作选择
        ↓
故障注入或真实异常
        ↓
结果验证
        ↓
干预—结果经验模型更新
        ↓
下一轮策略改变
```

两个外部仓库放在辅助支路：

```text
Bosch rosbag-fault-injection
        → 离线可重复故障数据、回放和基线

explainable_ROS
        → 日志/图像证据整理、候选假设和实验解释
```

这样可以保持论文的核心贡献清晰：解释模块负责整理和说明证据，EACR 负责在不确定性下选择恢复干预，并通过干预结果改变后续决策。

## 12. 当前执行决策

1. 暂不克隆或安装上述两个仓库到主 workspace；
2. 先完成用户指定目标点的地图可达性验证和正常导航；
3. 实现自有的在线 `eacr_fault_injector`，优先完成 AMCL 定位异常；
4. 建立纯 Python `eacr_core`，保持与 ROS 解耦；
5. 完成“故障—证据—belief—动作—验证—经验更新”的最小闭环；
6. 核心闭环稳定后，再用 Bosch 仓库设计离线 rosbag 基线；
7. EACR 核心完成后，再评估 explainable_ROS 的日志监控、RAG 和解释功能。

当前停止条件保持不变：没有经过地图和 Nav2 验证的目标点，不进入正式故障实验；没有跑通在线恢复闭环，不把外部 LLM/解释模块接入主决策路径。

## 13. 最新部署成果：地图与定位初始化

本节记录当前已经落地的仿真启动行为，作为后续继续部署的基线。

### 13.1 主地图已固定

当前主地图固定为官方 `tb3_sandbox`，不再由 episode manager 直接散落配置路径。地图配置入口为：

```text
eacr_ws/src/eacr_sim/config/map_profiles.yaml
```

当前启动配置显式使用：

```text
地图：
/opt/ros/jazzy/share/nav2_bringup/maps/tb3_sandbox.yaml

Gazebo 世界：
/opt/ros/jazzy/share/nav2_minimal_tb3_sim/worlds/tb3_sandbox.sdf.xacro
```

后续增加 `open`、`corridor`、`cluttered` 等地图时，只增加或修改地图配置项，不修改 episode manager 的定位和导航逻辑。

### 13.2 定位初始化流程已整理

当前启动后的定位流程为：

```text
机器人生成
    ↓
episode manager 自动发布 AMCL 初始位姿
    ↓
等待 /amcl_pose 达到稳定条件
    ↓
锁定初始位姿
    ↓
停止重复发布初始位姿
    ↓
等待用户提供目标点
```

当前初始位姿仍为官方 TB3 默认值：

```text
x = -2.0
y = -0.5
yaw = 0.0
```

该位姿用于仿真初始化和定位稳定流程，不使用 Gazebo Ground Truth 参与 EACR 决策。

### 13.3 自动目标发送已关闭

当前配置为：

```yaml
auto_send_goal: false
```

因此 AMCL 稳定后，系统不会自动发送尚未由用户确认的临时目标。验证日志为：

```text
AMCL is stable; automatic goal sending is disabled.
The system is ready for a user-provided goal.
```

这一步把目标点选择从部署流程中分离出来，后续由用户提供目标点，再进行地图 free 区域、路径可达性和重复导航验证。

### 13.4 当前推荐启动命令

```bash
cd "/home/hu/文档/ChatGPT/论文/eacr_ws"
source scripts/source_eacr.sh
ros2 launch eacr_sim eacr_episode.launch.py \
  headless:=False \
  use_rviz:=True \
  rviz_gpu:=1
```

`rviz_gpu:=1` 在当前双显卡主机上选择 AMD 渲染器。EACR 默认配置位于 `src/eacr_sim/rviz/eacr_minimal.rviz`，提供地图、机器人、TF、LaserScan、规划路径、初始位姿工具和目标工具。若只运行仿真而不打开 RViz，可设置 `use_rviz:=False`。

### 13.5 当前部署状态

```text
[已完成] ROS2 Jazzy / Nav2 / Gazebo Harmonic / ros_gz
[已完成] 官方 tb3_sandbox 地图和世界配置
[已完成] eacr_sim package 构建
[已完成] AMCL 初始位姿自动发布
[已完成] AMCL 稳定检测
[已完成] 初始位姿发布锁定
[已完成] 自动目标发送关闭
[已完成] 正式目标点选择与记录
[已完成] 目标点地图 free 区域和安全窗口检查
[已完成] 目标点三次 reset-and-navigate 正常验证
[已完成] `/reset_episode` episode reset 服务
[已完成] 在线故障注入和 EACR 恢复闭环
```

## 14. RViz 图形问题排查与修复记录

### 14.1 排查结论

本机有 AMD Radeon 780M 核显和 NVIDIA GeForce GTX 1660 SUPER。X11 当前默认 OpenGL 设备曾走 NVIDIA `nouveau` 驱动下的 Mesa NVK/Zink；RViz 日志记录了 `indexed_8bit_image` GLSL 链接提示，旧 Nav2 默认 RViz 配置还加载了 Navigation、Selector、Docking 等额外面板。

测试发现，精简后的 RViz 在当前环境中可以持续运行并在退出时正常关闭。地图显示仍会打印：

```text
active samplers with a different type refer to the same texture image unit
```

这条信息在当前测试中没有导致 RViz 进程退出；RViz 最终报告 `process has finished cleanly`。因此目前修复的是 RViz 的崩溃/退出问题，GLSL 提示本身仍存在，作为非致命渲染器提示保留记录。

### 14.2 已落地调整

- `eacr_episode.launch.py` 不再从 Nav2 默认 launch 隐式启动默认 RViz，而是单独启动 RViz；
- 新增 `rviz_gpu` 参数，默认 `1`，在当前主机对应 AMD 渲染器；如需选择默认 NVIDIA/NVK 渲染器，可传 `rviz_gpu:=0`；
- 新增 `rviz_config` 参数，默认使用 EACR 自带精简配置；
- 新增 `src/eacr_sim/rviz/eacr_minimal.rviz`，只加载 Grid、RobotModel、TF、LaserScan、Map 和 Path 等基础显示，不加载 Nav2 自定义面板；
- 保留 RViz 的初始位姿和目标工具；
- `use_rviz:=False` 仍可关闭 RViz，Gazebo 和 Nav2 仿真流程不受影响。

这些是 workspace 内可逆的 launch 和 RViz 配置调整，没有替换系统显卡驱动，也没有修改 ROS 安装目录。

### 14.3 验证结果

执行 `colcon build --packages-select eacr_sim` 成功。随后以 `headless:=False use_rviz:=True rviz_gpu:=1` 启动完整仿真：

- RViz 成功启动并加载 EACR 配置；
- Gazebo、Nav2 和 episode manager 正常启动；
- AMCL 稳定日志出现，系统等待用户目标；
- RViz 在运行期间未报告进程崩溃；
- Ctrl+C 后 RViz 报告正常结束。

退出完整仿真时，Nav2 的 `component_container_isolated` 另有 `Magick: ... SIGSEGV` 退出记录。这发生在 ROS2 组件容器清理阶段，RViz 本身已经正常退出；需作为独立的 Nav2 关闭问题另行排查，不能与 GLSL 提示混为一谈。

## 15. 当前启动命令

```bash
cd "/home/hu/文档/ChatGPT/论文/eacr_ws"
source scripts/source_eacr.sh
ros2 launch eacr_sim eacr_episode.launch.py \
  headless:=False \
  use_rviz:=True \
  rviz_gpu:=1
```

如需隐藏 RViz：

```bash
ros2 launch eacr_sim eacr_episode.launch.py headless:=False use_rviz:=False
```

## 16. RViz 修复后的当前结论

本轮 RViz 问题处理已经完成并写入当前启动基线：

```text
[已完成] RViz 独立启动，不再使用 Nav2 默认 RViz 启动路径
[已完成] 默认使用 AMD 渲染器（rviz_gpu:=1）
[已完成] 使用 EACR 精简 RViz 配置
[已完成] RViz 可随 Gazebo/Nav2 正常启动
[已完成] RViz 运行期间未再出现原来的崩溃
[已完成] Ctrl+C 后 RViz 正常退出
[已记录] indexed_8bit_image GLSL 提示仍存在，但目前为非致命提示
[待单独处理] Nav2 component_container_isolated 退出时的 Magick SIGSEGV
```

当前正式使用的启动命令为：

```bash
cd "/home/hu/文档/ChatGPT/论文/eacr_ws"
source scripts/source_eacr.sh
ros2 launch eacr_sim eacr_episode.launch.py \
  headless:=False \
  use_rviz:=True \
  rviz_gpu:=1
```

不启动 RViz 时使用：

```bash
ros2 launch eacr_sim eacr_episode.launch.py \
  headless:=False \
  use_rviz:=False
```

## 17. 阶段推进总笔记

后续阶段统一维护在：[EACR_阶段推进总笔记_v0.1.md](EACR_阶段推进总笔记_v0.1.md)。当前第一阶段包含四步：正式目标点验证、正常导航基线、纯 Python `eacr_core`、第一类 localization fault 最小闭环。阶段完成必须满足总笔记中的验收门槛；第二、第三阶段暂不提前实施。
## 18. 正式目标点、正常导航基线与 episode reset

### 18.1 正式目标点

目标点由用户在 RViz 的 `2D Goal Pose` 工具中选择，随后从 `/goal_pose`
读取并记录为：

```text
frame: map
x:     0.7508496046
y:     1.8354123831
yaw:   1.4751400097 rad (84.52 deg)
```

该点在 `/map` 的检查结果为：

```text
center cell: free (0)
0.35 m window: no occupied or unknown cell
```

### 18.2 正常导航重复验证

新增脚本 `scripts/validate_goal.py`，每轮执行：

```text
reset_episode
→ 等待 AMCL 回到固定起点并连续稳定
→ 发送 NavigateToPose
→ 等待 action result
→ 记录状态和耗时
```

三轮结果：

```text
trial 1: PASS, status 4, 15.20 s
trial 2: PASS, status 4, 17.90 s
trial 3: PASS, status 4, 18.30 s
summary: passed=3 total=3
```

### 18.3 episode reset

新增 `eacr_sim/episode_reset.py` 和 `/reset_episode` 服务：

```bash
source scripts/source_eacr.sh
ros2 service call /reset_episode std_srvs/srv/Trigger '{}'
```

reset 使用 Gazebo `model_only` reset，不重置仿真时间；随后发布固定的
`/initialpose`，等待短暂稳定时间。这样能够同时恢复 Gazebo 模型状态、
差分驱动里程计和 AMCL 初始条件，避免只调用 `set_pose` 导致多轮 episode
后出现 `odom` 与 `map` 不一致。

当前 reset 服务适合在上一轮导航 action 已结束后开始下一轮；验证脚本已经
按这个顺序调用。

## 19. 第一阶段 EACR 核心和 AMCL 故障闭环

### 19.1 ROS 无关核心

新增纯 Python package `src/eacr_core`，只依赖 Python 标准库，包含：

- Bayesian fault belief 更新和离散 outcome 的期望信息增益；
- Beta-Bernoulli recovery model；
- Dirichlet outcome model；
- 成本、恢复收益、不确定性和硬安全约束下的动作评分；
- belief 加权的在线经验更新和可序列化 snapshot；
- 无安全动作时的 `abstain`。

固定种子 toy-world 验收入口为：

```bash
python3 scripts/run_eacr_core_demo.py
```

结果文件为 `results/eacr_core_demo.json`。其中 `M0` 选择 `inspect_tf`，
`M20` 和 `M50` 选择 `relocalize_amcl`，并通过无安全动作的 abstain 检查。

### 19.2 AMCL 定位故障最小闭环

新增 `eacr_localization_loop` 节点。其两个服务为：

```bash
source scripts/source_eacr.sh
ros2 service call /inject_amcl_fault std_srvs/srv/Trigger '{}'
ros2 service call /run_eacr_localization_episode std_srvs/srv/Trigger '{}'
```

`/run_eacr_localization_episode` 默认先调用 `/reset_episode`，再执行：

```text
固定 AMCL 偏置注入
→ /amcl_pose、/odom 证据采集
→ belief 更新
→ 安全动作过滤和选择
→ inspect_tf / slow_observe / relocalize_amcl
→ AMCL 稳定窗口恢复验证
→ Beta/Dirichlet 经验更新
```

一次真实 `tb3_sandbox` 结果已写入：
`results/eacr_localization_episode_001.json`。该轮 reset 成功，注入
`(+0.65 m, -0.45 m, +0.35 rad)` 偏置，恢复验证为
`recovery_success: true`。第二轮结果显示 `relocalize_amcl` 的效用从
`0.029` 上升到 `0.114`，证明 ROS 侧经验更新进入下一轮评分。

当前第一阶段四项任务已全部完成；第二阶段正在进行。

## 20. 第二阶段基础设施与四类故障注入

### 20.1 纯 Python 基础设施

新增：

- `eacr_core/scenario.py`：四类故障规格和固定种子故障序列；
- `eacr_core/records.py`：统一 JSONL 事件和 episode summary；
- `eacr_core/action_library.py`：9 个带成本、风险、预期观测、最长持续时间
  和回滚字段的动作；
- `eacr_core/baselines.py`：Rule-based、Bayesian fixed-recovery、EACR-Static；
- `scripts/run_phase2_manifest.py`：固定种子 manifest 验收入口。
- `scripts/run_phase2_experiment.py`：四个 baseline 共用同一故障序列的确定性
  smoke runner。

manifest 结果：
`results/phase2_manifest.json`，四类故障覆盖、9 个动作、baseline 决策和事件
记录均通过。

### 20.2 ROS 注入和回滚

新增 `eacr_sim/fault_injector.py`，服务对为：

```bash
source scripts/source_eacr.sh
ros2 service call /inject_localization_fault std_srvs/srv/Trigger '{}'
ros2 service call /rollback_localization_fault std_srvs/srv/Trigger '{}'
ros2 service call /inject_costmap_fault std_srvs/srv/Trigger '{}'
ros2 service call /rollback_costmap_fault std_srvs/srv/Trigger '{}'
ros2 service call /inject_planner_fault std_srvs/srv/Trigger '{}'
ros2 service call /rollback_planner_fault std_srvs/srv/Trigger '{}'
ros2 service call /inject_control_fault std_srvs/srv/Trigger '{}'
ros2 service call /rollback_control_fault std_srvs/srv/Trigger '{}'
```

验证入口：

```bash
source scripts/source_eacr.sh
python3 scripts/validate_fault_injectors.py
```

在新启动的 `tb3_sandbox` 仿真中，四类 injection 和 rollback 均成功，结果写入
`results/phase2_fault_injector_validation.json`。planner/control 使用参数级故障
并恢复原值，避免停用 lifecycle 节点造成 Nav2 全局重置。

新增 `phase2_episode_runner` 和 `/run_phase2_fault_matrix`。该 runner 对固定 seed
的四个故障 episode 逐轮执行 `reset → evidence → inject → evidence → rollback`
并分别保存 JSONL 事件和 summary。

`results/phase2_fault_matrix.json` 验证结果：四轮 reset、四轮 injection、四轮
rollback 全部成功。第二阶段基础设施门禁已通过。

### 20.3 Baseline smoke runner

`scripts/run_phase2_experiment.py` 使用固定 seed、相同故障序列和相同动作库运行
Rule-based、Bayesian fixed-recovery、EACR-Static、EACR-Evolving，并写入统一
事件记录。该入口使用合成 outcome oracle 只检查实验驱动器的公平性和可重建性，
结果明确标记为 `synthetic_validation_only`，不作为 Gazebo 性能结果。
