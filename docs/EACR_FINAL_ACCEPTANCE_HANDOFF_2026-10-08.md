# EACR 最终确认性评估：验收交接记录

**状态：已完成，可以开始验收。** 本记录对应 2026-10-08 完成的最终确认性评估。统计输入、seed 清单和 checkpoint 均按冻结规范使用；无效尝试保留在原始结果目录中，并纳入 GitHub 备份。

## 1. 验收摘要

评估覆盖 20 个冻结 evaluation seed、4 个故障族、每个 seed×故障族 4 次重复，以及 4 个方法。四个方法均有 80/80 个有效 cell：共 **320 个有效 cell、1,280 个有效 episode**。聚合器的 `confirmatory_ready` 为 `true`，全部验收门槛通过。

| 方法 | 有效 cell | 原始 JSON 文件 | 原始 JSON 字节 | 被排除的 protocol-noncompliant 尝试 |
| --- | ---: | ---: | ---: | ---: |
| Static M0 | 80/80 | 121 | 36,406,514 | 40 |
| Online Evolving M0 | 80/80 | 205 | 56,527,054 | 104 |
| Frozen Evolving M20 | 80/80 | 295 | 86,122,363 | 194 |
| Frozen Evolving M50 | 80/80 | 198 | 55,492,115 | 97 |
| **合计** | **320/320** | **819** | **234,548,046** | **435** |

目录中的 JSON 总数包括有效记录、无效/重试记录和辅助 experience-state JSON；有效 cell 数以 `phase4_final_count_cells.py` 和聚合器验收为准。聚合器另记录 4 条无法归入四种方法的旧记录，故全部排除数为 439。无效文件未删除，也未纳入估计量。

## 2. 冻结设计与运行口径

完整定义见 [`EACR_FINAL_STATISTICAL_SPEC_v1.md`](EACR_FINAL_STATISTICAL_SPEC_v1.md)。主键是 `(method, seed, fault_family)`，每个 cell 必须有 4 个 protocol-compliant 且 evidence-valid episode。每个 seed 内先对四个故障族等权，再在 20 个 seed 上配对比较。主置信区间以 evaluation seed 为 cluster，有放回抽取 20 个 seed，bootstrap 20,000 次；没有用 episode 或 80 个 cell 作为独立样本。

固定故障族：`localization`、`costmap`、`planner`、`control`。固定 evaluation seed：

```text
1069364068  683001511   450637390   1207356449  1578549000
252445555   729528073   1092085222  200776800   1464253601
365260637   225495283   1725492561  1054169594  1613439514
1691408245  849115063   1146002680  1534671149  1320660730
```

`544047076` 不在最终 evaluation seeds 中。冻结执行参数为 `fault_scale=1.5`、`fault_repetitions=4`、`experience_prior_mode=weak_shared_m0`、`use_belief_action_scope=true`、`goal_timeout_sec=60`、`resume_experience_state=false`。Static M0 不更新经验；Online Evolving M0 在同一 cell 的顺序重复 episode 内在线更新；M20/M50 使用完整四故障训练 snapshot，测试时 `online_experience_update=false`。

| Snapshot | SHA-256 |
| --- | --- |
| `phase4_experience_evolving_full_M_0.json` | `6312a0e9aa5c87ad259bc93dd44d43a9b7cd2745757fa98c575cb645772f1964` |
| `phase4_experience_evolving_full_M_20.json` | `6fcfd7dac372c181223b86c683a54b21d255c51f07af522cb3e5eae9a10c4473` |
| `phase4_experience_evolving_full_M_50.json` | `79e9e84b58b634f34ff71a6a42f5ccca81792b60aa757155544a555557a739ab` |

聚合门槛逐项为 true：四种方法齐全、每种方法 80 个 cell、每个 cell 4 个有效 episode、共同的 20×4 配对键、无重复 cell、seed 排除正确、配置一致、M20/M50 snapshot SHA 有效。冻结 aggregate 记录 `bootstrap.unit=evaluation_seed`、`draws=20000`、随机种子 `20261004`。

## 3. 总体结果与结论

报告中的 IR 是 intervention recovery；SR / strict joint 是恢复动作成功且恢复后导航成功的严格联合指标。Cost 是干预成本（越低越好）；Useless probe 越低越好；MTTR 是成功恢复条件下的恢复时间。均值是 20 个 seed 等权平均，每个 seed 内四个故障族等权。

