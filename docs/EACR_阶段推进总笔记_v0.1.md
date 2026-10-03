# EACR 阶段推进总笔记 v0.1

更新时间：2026-09-26

## 0. 文件用途

本文件是 EACR 仿真和论文实验的阶段控制笔记。

后续第二阶段、第三阶段及其子任务，统一在本文件中记录：

- 阶段目标；
- 进入条件；
- 具体任务；
- 阶段门禁；
- 完成证据；
- 未解决问题；
- 计划变更及原因。

其他文档的职责保持不变：

- [研究框架](EACR_研究框架_v0.2.md)：研究问题、论文主张和实验假设；
- [算法规格](EACR_算法规格_v0.3.md)：EACR 数学定义和接口规范；
- [仿真部署计划](EACR_仿真平台从零部署计划_v0.1.md)：平台部署原则和长期路线；
- [仿真部署工作记录](EACR_仿真部署工作记录_v0.1.md)：系统安装、文件和命令的事实记录。

本文件负责回答一个问题：**当前处于哪个阶段，完成阶段需要什么证据，下一阶段何时才能开始。**

## 1. 总体研究主线

```text
证据采集
    ↓
fault belief
    ↓
经验模型 M_t
    ↓
信息增益 + 恢复收益 - 成本 - 不确定性
    ↓
安全动作选择
    ↓
执行并观察结果
    ↓
更新 belief 和 M_t
    ↓
改变下一次干预策略
```

核心论文主张：历史 intervention–outcome 经验不是只用于检索，而是直接进入 belief-space 的下一步主动恢复决策，并使动作排序随经验演化发生变化。

## 2. 阶段控制原则

1. 未达到当前阶段门禁，不开始下一阶段的大规模工作；
2. 每个阶段先完成最小可验证闭环，再扩展功能数量；
3. 仿真 Ground Truth 只用于故障注入和离线评价，不进入在线决策、belief 更新或恢复动作参数；
4. `eacr_core` 保持 ROS 无关，不导入 `rclpy` 或 `rospy`；
5. 所有正式实验固定记录地图、起点、目标点、随机种子、故障序列、动作序列和结果；
6. Strong LLM、MiniLLM、外部 rosbag 仓库和 ROS1 实车验证不提前插入第一阶段；
7. 阶段状态只使用：`未开始`、`进行中`、`已通过`、`阻塞`。标记为“已通过”必须有文件、日志或实验结果作为证据。

## 3. 阶段总览

| 阶段 | 目标 | 当前状态 |
|---|---|---|
| 第一阶段 | 用户目标点、正常导航基线、纯 Python `eacr_core`、单类定位故障最小闭环 | 进行中 |
| 第二阶段 | 扩展故障族、动作库、episode reset、证据记录和可重复实验基础设施 | 进行中 |
| 第三阶段 | 论文主实验、baseline、消融、经验演化和分布迁移验证 | 已完成门禁，迁移扩展另行记录 |
| 后续扩展 | Strong LLM 候选生成、RAG、MiniLLM、rosbag 离线支路、ROS1 外部验证 | 未开始 |

## 4. 第一阶段：导航基线与单故障 EACR 闭环

### 4.1 阶段目标

第一阶段只解决一个可控问题：在固定 `tb3_sandbox` 地图上，完成从用户选择目标点到单类 localization fault 恢复的最小闭环。

第一阶段包含以下四步，四步全部完成后才进入第二阶段：

```text
1. 选择并验证目标点
2. 建立正常导航基线
3. 实现纯 Python eacr_core
4. 接入第一类定位故障并跑通最小闭环
```

第一阶段不追求四类故障、批量实验或 LLM 接入。

### 4.2 已有前置条件

以下内容已经完成：

- Ubuntu 24.04、ROS 2 Jazzy、Nav2 Jazzy、Gazebo Harmonic、ros_gz；
- 官方 `tb3_sandbox` 地图和世界；
- `eacr_sim` package 构建；
- 自动 AMCL 初始位姿发布；
- AMCL 稳定检测和初始位姿锁定；
- 自动目标发送关闭；
- RViz 精简配置和 AMD 渲染路径；
- 当前 workspace 启动说明和部署事实记录。

### 4.3 第一步：选择并验证目标点

目标点由用户选择。当前临时目标 `(2.0, 0.5, 0.0)` 不作为正式实验目标。

验证内容：

