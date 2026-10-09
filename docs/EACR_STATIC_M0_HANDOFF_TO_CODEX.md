# Static M0 交接：Cursor 已停止，交给 Codex 继续

> 2026-10-04 19:06 CST。用户认为 Cursor 跑得太慢，要求停下来交给 Codex。本文记录停止时的真实状态。Cursor 没有改 `src/`、`scripts/`、`docs/` 或 checkpoint，也没有提交 git。

## 0. 停止时的现场

- 工作区：`/home/hu/文档/ChatGPT/论文/eacr_ws`
- HEAD：`9049b9f Add frozen final aggregate and fix static evaluation command`
- 分支比 `origin/master` 超前，这些 final 结果还没提交。
- Gazebo、`ros2 launch`、`phase3_gazebo_runner`、矩阵进程都已停掉。接手时再查一次，确认没有残留后再起**一个** Gazebo。
- Static M0 合法 cell：**11/80**。另外三个方法还没开始。
- 训练 checkpoint 仍然有效：`results/phase4_experience_evolving_full_manifest.json` 的 `ready=true`，52 cells，208 episodes。不要重跑训练，不要用 planner-only checkpoint。

状态文件：`results/phase4_final_eval_status.json`，当前是 `stopped_for_codex`。

## 1. 已合法的 11 个 cell

目录：`results/phase4_final_static_m0/`

这些结果满足：`protocol_compliant=true`，4 个 episode 都 `episode_evidence_valid=true`，`online_experience_update=false`，`resume_experience_state=false`，`fault_scale=1.5`。

| seed | 已完成故障族 |
|---|---|
| 1069364068 | localization, costmap, planner, control |
| 683001511 | localization, costmap, planner, control |
| 450637390 | localization, costmap, planner |

`450637390` 的 **control 还没有合法结果**。

对应最新合法文件：

```text
1069364068 localization  phase3_gazebo_eacr_static_1069364068_1791106784036017401.json
1069364068 costmap       phase3_gazebo_eacr_static_1069364068_1791107172990217191.json
1069364068 planner       phase3_gazebo_eacr_static_1069364068_1791107339235163806.json
1069364068 control       phase3_gazebo_eacr_static_1069364068_1791107790944289898.json
683001511  localization  phase3_gazebo_eacr_static_683001511_1791108084893617589.json
683001511  costmap       phase3_gazebo_eacr_static_683001511_1791108578162246317.json
683001511  planner       phase3_gazebo_eacr_static_683001511_1791108761193251790.json
683001511  control       phase3_gazebo_eacr_static_683001511_1791109128608660290.json
450637390  localization  phase3_gazebo_eacr_static_450637390_1791109385790605087.json
450637390  costmap       phase3_gazebo_eacr_static_450637390_1791109779446935064.json
450637390  planner       phase3_gazebo_eacr_static_450637390_1791110068131432975.json
```

`--resume` 会跳过这 11 个，因为它们 `protocol_compliant=true` 且 `online_experience_update=false`。

## 2. 必须保留的无效 JSON

不要删除，也不要当成完成。

1. `phase3_gazebo_eacr_static_1069364068_1791105997391791021.json`  
   第一次 Static 尝试，**没有** `--no-online-experience-update`。`online_experience_update=true`，`protocol_compliant=false`。4 个 episode 的 evidence 是 `[true, false, true, true]`，第 2 个 `inject_failed`。后来同一 cell 已有合法重跑，这份只作审计。

2. `phase3_gazebo_eacr_static_450637390_1791110620558460456.json`  
   control，`online_experience_update=false`，但不合法。4 个 episode evidence 全为 false。原因：`navigation_timeout, inject_failed, inject_failed, inject_failed`。

3. `phase3_gazebo_eacr_static_450637390_1791111208396633656.json`  
   同一 control cell 的第二次失败。evidence 全为 false，4 次都是 `inject_failed`。

停止时，第三次 control 重试刚开始约 2 分钟，还没写出新 JSON。进程已杀掉，所以这个 cell 仍然缺失，`--resume` 会再跑它。

## 3. 还没跑的 cell

缺 69 个：`450637390/control`，以及下面这些 seed 的 localization、costmap、planner、control。

