# EACR-Evolving 最终确认性评估：统计口径冻结规范 v1

本文档冻结最终 20-seed 评估的统计定义。Cursor 只负责按协议运行 Gazebo 和保存原始记录；统计脚本、汇总、置信区间和论文表格由 Codex 维护。没有新的协议变更时，不得临时更换估计量、分母或 bootstrap 单位。

## 1. 分析对象和数据层级

最终测试包含：

- 20 个冻结 evaluation seed；
- 4 个故障族：`localization`、`costmap`、`planner`、`control`；
- 每个 seed×故障族 4 次重复 episode；
- 4 个方法：`eacr_static_m0`、`eacr_evolving_online_m0`、`eacr_evolving_m20`、`eacr_evolving_m50`。

因此每个方法最多有 80 个 cell、320 个 episode。一个 cell 的主键是 `(method, seed, fault_family)`，不能按文件名或 run id 配对。

有效 episode 必须同时满足结果文件 `protocol_compliant == true`、`episode_evidence_valid == true`，并且同一 cell 恰有 4 条同故障族记录。无效运行和基础设施失败保留在磁盘上，但不进入估计量。

## 2. 方法条件

### Static M0

- `baseline=eacr_static`；
- `experience_checkpoint=M_0`；
- weak shared M0 prior；
- 测试阶段不更新经验；
- 不读取任何训练运行的经验状态。

### Evolving online M0

- `baseline=eacr_evolving`；
- `experience_checkpoint=M_0`；
- 测试 episode 内允许在线更新；
- 不读取训练运行的经验状态；
- 更新只发生在同一 cell 的顺序重复 episode 内，不跨方法、不跨 seed 借用状态。

### Evolving M20 / M50

- `baseline=eacr_evolving`；
- 从完整四故障训练生成的 `phase4_experience_evolving_full_M_20.json` 或 `M_50.json` 加载；
- `online_experience_update=false`；
- `resume_experience_state=false`；
- 每条结果必须记录 snapshot 路径和 SHA-256，且 SHA 必须与加载文件实际 SHA 一致。

## 3. Episode 层指标

### 3.1 Intervention recovery

单个 episode 的 `intervention_recovery` 使用 runner 写入的 `recovery_success`：对应当前故障族的恢复服务是否成功执行。该字段不是恢复后导航成功；后者单独统计。有效记录中若恢复动作不匹配故障族，`recovery_success=false`。

单个 cell 的 intervention recovery rate：

```text
IR(m,s,f) = mean_r recovery_success(m,s,f,r), r=1..4
```

### 3.2 Sustained recovery

单个 episode 的 sustained recovery 使用 `episode_success`。它要求故障效果被观测、恢复动作成功、回滚/恢复状态有效，并且恢复后的独立导航成功。

```text
SR(m,s,f) = mean_r episode_success(m,s,f,r), r=1..4
```

这是严格联合指标，不得与 intervention recovery 混写。

### 3.3 Strict joint success

论文可以把 `episode_success` 作为严格联合成功率报告；它与 sustained recovery 使用相同布尔定义。表格中要标明它是联合成功，不得把它叫作单纯 intervention success。

### 3.4 Intervention cost

使用每个 episode 的 `intervention_cost`，按 4 个 episode 等权平均；成功和失败都进入分母，只要 action 被记录。报告：

```text
Cost(m,s,f) = mean_r intervention_cost(m,s,f,r)
```

成本是代价指标，越低越好。Evolving 如果通过更积极的恢复提高成功率但成本更高，必须同时展示，不能只展示成功率。

### 3.5 MTTR / time to recovery

MTTR 的操作定义固定为**条件性干预恢复时间**：从 fault injection 开始，到对应恢复服务成功返回为止。runner 字段为 `time_to_recovery_sec`。

- 成功恢复 episode 才有有限时间值；诊断动作、错误恢复动作或服务失败记为缺失/右删失；
- 每个 cell 报告 `mttr_success_mean_sec`、`mttr_success_median_sec` 和 `mttr_success_n`，同时报告该 cell 的 intervention recovery rate；
- MTTR 不作为脱离成功率的单独优越性证据。失败越多的方法不能因为只对少量成功 episode 计算而被解释为整体更快；
- 若需要一个包含失败的时间指标，另报固定随访窗内的 restricted mean time-to-recovery，并将未恢复 episode 视为在干预随访窗末端删失。当前主论文先使用成功条件 MTTR + intervention recovery 双指标，避免把删失假设隐藏在一个均值里。