- 目标点位于地图 free 区域；
- 目标点与障碍物保持合理距离；
- Nav2 能从固定初始位姿规划到目标；
- 目标姿态和坐标被明确记录；
- 目标点可以通过 RViz 或明确的 ROS2 接口发送，不依赖读取 Ground Truth。

完成证据：

- 用户确认的起点和目标点坐标；
- 地图名称和版本；
- 至少一次成功规划和到达日志；
- 目标点记录进入实验配置，而不是继续使用占位值。

当前正式目标点：

```text
map frame
x   = 0.7508496046
y   = 1.8354123831
yaw = 1.4751400097 rad
```

地图检查显示目标中心为 free cell，目标周围 0.35 m 内没有 occupied 或
unknown 栅格；目标已写入 `src/eacr_sim/config/episode.yaml`。

当前状态：`已通过`。

### 4.4 第二步：建立正常导航基线

在没有故障注入的情况下，使用固定起点、目标点、地图和随机种子运行重复导航，记录：

- 是否成功规划；
- 是否成功到达；
- 导航时间；
- 路径长度；
- 控制器和规划器异常；
- 到达后的稳定时间；
- 每次运行的日志、配置和结果文件。

建议先完成至少三次正常运行，确认底座稳定后再进入故障实验。基线的具体重复次数、超时和稳定窗口在第一步目标点确定后冻结。

完成证据：

- 正常导航结果表；
- 固定起点—目标点配置；
- 可复现启动命令；
- 无故障情况下的成功率和时间统计。

已新增 `scripts/validate_goal.py`，使用固定起点和目标点自动执行
`reset_episode → AMCL 稳定 → NavigateToPose → 结果记录`。当前三轮结果均为
`STATUS_SUCCEEDED (4)`，耗时分别为 15.20 s、17.90 s、18.30 s。

当前状态：`已通过`。

### 4.5 第三步：实现纯 Python `eacr_core`

第一版只实现算法最小集合：

- belief 初始化和 Bayesian 更新；
- Beta-Bernoulli 恢复成功模型；
- Dirichlet 结果模型；
- 信息增益；
- 恢复收益、成本和模型不确定性；
- 白名单、前置条件和风险硬约束；
- 动作评分和动作选择；
- 经验记录和在线更新。

先在不启动 Gazebo 的 toy-world 中验证：

- 固定随机种子后结果一致；
- `M_0`、`M_20`、`M_50` 能产生不同的动作排序；
- belief、结果预测和经验参数都有可序列化记录；
- `eacr_core` 不依赖 ROS。

完成证据：

- 纯 Python 单元级运行入口；
- 固定种子结果文件；
- 一组动作排名变化记录；
- 无 `rclpy`/`rospy` 导入。

已新增 `src/eacr_core` 纯 Python package。固定种子 `20260926` 的 toy-world
验收结果写入 `results/eacr_core_demo.json`：Bayesian belief 从均匀先验更新为
`localization_drift=0.4467`、`odom_tf_inconsistency=0.2132`、
`amcl_degeneracy=0.3401`；动作选择从 `M0: inspect_tf` 变为
`M20/M50: relocalize_amcl`；高风险动作被硬过滤；无安全动作时能够 abstain。
`eacr_core` 源码没有 `rclpy` 或 `rospy` 导入。

当前状态：`已通过`。

### 4.6 第四步：接入第一类定位故障并跑通最小闭环

第一类故障为 localization fault。故障可以表现为初始位姿偏移、定位漂移或定位置信度下降，但故障注入必须可重复、可回滚。

第一批动作限制为三个：

1. 检查定位一致性并采集证据；
2. 短时间降速或受控观测动作后重新判断；
3. 执行 AMCL 全局重定位。

闭环必须完成：

```text
故障注入
→ 证据采集
→ belief 更新
→ 候选动作安全过滤
→ 动作评分
→ 执行动作
→ 反馈观测
→ belief 和 M 更新
→ 恢复验证或 abstain
```

完成证据：

- 一次完整 localization fault episode；
- 动作前后 belief；
- 动作评分和选择原因；
- 执行结果和稳定窗口；
- verified success、verified failure 或 inconclusive 标记；
- 经验模型更新前后参数；
- 无安全动作时能够 abstain。

已新增 `eacr_localization_loop` 节点和两个服务：
`/inject_amcl_fault`、`/run_eacr_localization_episode`。一次真实
`tb3_sandbox` episode 已完成：注入 AMCL 初始位姿偏置
`(+0.65 m, -0.45 m, +0.35 rad)`，采集 `/amcl_pose` 和 `/odom` 证据，得到
`localization_drift=0.4971` 的最高 belief，依次选择
`inspect_tf → slow_observe → relocalize_amcl`，恢复稳定窗口验证成功。
完整记录写入 `results/eacr_localization_episode_001.json`；Ground Truth 没有进入
在线决策。

