# EACR 最终确认性评估报告

统计口径为 `docs/EACR_FINAL_STATISTICAL_SPEC_v1.md`。主比较是每个 Evolving 条件减去 Static M0。
主置信区间把 20 个 evaluation seed 作为配对聚类，重采样 20,000 次。
成功率差值为正更好；成本、无效探测和成功条件 MTTR 差值为负更好。
区间包含 0 时，不把该比较写成确定性优越。

## 方法水平

每个数是 20 个 seed 的等权平均。一个 seed 内部四个故障族等权。

| 方法 | IR | SR / strict joint | Cost | Useless probe | Success-conditional MTTR (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Static M0 | 0.250 | 0.250 | 0.232 | 0.750 | 58.26 |
| Evolving online M0 | 0.425 | 0.391 | 0.303 | 0.575 | 45.07 |
| Evolving M20 | 0.250 | 0.250 | 0.246 | 0.750 | 58.21 |
| Evolving M50 | 0.744 | 0.650 | 0.425 | 0.250 | 44.50 |

## 相对 Static 的配对差

| 方法 | 指标 | 种子数 | 平均差 | 95% CI | + / − / 0 | 读法 |
| --- | --- | ---: | ---: | --- | --- | --- |
| Evolving online M0 | Intervention recovery | 20 | 0.175 | [0.163, 0.184] | 20 / 0 / 0 | CI excludes 0 in the favourable direction |
| Evolving online M0 | Sustained recovery / strict joint success | 20 | 0.141 | [0.113, 0.166] | 18 / 0 / 2 | CI excludes 0 in the favourable direction |
| Evolving online M0 | Intervention cost | 20 | 0.071 | [0.066, 0.074] | 20 / 0 / 0 | CI excludes 0 in the unfavourable direction |
| Evolving online M0 | Useless probe | 20 | -0.175 | [-0.184, -0.163] | 0 / 20 / 0 | CI excludes 0 in the favourable direction |
| Evolving online M0 | Success-conditional MTTR (s) | 20 | -13.187 | [-14.834, -11.351] | 0 / 20 / 0 | CI excludes 0 in the favourable direction |
| Evolving M20 | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | Sustained recovery / strict joint success | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | Intervention cost | 20 | 0.014 | [0.013, 0.016] | 20 / 0 / 0 | CI excludes 0 in the unfavourable direction |
| Evolving M20 | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | Success-conditional MTTR (s) | 20 | -0.051 | [-0.144, 0.051] | 7 / 13 / 0 | CI includes 0; no superiority claim |
| Evolving M50 | Intervention recovery | 20 | 0.494 | [0.484, 0.500] | 20 / 0 / 0 | CI excludes 0 in the favourable direction |
| Evolving M50 | Sustained recovery / strict joint success | 20 | 0.400 | [0.366, 0.431] | 20 / 0 / 0 | CI excludes 0 in the favourable direction |
| Evolving M50 | Intervention cost | 20 | 0.193 | [0.193, 0.193] | 20 / 0 / 0 | CI excludes 0 in the unfavourable direction |
| Evolving M50 | Useless probe | 20 | -0.500 | [-0.500, -0.500] | 0 / 20 / 0 | CI excludes 0 in the favourable direction |
| Evolving M50 | Success-conditional MTTR (s) | 20 | -13.757 | [-14.737, -12.735] | 0 / 20 / 0 | CI excludes 0 in the favourable direction |

## 分故障族配对差

每一行固定一个故障族，在 20 个 seed 上做配对 bootstrap。cell 内 4 次重复先取平均，不把 episode 当作独立样本。

| 方法 | 故障族 | 指标 | 种子数 | 平均差 | 95% CI | + / − / 0 | 读法 |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| Evolving online M0 | localization | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving online M0 | localization | Sustained recovery / strict joint success | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving online M0 | localization | Intervention cost | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving online M0 | localization | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving online M0 | localization | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |
| Evolving online M0 | costmap | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving online M0 | costmap | Sustained recovery / strict joint success | 20 | -0.013 | [-0.037, 0.000] | 0 / 1 / 19 | CI includes 0; no superiority claim |
| Evolving online M0 | costmap | Intervention cost | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving online M0 | costmap | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving online M0 | costmap | Success-conditional MTTR (s) | 20 | 0.013 | [-0.087, 0.110] | 10 / 10 / 0 | CI includes 0; no superiority claim |
| Evolving online M0 | planner | Intervention recovery | 20 | 0.450 | [0.400, 0.487] | 20 / 0 / 0 | CI excludes 0 in the favourable direction |
| Evolving online M0 | planner | Sustained recovery / strict joint success | 20 | 0.388 | [0.287, 0.475] | 16 / 0 / 4 | CI excludes 0 in the favourable direction |
| Evolving online M0 | planner | Intervention cost | 20 | 0.172 | [0.153, 0.185] | 20 / 0 / 0 | CI excludes 0 in the unfavourable direction |
| Evolving online M0 | planner | Useless probe | 20 | -0.450 | [-0.487, -0.400] | 0 / 20 / 0 | CI excludes 0 in the favourable direction |
| Evolving online M0 | planner | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |
| Evolving online M0 | control | Intervention recovery | 20 | 0.250 | [0.250, 0.250] | 20 / 0 / 0 | CI excludes 0 in the favourable direction |
| Evolving online M0 | control | Sustained recovery / strict joint success | 20 | 0.188 | [0.138, 0.225] | 15 / 0 / 5 | CI excludes 0 in the favourable direction |
| Evolving online M0 | control | Intervention cost | 20 | 0.113 | [0.113, 0.113] | 20 / 0 / 0 | CI excludes 0 in the unfavourable direction |
| Evolving online M0 | control | Useless probe | 20 | -0.250 | [-0.250, -0.250] | 0 / 20 / 0 | CI excludes 0 in the favourable direction |
| Evolving online M0 | control | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |
| Evolving M20 | localization | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | localization | Sustained recovery / strict joint success | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | localization | Intervention cost | 20 | 0.006 | [0.000, 0.012] | 3 / 0 / 17 | CI includes 0; no superiority claim |
| Evolving M20 | localization | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | localization | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |
| Evolving M20 | costmap | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | costmap | Sustained recovery / strict joint success | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | costmap | Intervention cost | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | costmap | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | costmap | Success-conditional MTTR (s) | 20 | -0.051 | [-0.143, 0.049] | 7 / 13 / 0 | CI includes 0; no superiority claim |
| Evolving M20 | planner | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | planner | Sustained recovery / strict joint success | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | planner | Intervention cost | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | planner | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | planner | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |
| Evolving M20 | control | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | control | Sustained recovery / strict joint success | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | control | Intervention cost | 20 | 0.050 | [0.050, 0.050] | 20 / 0 / 0 | CI excludes 0 in the unfavourable direction |
| Evolving M20 | control | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M20 | control | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |
| Evolving M50 | localization | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M50 | localization | Sustained recovery / strict joint success | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M50 | localization | Intervention cost | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M50 | localization | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M50 | localization | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |
| Evolving M50 | costmap | Intervention recovery | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M50 | costmap | Sustained recovery / strict joint success | 20 | -0.013 | [-0.037, 0.000] | 0 / 1 / 19 | CI includes 0; no superiority claim |
| Evolving M50 | costmap | Intervention cost | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M50 | costmap | Useless probe | 20 | 0.000 | [0.000, 0.000] | 0 / 0 / 20 | CI includes 0; no superiority claim |
| Evolving M50 | costmap | Success-conditional MTTR (s) | 20 | 0.032 | [-0.101, 0.167] | 11 / 9 / 0 | CI includes 0; no superiority claim |
| Evolving M50 | planner | Intervention recovery | 20 | 1.000 | [1.000, 1.000] | 20 / 0 / 0 | CI excludes 0 in the favourable direction |
| Evolving M50 | planner | Sustained recovery / strict joint success | 20 | 0.938 | [0.875, 0.988] | 20 / 0 / 0 | CI excludes 0 in the favourable direction |
| Evolving M50 | planner | Intervention cost | 20 | 0.370 | [0.370, 0.370] | 20 / 0 / 0 | CI excludes 0 in the unfavourable direction |
| Evolving M50 | planner | Useless probe | 20 | -1.000 | [-1.000, -1.000] | 0 / 20 / 0 | CI excludes 0 in the favourable direction |
| Evolving M50 | planner | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |
| Evolving M50 | control | Intervention recovery | 20 | 0.975 | [0.938, 1.000] | 20 / 0 / 0 | CI excludes 0 in the favourable direction |
| Evolving M50 | control | Sustained recovery / strict joint success | 20 | 0.675 | [0.562, 0.775] | 19 / 0 / 1 | CI excludes 0 in the favourable direction |
| Evolving M50 | control | Intervention cost | 20 | 0.400 | [0.400, 0.400] | 20 / 0 / 0 | CI excludes 0 in the unfavourable direction |
| Evolving M50 | control | Useless probe | 20 | -1.000 | [-1.000, -1.000] | 0 / 20 / 0 | CI excludes 0 in the favourable direction |
| Evolving M50 | control | Success-conditional MTTR (s) | 0 | — | — | 0 / 0 / 0 | CI includes 0; no superiority claim |

## 优势是否只来自一个故障族

- Evolving online M0 / Intervention recovery：有利且排除 0 的故障族为 planner, control。
- Evolving online M0 / Sustained recovery / strict joint success：有利且排除 0 的故障族为 planner, control。
- Evolving online M0 / Intervention cost：没有故障族的区间落在有利一侧且排除 0。
- Evolving online M0 / Useless probe：有利且排除 0 的故障族为 planner, control。
- Evolving online M0 / Success-conditional MTTR (s)：没有故障族的区间落在有利一侧且排除 0。
- Evolving M20 / Intervention recovery：没有故障族的区间落在有利一侧且排除 0。
- Evolving M20 / Sustained recovery / strict joint success：没有故障族的区间落在有利一侧且排除 0。
- Evolving M20 / Intervention cost：没有故障族的区间落在有利一侧且排除 0。
- Evolving M20 / Useless probe：没有故障族的区间落在有利一侧且排除 0。
- Evolving M20 / Success-conditional MTTR (s)：没有故障族的区间落在有利一侧且排除 0。
- Evolving M50 / Intervention recovery：有利且排除 0 的故障族为 planner, control。
- Evolving M50 / Sustained recovery / strict joint success：有利且排除 0 的故障族为 planner, control。
- Evolving M50 / Intervention cost：没有故障族的区间落在有利一侧且排除 0。
- Evolving M50 / Useless probe：有利且排除 0 的故障族为 planner, control。
- Evolving M50 / Success-conditional MTTR (s)：没有故障族的区间落在有利一侧且排除 0。

## 口径

- Intervention recovery 使用 `recovery_success`，不是恢复后的导航成功。
- Sustained recovery 与 strict joint success 都使用 `episode_success`。
- MTTR 使用成功恢复 episode 的 `time_to_recovery_sec`。没有成功恢复的 seed 保持缺失，不填 0。
- 成本把成功和失败的已记录 action 都算进分母。
- 本报告不提供未预注册的 p 值。