| 方法 | IR | SR / strict joint | Cost | Useless probe | 成功条件 MTTR (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Static M0 | 0.250 | 0.250 | 0.232 | 0.750 | 58.26 |
| Online Evolving M0 | 0.425 | 0.391 | 0.303 | 0.575 | 45.07 |
| Frozen Evolving M20 | 0.250 | 0.250 | 0.246 | 0.750 | 58.21 |
| Frozen Evolving M50 | 0.744 | 0.650 | 0.425 | 0.250 | 44.50 |

相对 Static M0 的 20-seed paired-cluster-bootstrap 结果：

| 方法 | 指标 | 均值差 | 95% CI | 结论 |
| --- | --- | ---: | --- | --- |
| Online M0 | IR | +0.175 | [0.163, 0.184] | 有利；区间不含 0 |
| Online M0 | SR / strict joint | +0.141 | [0.113, 0.166] | 有利；区间不含 0 |
| Online M0 | Cost | +0.071 | [0.066, 0.074] | 代价增加；区间不含 0 |
| M20 | IR | 0.000 | [0.000, 0.000] | 没有恢复率优势 |
| M20 | SR / strict joint | 0.000 | [0.000, 0.000] | 没有严格联合成功优势 |
| M20 | Cost | +0.014 | [0.013, 0.016] | 代价增加；区间不含 0 |
| M20 | 成功条件 MTTR | −0.051 s | [−0.144, 0.051] | 区间含 0，不能声称更快 |
| M50 | IR | +0.494 | [0.484, 0.500] | 有利；区间不含 0 |
| M50 | SR / strict joint | +0.400 | [0.366, 0.431] | 有利；区间不含 0 |
| M50 | Cost | +0.193 | [0.193, 0.193] | 代价增加；区间不含 0 |
| M50 | Useless probe | −0.500 | [−0.500, −0.500] | 有利；区间不含 0 |
| M50 | 成功条件 MTTR | −13.757 s | [−14.737, −12.735] | 有利；区间不含 0 |

**对 M20 的验收判断：** 当前最终样本没有显示 Frozen Evolving M20 在恢复率或严格联合成功率上优于 Static M0；干预成本略高，MTTR 区间包含 0。不能把 M20 解释为已证实的 evolving 优势。

**对 M50 的验收判断：** M50 的总体恢复和严格联合成功明显提高，同时成本增加。分故障族审计显示恢复优势主要来自 `planner` 和 `control`：M50 在这两族的 SR 差分别为 +0.938（95% CI [0.875, 0.988]）和 +0.675（[0.562, 0.775]）；`localization` 无差异，`costmap` SR 差为 −0.013（[−0.037, 0.000]，区间含 0）。因此应同时报告效果集中于故障族及成本取舍，不能笼统表述成对所有故障都占优。

Online M0 的 SR 增益也集中于 planner（+0.388，[0.287, 0.475]）和 control（+0.188，[0.138, 0.225]）；这两族的成本分别增加 +0.172 和 +0.113。每个指标、每个故障族的完整差值、CI 和正/负/零 seed 计数，见最终报告的“分故障族配对差”表及“优势是否只来自一个故障族”审计段。

## 4. 原始数据与验收文件

四个方法的所有原始 JSON（包括无效尝试、重试和辅助状态文件）都保留在对应目录：

```text
results/phase4_final_static_m0/
results/phase4_final_evolving_online_m0/
results/phase4_final_evolving_m20/
results/phase4_final_evolving_m50/
```

重要验收文件：

- [`phase4_final_report.md`](../results/phase4_final_report.md)：方法级配对差、按故障族差值与集中性审计、指标解释。
- [`phase4_final_aggregate.json`](../results/phase4_final_aggregate.json)：320 个有效 cell、1,280 个 episode、seed 指标、paired bootstrap、门槛和排除计数。
- [`phase4_final_tables.json`](../results/phase4_final_tables.json)：报告表格数据。
- [`phase4_final_eval_status.json`](../results/phase4_final_eval_status.json)：最终状态和各方法 cell/file 计数。
- [`phase4_final_raw_data_manifest.json`](../results/phase4_final_raw_data_manifest.json)：819 个原始 JSON 的逐文件大小与 SHA-256 清单。
- [`phase4_final_m50_resume.log`](../results/phase4_final_m50_resume.log)：M50 最后补跑及最终聚合通过记录。
- [`EACR_FINAL_STATISTICAL_SPEC_v1.md`](EACR_FINAL_STATISTICAL_SPEC_v1.md)：冻结统计定义。

原始四方法 JSON 已按原路径逐文件存放在 GitHub 的 `results/phase4_final_*` 目录中，方便直接查看和下载。逐文件 SHA-256 与大小列在 `results/phase4_final_raw_data_manifest.json`。完整工作区差异的压缩归档也保留在 GitHub `backups/`，包含有效与无效结果、执行日志、脚本、文档及带 SHA-256 清单的恢复信息；两种形式互为补充。

## 5. 可复核命令

在仓库根目录运行以下只读 cell 计数：

```bash
python3 results/phase4_final_count_cells.py eacr_static_m0 results/phase4_final_static_m0
python3 results/phase4_final_count_cells.py eacr_evolving_online_m0 results/phase4_final_evolving_online_m0
python3 results/phase4_final_count_cells.py eacr_evolving_m20 results/phase4_final_evolving_m20
python3 results/phase4_final_count_cells.py eacr_evolving_m50 results/phase4_final_evolving_m50
```

冻结 aggregate 已生成并通过门槛；复核其 JSON 字段即可确认 `confirmatory_ready=true`、`valid_cell_count=320`、`valid_episode_count=1280`、`bootstrap.draws=20000` 和上述 acceptance 布尔值均为 true。复核期间不要覆盖冻结输入、snapshot、seed manifest 或原始 JSON；如果要重跑或改变统计口径，请另存输出并先记录为新的分析版本。

## 6. 执行与运行器收尾

M50 续跑包装器记录显示：2026-10-08 07:49:26 启动单一 Gazebo，08:35:12 达到 80/80，08:35:13 停止其自有 Gazebo，随后对四个方法重新逐一验收计数，并在 08:35:14 运行冻结 20,000-draw aggregate；08:35:28 聚合和论文报告通过。最后检查没有残留 Gazebo 进程。没有在本次收尾中改动冻结协议、checkpoint 或算法实现。

## 7. GitHub 备份

仓库：[`1104546057-cloud/EACR`](https://github.com/1104546057-cloud/EACR)。完整工作区差异归档的 SHA-256 为 `3209ea228d1beff6e81f39ab584b6587763a9c236641b8d299f864ac8a9ad2b8`；压缩包 18,025,665 字节，含 940 个文件（解压 362,377,555 字节），分成 26 个 GitHub 文件保存。恢复步骤见 [`EACR_FINAL_BACKUP_2026-10-08.md`](../backups/EACR_FINAL_BACKUP_2026-10-08.md)。本次验收交接还把四个方法的原始 JSON 目录作为普通文件逐项上传，避免只提供压缩归档。