当前状态：`进行中`。

### 4.7 第一阶段门禁

只有同时满足以下条件，第一阶段才算通过：

```text
[x] 用户正式目标点已确定并通过地图/Nav2 可达性验证
[x] 正常导航基线已记录并可以重复运行
[x] 纯 Python eacr_core 可独立运行且结果可复现
[x] localization fault 最小闭环完成
[x] Ground Truth 没有进入在线决策
[x] 至少一次经验更新改变了后续动作评分或排序
[x] 失败或不确定时系统能够 abstain
```

目标点、正常导航、纯 Python 核心和 AMCL 偏置恢复工程链路已具备。最新在线
episode 已加入动作先验、每步 outcome likelihood、posterior belief trace 和经验
更新记录；一次重跑中 `inspect_tf` 的信息增益为 `0.0158`，AMCL 偏置证据后
belief 从 `localization_drift=0.4992`、`odom_tf_inconsistency=0.2435` 变为
`0.4027`、`0.4491`。但还没有证明经验更新改变了后续动作排序或选择，第一阶段
门禁仍为进行中。

## 5. 第二阶段：故障族和实验基础设施扩展

第二阶段只有在第一阶段门禁通过后开始。本文三个阶段先完成不依赖 LLM/RAG
的 EACR 主线；LLM、RAG 和 MiniLLM 不进入本文主方法、主实验或阶段门禁。

### 5.1 初步范围

- 扩展四类故障族：localization、costmap、planner、sensor/TF/control；
- 建立可回滚的在线故障注入器；
- 完善 episode reset、故障序列和随机种子管理；
- 建立统一 evidence/context/action/outcome 记录；
- 将动作库扩展到约 8–12 个安全动作；
- 为每个动作定义前置条件、预期观测、成本、风险、最长持续时间、回滚方式和验证标准；
- 建立 Rule-based 和 Bayesian fixed-recovery 等初始 baseline。

已完成第二阶段的第一批基础设施：

- `eacr_core/scenario.py`：四类故障规格和固定种子故障序列；
- `eacr_core/records.py`：统一 JSONL 事件和 episode summary；
- `eacr_core/action_library.py`：9 个带成本、风险、前置/观测和持续时间字段的动作；
- `eacr_core/baselines.py`：Rule-based、Bayesian fixed-recovery、EACR-Static；
- `eacr_sim/fault_injector.py`：localization、costmap、planner、control 的注入/回滚服务；
- `results/phase2_manifest.json`：固定种子 manifest 和基础验收结果。
- `scripts/run_phase2_experiment.py`：四个 baseline 共用同一故障序列的确定性
  smoke runner；当前只验证实验驱动器，不作为 Gazebo 性能结论。

### 5.2 第二阶段门禁

- 四类故障均可重复注入和回滚；
- 不同 episode 之间状态隔离；
- 所有 baseline 使用相同故障序列和随机种子；
- 结果文件能重建每一步 belief、动作、反馈和模型更新；
- 不依赖 LLM/RAG 也能完成实验。

当前状态：`进行中`。

已有验证：`scripts/validate_fault_injectors.py` 检查四类服务的返回值；这只能证明
接口调用成功。costmap 的严格在线行为验证已移到第三阶段 paired runner：通过
Nav2 `footprint_padding` 参数使 fault navigation 超时，再回滚并验证恢复；
`phase2_episode_runner` 仍明确不把 planner/control 参数读回当作行为故障。
planner/control 采用可恢复的参数级注入；曾测试的 lifecycle 停用方式会触发
Nav2 lifecycle manager 全局重置，已废弃，不作为正式故障注入方案。
统一事件记录已接入 localization episode，单轮正常导航回归为
`STATUS_SUCCEEDED (4)`、`15.90 s`。

`results/phase2_baseline_smoke.json` 已记录 Rule-based、Bayesian
fixed-recovery、EACR-Static、EACR-Evolving 四个 baseline 在相同 seed 和故障
序列下的 smoke run；它明确标记为 `synthetic_validation_only`。