```text
1207356449, 1578549000, 252445555, 729528073, 1092085222,
200776800, 1464253601, 365260637, 225495283, 1725492561,
1054169594, 1613439514, 1691408245, 849115063, 1146002680,
1534671149, 1320660730
```

`1207356449/localization` 曾经跑满 600 秒超时，没有留下合法 JSON。

## 4. 调度脚本的超时 bug

`scripts/run_phase3_gazebo_matrix.py` 在 cell 超时后会崩，Cursor 按约定没有改它。

现象：`1207356449` localization 的 `communicate(timeout=600)` 超时后，再 `communicate(timeout=10)` 也超时，接着：

```text
TypeError: can't concat str to bytes
```

位置在超时处理里 `stdout += stdout_tail`。`Popen(..., text=True)` 之后，超时异常路径上拿到的 tail 可能是 bytes。异常从 `main()` 抛出，整个矩阵退出，后面的 cell 不会再跑。

Gazebo 本身当时还活着，没有 Bus error。Cursor 随后用同一个 Gazebo 做了 `--resume`，跳过了 11 个合法 cell，并重新开始 `450637390/control`。这次交接前该进程已停止。

继续长跑之前建议先修这个超时拼接，否则下一次 600 秒超时还会把矩阵打崩。修完再跑，不要靠反复人工 `--resume`。

## 5. 继续命令

先确认没有残留进程，再只起一个 Gazebo，`fault_scale=1.5`。Static 命令必须带 `--no-online-experience-update` 和 `--resume`：

```bash
cd /home/hu/文档/ChatGPT/论文/eacr_ws
source scripts/source_eacr.sh
python3 scripts/run_phase3_gazebo_matrix.py \
  --baseline eacr_static \
  --seed 1069364068 --seed 683001511 --seed 450637390 \
  --seed 1207356449 --seed 1578549000 --seed 252445555 \
  --seed 729528073 --seed 1092085222 --seed 200776800 \
  --seed 1464253601 --seed 365260637 --seed 225495283 \
  --seed 1725492561 --seed 1054169594 --seed 1613439514 \
  --seed 1691408245 --seed 849115063 --seed 1146002680 \
  --seed 1534671149 --seed 1320660730 \
  --fault-family localization --fault-family costmap \
  --fault-family planner --fault-family control \
  --fault-repetitions 4 --goal-timeout-sec 60 \
  --experience-checkpoint M_0 \
  --experience-prior-mode weak_shared_m0 \
  --no-online-experience-update \
  --use-belief-action-scope --fault-scale 1.5 \
  --result-dir results/phase4_final_static_m0 \
  --timeout-sec 600 --retries 1 --resume
```

完成判据不是退出码 0，而是 80 个 distinct `(seed, fault_family)` 都满足：

```text
protocol_compliant == true
len(episodes) == 4
每个 episode_evidence_valid == true
online_experience_update == false
resume_experience_state == false
fault_scale == 1.5
```

Online Evolving M0 不要加 `--no-online-experience-update`。M20/M50 要加，并且 snapshot 模板必须是 `results/phase4_experience_evolving_full_{checkpoint}.json`。不要用 planner-only 的 `phase4_experience_evolving_M_20.json` / `M_50.json`。

## 6. 日志和未提交文件

```text
results/phase4_final_gazebo_static_m0.log
results/phase4_final_gazebo_static_m0_attempt1.log
results/phase4_final_eval_status.json
results/phase4_final_static_m0/
```

`attempt1` 是第一次没关在线更新时的 Gazebo 日志副本。当前 `phase4_final_gazebo_static_m0.log` 是后来那次 `fault_scale=1.5` 的仿真日志。

未提交：`results/phase2_fault_injector.events.jsonl` 也有修改，那是仿真运行留下的，不是这次评估要改的协议文件。不要把 token 写进仓库。

## 7. 不要做的事

1. 不要删除任何已有 JSON。
2. 不要把 `protocol_compliant=false` 的文件当成 `--resume` 可跳过的结果。
3. 不要同时开两个 Gazebo。
4. 不要把 `544047076` 加回测试集。
5. 不要在 Static 上省略 `--no-online-experience-update`。
6. 不要在 80 个合法 cell 齐之前跑最终 aggregate，也不要把 pilot 或训练目录混进去。
