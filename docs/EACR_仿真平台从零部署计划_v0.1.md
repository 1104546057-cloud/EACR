# EACR 仿真平台从零部署计划 v0.1

## 0. 目标与边界

目标：在 Ubuntu 24.04 上建立 ROS 2 Jazzy + Nav2 Jazzy + Gazebo Harmonic + ros_gz 的可重复移动机器人导航故障仿真平台，并逐步接入 EACR。

主实验平台只负责论文仿真。现有 ROS 1 无人车不迁移、不作为当前部署依赖；ROS 1 适配器放到仿真闭环稳定之后。

核心原则：

- `eacr_core` 不导入 `rospy` 或 `rclpy`；
- 先复用官方 TurtleBot/Nav2/Gazebo，再实现 EACR 自己的故障注入、证据采集和恢复动作；
- 先做一个故障、三个动作的闭环，再扩展到四类故障；
- 所有实验配置、随机种子、故障序列和结果都可记录、可复现。

## 1. 阶段总览

### 阶段 0：网络与系统准备

安装 ROS 前先确认 Ubuntu 软件源、ROS 软件源和 GitHub 可访问。网络未确认前不开始大规模安装。

验收：`apt update`、ROS 软件源和 GitHub 均可访问。

### 阶段 A：主机与 ROS2 环境

输入：Ubuntu 24.04.5，空工作区。

工作：

1. 安装 ROS 2 Jazzy desktop、ros-dev-tools、rosdep；
2. 安装 Nav2 Jazzy、Gazebo Harmonic、ros_gz 和 Nav2 minimal TurtleBot 仿真包；
3. 配置 shell 环境和工作区环境；
4. 保存安装版本、系统信息和启动命令。

验收：

- `ros2 doctor` 可运行；
- `ros2 topic list` 可运行；
- 官方 Nav2 TurtleBot 仿真能够启动；
- Gazebo、RViz、AMCL、planner、controller 正常出现。

停止条件：官方仿真无法启动前，不写 EACR 节点，不开始故障实验。

### 阶段 B：建立项目工作区与最小闭环

目录：

```
eacr_ws/
├── src/
│   ├── eacr_core/
│   ├── eacr_interfaces/
│   ├── eacr_sim/
│   ├── eacr_monitor/
│   ├── eacr_fault_injector/
│   ├── eacr_backend_ros2/
│   └── eacr_experiments/
├── README.md
├── results/
└── docs/

ROS 运行时资源归属具体 package：`src/eacr_backend_ros2/{launch,config}`、`src/eacr_sim/{launch,config,maps,worlds}`。
```

先实现：

- 统一 evidence/context/action/outcome 数据结构；
- ROS 无关的 belief、Beta/Dirichlet、IG、动作评分和安全过滤；
- ROS2 adapter 的证据读取接口；
- 记录每一步的 belief、候选动作、评分、执行结果和时间戳。

验收：

- 不启动 Gazebo 也能运行 toy-world 数学仿真；
- 固定随机种子后结果一致；
- ROS2 节点能够读取仿真证据并输出结构化记录。

### 阶段 C：单故障在线闭环

第一类故障建议从 localization fault 开始，例如：

- 初始位姿偏移；
- 定位漂移或定位置信度下降；
- 受控重定位动作。

第一批动作限制为三个：

1. 采集/检查定位一致性；
2. AMCL 全局重定位；
3. 短时间降速并重新观察。

Ground Truth 只允许用于故障注入和离线评价，禁止进入 EACR 决策、belief 更新或 recovery action 参数；不得读取真实坐标后直接设置初始位姿。

每个动作必须经过：

- schema 校验；
- 白名单匹配；
- 前置条件检查；
- 风险过滤；
- 执行后稳定窗口验证。

闭环：

```
故障注入 → 证据采集 → belief → 动作评分
→ 执行动作 → 反馈 → belief/M 更新 → 恢复验证
```

验收：

- 一次故障实例能够完成完整闭环；
- 无安全动作时系统 abstain；
- 经验更新能改变后续动作评分。

### 阶段 D：扩展故障与动作

四类故障族：

1. localization；
2. costmap；
3. planner；
4. sensor / TF / control。

先实现可重复、可安全回滚的注入方式：

- 参数或状态扰动；
- topic/消息级受控异常；
- 节点服务级异常；
- 必要时使用 rosbag fault injection 做离线辅助数据，不替代在线闭环。

动作库目标：8–12 个安全动作。每个动作定义：

- 前置条件；
- 预期观测；
- 成本；
- 风险等级；
- 最大持续时间；
- 回滚方式；
- 验证标准。

### 阶段 E：论文主实验

主比较：

- Rule-based recovery；
- Bayesian diagnosis + fixed recovery；
- IG without evolving experience；
- EACR-Static；
- EACR-Evolving。

关键控制实验：

固定 belief、context、候选动作、成本、安全边界、故障序列和随机种子，只替换经验模型：

```
M0 → M20 → M50
```

记录：

- action ranking；
- policy KL；
- posterior mean/variance；
- useless probe rate；
- intervention cost；
- MTTR；
- recovery success；
- sustained recovery。

分布迁移实验：

- 旧环境中动作 A 成功率高；
- 新环境中动作 A 成功率下降；
- 观察后验修正和动作排名恢复。

数据隔离：

- 测试反馈不得初始化模型；
- 未来反馈不得进入当前时刻；
- 同一故障实例不同时进入训练和独立测试；
- 所有 baseline 使用相同故障序列和随机种子。

### 阶段 F：Strong LLM 候选生成

最后接入。LLM 只输出：

- 开放集故障假设；
- 候选干预；
- 所需证据；
- abstain 和不确定性说明。

EACR 继续负责：

- schema 校验；
- 白名单和前置条件；
- 安全过滤；
- 结果预测；
- 动作排序；
- 执行与停止。

评估 valid candidate rate、open-set recall、unsafe rejection rate、candidate coverage、latency 和 token cost。

### 阶段 G：ROS1 外部验证

仿真主结论完成后，再实现 ROS1 backend adapter：

- 读取 scan、odom、TF、定位、costmap 和导航状态；
- 转换成统一 evidence；
- 只执行低风险、可回滚动作；
- 单独报告工程接入、延迟和真实传感器变化。

ROS1 结果不与 ROS2 仿真结果混合统计。

## 2. 第一轮实际操作顺序

1. 安装 ROS2 Jazzy 与 Nav2 依赖；
2. 启动官方 TurtleBot/Nav2 仿真；
3. 保存主机和软件版本；
4. 创建上述工作区目录；
5. 实现 toy-world 与 EACR core；
6. 实现 ROS2 evidence collector；
7. 注入单类定位故障；
8. 跑通一次在线闭环；
9. 再扩展四类故障和论文实验。

## 3. 当前不做

- 不迁移现有 ROS1 无人车；
- 不用 ros1_bridge 作为主实验依赖；
- 不先接 Strong LLM；
- 不先做 MiniLLM 蒸馏；
- 不把 rosbag 回放当作在线恢复闭环；
- 不在官方仿真未通过前调 EACR 算法。

## 4. 当前决策

采用 Ubuntu 24.04 + ROS2 Jazzy + Nav2 Jazzy + Gazebo Harmonic + ros_gz + Nav2 minimal TurtleBot 作为主仿真平台；EACR 核心保持 ROS 无关，ROS2 只作为适配器和实验后端。