当前状态：`接口完成，门禁未通过`。已有四轮固定 seed episode 的 reset、证据
采集、注入、回滚和独立事件记录，但旧结果把局部栅格微小波动、参数读回误当作
故障效果，且没有 planner/control 的导航行为证据，也没有 belief/action/model
update 决策轨迹。因此 `results/phase2_fault_matrix.json` 的 acceptance 不能作为
第二阶段通过证明；Gazebo baseline 性能比较仍属于第三阶段。

## 6. 第三阶段：论文主实验与扩展

第三阶段只有在第二阶段实验基础设施稳定后开始。

### 6.1 主实验

比较：

1. Rule-based recovery；
2. Bayesian diagnosis + fixed recovery；
3. IG without evolving experience；
4. EACR-Static；
5. EACR-Evolving。

固定相同的 belief、context、候选动作、成本、安全边界、故障序列和随机种子，只改变经验模型：

```text
M_0 → M_20 → M_50
```

报告：

- action ranking；
- policy KL divergence；
- outcome prediction NLL、Brier、ECE；
- useless probe rate；
- intervention cost；
- MTTR；
- recovery success；
- sustained recovery。

### 6.2 消融和迁移

- w/o Memory Update；
- w/o IG；
- w/o Recovery Utility；
- w/o Risk Constraint；
- w/o Belief Update；
- w/o Model Uncertainty；
- 旧环境到新环境的动作成功率变化和后验修正。

### 6.3 后期扩展

主实验稳定后，才评估：

- Strong LLM 开放集候选生成；
- explainable_ROS 的日志/图像证据整理；
- Bosch rosbag-fault-injection 的离线数据和回放基线；
- MiniLLM 或本地策略蒸馏；
- ROS1 外部验证。

这些扩展不能替代 EACR 主闭环，也不能改变主实验的核心比较协议。

### 6.4 第三阶段门禁

- EACR-Evolving 相对 EACR-Static 的策略变化和结果改善有统计证据；
- 消融能够说明 belief、IG、经验更新和风险约束各自的作用；
- 测试反馈没有泄漏到模型初始化或训练阶段；
- 仿真主结论能够独立复现；
- 扩展模块与 EACR 核心接口边界清晰。

当前状态：`进行中`。

## 7. 当前唯一执行焦点

第一阶段已经通过，第二阶段只有接口基础设施完成、门禁未通过；第三阶段协议和
适配器开发可以继续，但主实验结论必须等待第二阶段行为证据补齐。LLM、RAG、MiniLLM、外部 rosbag 仓库和 ROS1
实车验证继续保持未开始。

## 8. 阶段变更记录

### 2026-09-26

- 将原计划中的“选择目标点、正常导航基线、纯 Python `eacr_core`、第一类定位故障闭环”合并定义为第一阶段；
- 建立第二阶段和第三阶段的范围、门禁和完成条件；
- 确定后续阶段说明统一维护在本文件中；
- 用户确定正式目标点并完成三次正常导航基线；
- 完成纯 Python `eacr_core` 固定种子验收；
- 完成一次带 reset 的 AMCL 定位故障最小闭环，第一阶段状态更新为“已通过”；
- 第二阶段完成四类故障矩阵、episode 隔离和统一记录的第一批基础设施；当时误将
  接口返回成功记为门禁通过，后续审计已撤销该结论；
- 第三阶段协议开发开始，但主实验门禁仍依赖第二阶段行为证据补齐。

### 2026-09-29

- 用户将第三阶段设为当前 goal；
- 冻结 `results/phase3_protocol.json`：5 个 baseline、4 类故障、5 个 seed、
  `M_0/M_20/M_50` 检查点、消融条件和评价指标；
- 新增 `eacr_core.metrics`，为主实验提供 KL、NLL、Brier、ECE、MTTR 和恢复率计算。
- 新增 `scripts/run_phase3_experiment.py`，完成 5 个 seed、5 个 baseline 和消融
  条件的协议驱动 dry run；结果明确标记 `synthetic_dry_run`，不作为 Gazebo 主结论。
- 新增 `eacr_sim/phase3_gazebo_runner.py`，接通真实 reset、四类故障服务、
  `NavigateToPose` 和结果落盘；已完成两个 baseline 的单 episode 适配器运行。
  当前真实 episode 的导航结果仍为失败样本，尚未形成主实验统计结论。
- runner 现在强制记录 Nav2 lifecycle 状态；启动时 controller/local_costmap 未
  active 的结果会标记 `infrastructure_failure`，并由
  `scripts/aggregate_phase3_gazebo.py` 排除，不能进入论文统计。
