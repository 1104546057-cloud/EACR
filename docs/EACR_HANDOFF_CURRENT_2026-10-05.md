# EACR 最终评估交接笔记（2026-10-05）

## 1. 目标

完成 EACR 四种方法的最终 Gazebo 确认性评估，并在全部有效后生成统计汇总、配对 bootstrap CI、分故障族审计、论文表格和 GitHub 备份。

四种方法各需要 20 个冻结 seed × 4 个故障族，每个 cell 4 次 episode，即每种方法 80 个有效 cell、320 个有效 episode；四种方法合计 1280 个 episode。

## 2. 当前现场（以进程和结果目录为准）

工作区：/home/hu/文档/ChatGPT/论文/eacr_ws

当前已有一个 results/phase4_final_orchestrator.sh 在运行，并且已有一个 Gazebo。不要再启动第二个 orchestrator 或第二个 Gazebo。先让当前任务自然结束，再检查结果。

截至本笔记生成时，按 results/phase4_final_count_cells.py 统计：

- eacr_static_m0：78/80；缺少：
  - 1320660730:localization
  - 1534671149:planner
  - 另有 37 个无效/不合规 JSON，必须保留。
- eacr_evolving_online_m0：7/80；当前正在运行，已有 31 个无效/不合规 JSON，必须保留。
- eacr_evolving_m20：0/80，尚未开始。
- eacr_evolving_m50：0/80，尚未开始。

当前活动进程可用下面命令查看：

    cd /home/hu/文档/ChatGPT/论文/eacr_ws
    pgrep -af 'phase4_final_orchestrator.sh|run_phase3_gazebo_matrix.py|phase3_gazebo_runner|gz sim|eacr_episode.launch.py'

results/phase4_final_eval_status.json 可能落后于实际进程（曾显示 running_static_m0，而现场已经进入 Online M0），所以每次接手必须重新统计结果目录和检查进程；不要只相信这个状态 JSON。

## 3. 接手后的第一步

1. 不要杀掉当前正在运行的 matrix/Gazebo，也不要另开一套。
2. 等当前 orchestrator 或 matrix 退出后，重新运行四个目录的有效 cell 统计：

    python3 results/phase4_final_count_cells.py eacr_static_m0 "$PWD/results/phase4_final_static_m0"
    python3 results/phase4_final_count_cells.py eacr_evolving_online_m0 "$PWD/results/phase4_final_evolving_online_m0"
    python3 results/phase4_final_count_cells.py eacr_evolving_m20 "$PWD/results/phase4_final_evolving_m20"
    python3 results/phase4_final_count_cells.py eacr_evolving_m50 "$PWD/results/phase4_final_evolving_m50"

3. 如果 Static 仍为 78/80，先用同一冻结命令加 --resume 补齐两个缺失 cell；不能删除旧 JSON，不能手改 JSON。
4. Online M0 的有效 cell 未达到 80 时继续补齐；然后依次完成 M20、M50。
5. 每个方法完成后确认 80 个 distinct (seed, fault_family)，且四个故障族各 20 个。

## 4. 冻结协议

冻结文档：

- docs/EACR_CURSOR_FINAL_EVAL_INSTRUCTIONS.md
- docs/EACR_FINAL_STATISTICAL_SPEC_v1.md

冻结 seed（不包括 544047076）：

    1069364068 683001511 450637390 1207356449 1578549000
    252445555 729528073 1092085222 200776800 1464253601
    365260637 225495283 1725492561 1054169594 1613439514
    1691408245 849115063 1146002680 1534671149 1320660730

故障族固定为：localization、costmap、planner、control。

固定参数：fault_scale=1.5、fault_repetitions=4、goal_timeout_sec=60、experience_prior_mode=weak_shared_m0、use_belief_action_scope=true、resume_experience_state=false。

方法语义：

- Static M0：baseline=eacr_static、M_0、必须带 --no-online-experience-update。
- Online Evolving M0：baseline=eacr_evolving、M_0、不带 --no-online-experience-update，即 online update 为 true。
- Frozen Evolving M20：baseline=eacr_evolving、M_20，带 experience-snapshot-template results/phase4_experience_evolving_full_{checkpoint}.json 和 --no-online-experience-update。
- Frozen Evolving M50：同上，将 checkpoint 改为 M_50。

M20/M50 必须核对：snapshot path 正确、snapshot SHA-256 等于当前 full checkpoint 文件、online_experience_update=false、resume_experience_state=false。

每个有效 cell 必须有：protocol_compliant=true、恰好 4 个 episode、每个 episode episode_evidence_valid=true。无效结果只排除统计，不能删除。

## 5. 不能做的事

- 不要同时运行两个 Gazebo。
- 不要重新训练，不要使用 planner-only checkpoint。
- 不要修改 src/、scripts/、docs/、冻结 protocol/seed manifest 或 full checkpoint。
- 不要复制、手改或删除结果 JSON。
- 不要在四个方法都达到 80/80 前运行最终 confirmatory aggregate。
- 不要把 pilot、训练目录或 544047076 放进最终统计。

## 6. 全部评估完成后的工作

只有四个方法都 80/80 且 20×4 paired keys 完全一致后，才运行：

    python3 scripts/aggregate_phase4_final.py \
      --repo-root /home/hu/文档/ChatGPT/论文/eacr_ws \
      --input results/phase4_final_static_m0 \
      --input results/phase4_final_evolving_online_m0 \
      --input results/phase4_final_evolving_m20 \
      --input results/phase4_final_evolving_m50 \
      --output results/phase4_final_aggregate.json

随后检查/生成论文报告（若脚本存在且四方法门槛已满足）：

    python3 results/phase4_final_make_report.py

统计必须遵守 docs/EACR_FINAL_STATISTICAL_SPEC_v1.md：先按故障族聚合到 cell，再按 seed 等权聚合；以 20 个 seed 为 paired cluster 做 20,000 次 bootstrap；报告 IR、SR/strict joint success、cost、条件 MTTR、useless probe 及各故障族审计。CI 包含 0 时不能宣称确定性优越。

最终还要检查 Git 状态，把原始结果、日志、状态、aggregate、报告和交接文档备份到 GitHub；不要提交任何 PAT 或凭据。

## 7. 重要文件

- 运行说明：docs/EACR_CURSOR_FINAL_EVAL_INSTRUCTIONS.md
- 统计规范：docs/EACR_FINAL_STATISTICAL_SPEC_v1.md
- 矩阵 runner：scripts/run_phase3_gazebo_matrix.py
- 有效 cell 计数：results/phase4_final_count_cells.py
- 统计脚本：scripts/aggregate_phase4_final.py
- 总 orchestrator：results/phase4_final_orchestrator.sh
- 结果目录：results/phase4_final_static_m0/、results/phase4_final_evolving_online_m0/、results/phase4_final_evolving_m20/、results/phase4_final_evolving_m50/
- 训练 full checkpoints：results/phase4_experience_evolving_full_M_0.json、results/phase4_experience_evolving_full_M_20.json、results/phase4_experience_evolving_full_M_50.json

新对话接手时，先阅读本文件和两个 docs/ 文件，再按第 3 节检查现场。