当前 runner 的干预服务 timeout 是 30 s；导航 timeout 是 60 s。不要把 `recovery_navigation_duration_sec` 误称为 MTTR，它是恢复动作之后的导航耗时。

### 3.6 Useless probe

沿用现有定义：选中的 action 名称以 `inspect` 开头且 `episode_success=false`。它是辅助指标，越低越好；不得用它替代主要成功率。

## 4. Seed 级聚合和配对

四类故障族先在 cell 内聚合，再在 seed 内等权聚合：

```text
IR_seed(m,s) = mean_f IR(m,s,f), f ∈ {localization,costmap,planner,control}
SR_seed(m,s) = mean_f SR(m,s,f)
Cost_seed(m,s) = mean_f Cost(m,s,f)
Probe_seed(m,s) = mean_f Probe(m,s,f)
```

这样每个 seed 对整体估计贡献相同，每个故障族在一个 seed 内权重相同；不能把 80 个 cell 直接当作 80 个独立样本作为主 CI。

对每个 evolving 方法与 Static 做同 seed 的差值：

```text
Δ_metric(s) = metric_seed(evolving,s) - metric_seed(static,s)
```

方向约定：

- IR、SR、strict joint success：`Δ > 0` 更好；
- MTTR、Cost、useless probe：`Δ < 0` 更好；
- 对 MTTR，优先报告成功条件分布和成功数，不把缺失值随意填 0。

## 5. 置信区间和显著性

主置信区间以 20 个 evaluation seed 为独立 cluster，对 20 个 `Δ_metric(s)` 做 paired cluster bootstrap：每次有放回抽取 20 个 seed，保留该 seed 的四个故障族聚合值，重新计算平均差；重复 20,000 次，取 2.5% 和 97.5% 分位数。

故障族分层结果也以 20 个 seed 为 bootstrap cluster：固定一个故障族，在 20 个 seed 上做 paired bootstrap。不要对 4 次重复 episode 或 80 个 cell 直接独立重采样作为主结果。

最终报告：均值差、95% paired bootstrap CI、20 个 seed 中差值为正/负/零的数量，并给出每个故障族的同样结果。若 CI 包含 0，不能写成确定性优越；若优势只来自一个故障族，要明确说明。

本评估不把一个未经预注册的 p 值作为唯一结论。三个 Evolving 条件相对 Static 的比较和两个主要成功率端点全部并列报告；如果后续增加正式 p 值，必须对这 6 个预先定义的主要比较使用 Holm 校正，并同时保留未校正值和校正规则。

## 6. 最终验收门槛

统计脚本只有在以下条件都满足时才生成 confirmatory aggregate：

1. 四个方法目录都存在；
2. 每个方法恰有 80 个 distinct `(seed,fault_family)` 有效 cell；
3. 每个 cell 有 4 个有效 episode；
4. 四方法共有完全相同的 20×4 paired keys；
5. Static/Evolving prior、action scope、fault scale 和 repetitions 一致；
6. M20/M50 的 snapshot path、SHA 和 `online_experience_update=false` 全部一致；
7. `544047076` 不在最终测试 seed 中；
8. pilot 目录、训练目录、planner-only checkpoint 不在 confirmatory aggregate 输入中。

任何一个门槛失败，只输出缺口报告，不计算最终优势结论。

## 7. 文件所有权

- Codex：本文件、统计脚本、最终 aggregate、论文统计表；
- Cursor：`results/phase4_final_*` 原始结果、运行日志、final evaluation 状态 JSON；
- 双方只读：`results/phase3_evolving_advantage_protocol.json`、seed manifest、`phase4_experience_evolving_full_*` checkpoint；
- Cursor 不修改 `src/`、`scripts/`、`docs/` 或 checkpoint；如 runner 出现代码问题，先停止并报告，不在最终评估中临时改实现。