- paired Gazebo 适配器已得到有效 costmap/control/localization 样本：每轮先做
  nominal 导航，再注入故障、执行 fault 导航、回滚/恢复并再次导航；costmap、
  control、localization 均出现可记录的 fault effect 和恢复成功。planner 首次
  参数修改未改变已实例化 planner，已补充 `ComputePathToPose` 的无效 planner_id
  探针；在 nominal 成功的一轮中返回 `error_code=201 INVALID_PLANNER`，随后恢复
  导航成功。nominal 导航失败的轮次会被排除，不能当作故障效果。
- 新增 `scripts/run_phase3_gazebo_matrix.py`，按冻结协议调度
  `baseline × seed × fault_family`，每轮独立落盘；新增 paired nominal 导航、
  在线 Nav2 参数证据、超时/取消原因和经验快照字段。当前只完成少量有效单轮，
  聚合器仍报告统计未就绪。
- baseline 语义已明确写入 runner：只有 `eacr_evolving`/`full_eacr` 更新在线经验，
  `eacr_static` 冻结，`ig_without_evolving_experience` 关闭信息增益项；聚合器现要求
  5 个 baseline × 5 个 seed × 4 类故障共 100 个 lifecycle-ready paired episode，
  且 nominal、fault effect、recovery 均有效后才允许统计门禁通过。
- 复核发现第二阶段旧验收逻辑过松：已将 costmap 目标单元转变、planner/control
  导航行为和决策轨迹列为必须证据，阶段状态回退为“接口完成，门禁未通过”。
- 首个真实矩阵批次 `bayesian_fixed_recovery / seed=20260926` 的四类故障已跑完；
  四轮均完成 nominal 导航、注入、fault 观测、回滚和恢复导航，但当前仍未进入
  统计聚合，因为 runner 还未满足 M0/M20/M50 与完整消融协议。
- 为避免把空模型误称为演化模型，新增 `ExperienceModel.from_snapshot` 和显式
  M0 领域先验；`eacr_evolving` 按 baseline/seed 持久化经验快照，`eacr_static`
  使用冻结先验。真实回归发现旧先验会选择低成本 `inspect_tf` 而不是定位恢复，
  已修正非恢复动作的 M0 恢复先验，并将 AMCL 相对 reset 位姿偏差作为定位故障效果证据。
同时修复了上下文键含多个分隔符时的快照反序列化问题；快照 round-trip 已通过。

### 2026-09-30

- 主实验 Gazebo 矩阵完成：5 个 baseline × 5 个 seed × 4 类故障，共 100/100 个有效 paired episode；
  `results/phase3_gazebo_aggregate.json` 的 `statistics_ready=true`。
- 主矩阵整体恢复成功率为 0.70；EACR-Static 为 0.90，EACR-Evolving 为 0.85，当前不能声称经验演化带来改善。
  EACR-Evolving 与 Static 的策略都按四类故障选择对应恢复动作，但仍需消融和检查点实验解释差异。
- `fault_effect_observed` 现表示可复核的子系统状态变化；另记录 `fault_behavior_observed` 表示导航 abort/timeout，避免把服务回包直接当作行为效果。
- 主实验完成后启动独立 checkpoint training；使用 seed 20300001..20300013 的独立训练目录，已获得 51 条唯一有效反馈，生成 M0、M20、M50 三个可审计 checkpoint，`phase3_experience_eacr_evolving_manifest.json` 标记 `ready=true`。
- 真实 Gazebo 消融矩阵已完成：7 个条件 × 5 个 seed × 4 类故障，共 140/140 个唯一协议有效单元；3 个无效重试文件未计入聚合。`results/phase3_ablation_aggregate.json` 标记 `all_conditions_complete=true`。
- `scripts/build_phase3_stage_gate.py` 已生成 `results/phase3_stage_gate.json`，主实验、M50 检查点和完整消融均通过，第三阶段总门禁为 `ready=true`。一次未设置 `GZ_PARTITION` 的并行试跑保留在 `results/phase3_ablation_gazebo_unisolated_rosdomain42/`，不参与统计。
- 规划器效果证据已改为记录参数配置回读，并单独保留 `fault_behavior_observed`；不能把配置生效自动解释为导航行为失败。
- 当前主矩阵的 planner 故障证据仍需谨慎解释：无效 planner ID 探针可证明 planner channel 返回错误，但不能单独证明真实导航行为被破坏；后续应补充有效 planner 配置切换或独立行为对照。
