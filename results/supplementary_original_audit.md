# 原最终评估只读审计：补充实验基线

输入：`results/phase4_final_aggregate.json`（SHA-256 `03118a2448681ea20bd4bb2a6fb209afb98d1272a96e88e72df8d6093a6e4f23`）。
有效 cell `320`，episode `1280`。
以下为描述性计数，不是新增确认性检验。

## 故障态导航与行为失败后的结果

| 方法 | 故障族 | 故障态导航成功 | 行为失败 | 行为失败中严格联合成功 | 全部严格联合成功 |
| --- | --- | ---: | ---: | ---: | ---: |
| eacr_static_m0 | localization | 33/80 | 47/80 | 0/47 | 0/80 |
| eacr_static_m0 | costmap | 0/80 | 80/80 | 80/80 | 80/80 |
| eacr_static_m0 | planner | 74/80 | 6/80 | 0/6 | 0/80 |
| eacr_static_m0 | control | 38/80 | 42/80 | 0/42 | 0/80 |
| eacr_evolving_online_m0 | localization | 27/80 | 53/80 | 0/53 | 0/80 |
| eacr_evolving_online_m0 | costmap | 0/80 | 80/80 | 79/80 | 79/80 |
| eacr_evolving_online_m0 | planner | 69/80 | 11/80 | 1/11 | 31/80 |
| eacr_evolving_online_m0 | control | 33/80 | 47/80 | 7/47 | 15/80 |
| eacr_evolving_m20 | localization | 32/80 | 48/80 | 0/48 | 0/80 |
| eacr_evolving_m20 | costmap | 0/80 | 80/80 | 80/80 | 80/80 |
| eacr_evolving_m20 | planner | 71/80 | 9/80 | 0/9 | 0/80 |
| eacr_evolving_m20 | control | 36/80 | 44/80 | 0/44 | 0/80 |
| eacr_evolving_m50 | localization | 36/80 | 44/80 | 0/44 | 0/80 |
| eacr_evolving_m50 | costmap | 0/80 | 80/80 | 79/80 | 79/80 |
| eacr_evolving_m50 | planner | 75/80 | 5/80 | 1/5 | 75/80 |
| eacr_evolving_m50 | control | 32/80 | 48/80 | 23/48 | 54/80 |

## 与 Static 配对：相同 belief、候选集与动作变化

| 方法 | 故障族 | belief 相同 | 候选集相同 | 动作改变 | 双方都发生行为失败 | 该子集严格联合成功 Static → 对照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| eacr_evolving_online_m0 | localization | 80/80 | 80/80 | 0/80 | 28/80 | 0/28 → 0/28 |
| eacr_evolving_online_m0 | costmap | 80/80 | 80/80 | 0/80 | 80/80 | 80/80 → 79/80 |
| eacr_evolving_online_m0 | planner | 80/80 | 80/80 | 56/80 | 0/80 | 0/0 → 0/0 |
| eacr_evolving_online_m0 | control | 80/80 | 80/80 | 40/80 | 27/80 | 0/27 → 3/27 |
| eacr_evolving_m20 | localization | 68/80 | 68/80 | 12/80 | 27/80 | 0/27 → 0/27 |
| eacr_evolving_m20 | costmap | 80/80 | 80/80 | 0/80 | 80/80 | 80/80 → 80/80 |
| eacr_evolving_m20 | planner | 72/80 | 80/80 | 0/80 | 0/80 | 0/0 → 0/0 |
| eacr_evolving_m20 | control | 80/80 | 80/80 | 80/80 | 26/80 | 0/26 → 0/26 |
| eacr_evolving_m50 | localization | 80/80 | 80/80 | 0/80 | 29/80 | 0/29 → 0/29 |
| eacr_evolving_m50 | costmap | 80/80 | 80/80 | 0/80 | 80/80 | 80/80 → 79/80 |
| eacr_evolving_m50 | planner | 80/80 | 80/80 | 80/80 | 1/80 | 0/1 → 0/1 |
| eacr_evolving_m50 | control | 80/80 | 80/80 | 80/80 | 25/80 | 0/25 → 12/25 |

`fault_navigation_status` 是干预前 Nav2 目标结果；它和干预恢复率不是同一指标。
双方法行为失败子集可能很小，不能据此单独主张优越性。
