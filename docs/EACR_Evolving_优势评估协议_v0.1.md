# EACR-Evolving 优势评估协议 v0.1

## 目的

本协议用于检验 EACR-Evolving 是否能利用历史 intervention–outcome 反馈，在重复故障、先验不完美和测试分布变化时获得相对 EACR-Static 的性能优势。

原第三阶段 `eacr_phase3_v1` 结果保持冻结，不被本协议覆盖。

## 核心假设

`H1`：在训练反馈改变后，EACR-Evolving 的动作排序和 outcome prediction 会发生可审计变化。

`H2`：在未参与训练的测试 seed 上，EACR-Evolving 相对冻结的 EACR-Static 具有更高的干预恢复率和持续恢复率；MTTR 与干预成本同时报告，不预设其一定更低。

`H3`：优势主要出现在故障重复出现、故障严重程度或环境上下文发生变化的测试单元中。

## 方法条件

| 条件 | 初始化 | 测试阶段更新 |
|---|---|---|
| `eacr_static_m0` | M0 | 否 |
| `eacr_evolving_online_m0` | M0 | 是 |
| `eacr_evolving_m20` | 独立训练得到的 M20 | 否 |
| `eacr_evolving_m50` | 独立训练得到的 M50 | 否 |

所有条件使用相同地图、目标点、动作库、安全规则、故障序列和测试 seed。

## 训练与测试划分

- 训练 seed：`20310001..20310013`，由固定清单预先生成，不进入最终测试；
- pilot seed：`20410001..20410004`，只用于修复协议与可行性检查，不进入最终统计推断；
- 最终测试 seed：见 `results/phase3_evolving_advantage_seed_manifest.json`，使用 `secrets.SystemRandom.sample` 生成的 20 个独立整数，已在最终测试开始前冻结；
- 测试反馈不初始化 M20/M50，也不回写冻结 checkpoint；
- 每个 seed 至少重复出现同一故障族，使在线更新有机会影响后续决策。
- 训练阶段使用 `fault_scale=1.0`，测试阶段使用预先冻结的 `fault_scale=1.5`；该参数会改变 localization、costmap 和 control 故障强度，并写入运行记录。

## 先验与策略

M0 使用双方完全相同的弱先验。它给每个故障族的对应恢复动作一个小幅较高的先验均值，因此包含弱的领域映射；该映射、动作库及筛选器对 Static 和 Evolving 完全相同。论文必须如实报告先验设置，不能称其为无知识先验。

动作候选先经过相同的 belief 相关范围过滤：保留当前主导故障族的诊断/恢复动作和 `slow_observe` 通用安全观测动作。该过滤只表达动作前置条件与安全相关性，Static 和 Evolving 使用完全相同的过滤器。

Evolving 使用预先冻结的 checkpoint 加载流程。`experience_checkpoint` 必须实际读取对应 snapshot，不能只写入结果字段；结果记录 snapshot 路径和 SHA-256。M20/M50 测试阶段关闭在线更新，避免把测试反馈写回冻结模型。

## 随机性

- 最终测试 seed 在实验开始前一次性生成并保存，协议 SHA-256 和 seed 清单另存于 manifest；
- 所有方法使用同一测试 seed；
- 不根据结果替换、删除或重新挑选 seed；
- Gazebo、故障序列和实验调度日志均记录 seed 和 run id。

## 指标与统计判据

主要指标：

1. `intervention_recovery_rate`：动作对应的 fault injector rollback 是否成功；
2. `sustained_recovery_rate`：rollback 后的独立导航是否成功；
3. MTTR；
4. intervention cost。

`episode_success` 仍保留为严格联合指标（故障被观测、目标恢复动作成功、恢复后导航成功），但不再把它与动作层恢复混写。这样可以区分“恢复动作已经成功，但后续 Nav2 action 被取消”和“恢复动作本身没有生效”。

辅助指标：

- action ranking change；
- policy KL；
- outcome prediction NLL、Brier、ECE；
- useless probe rate；
- 按 fault family 和 context 的分层结果。

主要比较先在每个 seed×故障族内聚合四次重复，再在同一 seed 的四个故障族上求平均，并按 seed 配对计算差值与 bootstrap 置信区间。只有当优势在最终冻结测试集上稳定出现，且不是由单个故障族或单个 seed 造成时，才在论文中声称 Evolving 优于 Static。pilot 数据与最终结果分表呈现。

## 实验分批

1. 先完成 ROS 无关 dry run，检查 checkpoint 加载、重复故障序列和统计脚本；
2. 再运行小规模 Gazebo pilot，确认 Evolving 能产生动作排序变化；
3. 冻结 pilot 后运行完整 held-out Gazebo 矩阵；
4. 最后生成独立汇总和论文表格。

## 最终 seed 清单修订（2026-10-03）

原最终清单中的 `544047076` 被用于一次 planner/M50 checkpoint 加载 pilot（Static 与 Evolving 的结果均已观察），因此不再作为确认性推断样本。这个排除规则与 pilot 结果方向和幅度无关。用 `secrets.SystemRandom.randrange(100000000, 2000000000)` 抽取无冲突的 `1069364068` 替换，保留最终清单 20 个 seed。原清单、暴露原因、修订时间及旧协议 SHA 均保存在 `results/phase3_evolving_advantage_seed_manifest.json` 与协议 JSON 中。`544047076` 的 pilot 结果只用于机制说明，绝不并入最终置信区间或显著性结论。
