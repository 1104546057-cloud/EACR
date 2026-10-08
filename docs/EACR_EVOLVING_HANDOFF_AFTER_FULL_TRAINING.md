# EACR-Evolving 训练完成：交给下一位执行代理

> 这是 2026-10-04 的交接笔记，接在 `EACR_EVOLVING_HANDOFF_CURSOR.md` 之后。先读本文件，再读旧交接文档的协议和论文边界。本文件记录的是仓库里刚刚核对过的真实状态，不是论文结论。

## 0. 现在停在哪里

- 工作区：`/home/hu/文档/ChatGPT/论文/eacr_ws`
- 环境：这台机器是 Ubuntu，ROS 2 Jazzy。不要把本工作区当成 Ubuntu 20.04 / ROS Foxy 来跑。
- 训练矩阵已经完成：**52/52**。
- 四故障族完整 checkpoint 已经生成，`ready == true`。
- planner-only 的旧 checkpoint 还在，没有被覆盖，`ready` 仍是 `false`。
- 20-seed 确认性评估还没有开始，没有 `results/phase4_final_*` 目录。
- Gazebo、`ros2 launch`、`phase3_gazebo_runner` 都已停止。开始下一次评估前先再查一次进程。
- 这些新结果和 `scripts/run_phase3_gazebo_matrix.py` 的修改都还没提交。本地 `master` 最后一次提交仍是 `170aded`。不要假定 GitHub 上已经有这次训练。

最权威的完成标记：

```text
results/phase4_experience_evolving_full_manifest.json
  ready == true
  feedback_episodes_applied == 208
  unique_training_cells == 52
  retained_training_episodes == 208
  coverage_by_family == localization/costmap/planner/control 各 13
  checkpoints == M_0, M_20, M_50
```

状态文件 `results/phase4_training_full_status.json` 现在是 `training_complete`，`missing_training_cells` 为空。接手时仍要用下面的命令重新数 JSON，不要只信状态文件。

```bash
cd /home/hu/文档/ChatGPT/论文/eacr_ws
python3 - <<'PY'
import glob, json, collections
valid=set()
for path in glob.glob('results/phase4_evolving_training_full/phase3_gazebo_eacr_evolving_*.json'):
    data=json.load(open(path))
    rows=data.get('episodes') or []
    if (data.get('protocol_compliant') is True and len(rows)==4
        and all(r.get('episode_evidence_valid') for r in rows)):
        valid.add((int(data['seed']), rows[0]['fault_family']))
print(len(valid), dict(collections.Counter(f for _,f in valid)))
assert len(valid)==52
PY
```

同时确认没有残留仿真：

```bash
ps -eo pid,etime,cmd | rg 'gz sim -r|ros2 launch eacr_sim|phase3_gazebo_runner|run_phase3_gazebo_matrix' || true
```

没有进程时，一次只启动一个 Gazebo。

---

## 1. 这次接手完成了什么

旧交接文档停在 23/52，`status` 写成 `stopped_for_quota`。现场当时已经变成 `running_resume`，但进程已经死了：Gazebo 在 `results/phase4_training_full_gazebo_resume.log` 里 Bus error 退出。那次 resume 还误重跑了已经合法的 planner cell。

本次实际做了四件事：

1. 修正 `--resume`，让已经合法的 cell 不再被重跑。
2. 在单个 Gazebo 上补齐缺失训练 cell，从 23/52 跑到 52/52。
3. 对反复失败的格子只重试，不改写、不删除失败 JSON。
4. 用全部四族训练生成 `phase4_experience_evolving_full_*`，不覆盖 planner-only checkpoint。

没有做的事：20-seed × 4 故障族 × 4 方法的确认性评估，以及最终 aggregate。

---

## 2. `--resume` 修了什么

文件：`scripts/run_phase3_gazebo_matrix.py`

旧逻辑要求 `resume_experience_state == false`。早期 planner JSON 里这个字段是 `null`，所以 `--resume` 不承认它们，会把已经合法的 planner cell 再跑一遍。`20310001` planner 因此多了一个合法重跑，`20310002` planner 多了一个不合法重跑。

现在跳过条件和 checkpoint builder 一致：缺失或 `null` 都当成 `false`。

```python
stored_resume = bool(item.get('resume_experience_state'))
stored_resume == bool(args.resume_experience_state)
```

函数名是 `record_matches_resume`。矩阵还会打印 `skip existing valid ...` 和 `start ...`。继续跑确认性评估时必须使用这份脚本，不要退回旧比较。

这次修改还没提交。

---

## 3. 训练结果

目录：`results/phase4_evolving_training_full/`

- 13 个训练 seed：`20310001`–`20310013`
- 4 个故障族：`localization`、`costmap`、`planner`、`control`
- 每个 cell 4 个重复 episode
- 训练参数：`fault_scale=1.0`，`prior_mode=weak_shared_m0`，`use_belief_action_scope=true`，`online_experience_update=true`，`resume_experience_state=false`，`experience_checkpoint=M_0`

builder 从每个 `(seed, fault_family)` 里保留 `run_id` 最新的那份合法 JSON。因此 `20310001` planner 用的是后来那份合法重跑：

```text
phase3_gazebo_eacr_evolving_20310001_1791033804658189996.json
```

不是更早的 `1790950998626337146`。两份都合法；builder 的规则是留最新的一份。不要手改这个选择。

不合法尝试一共被 builder 排除了 14 个，原因都是 `paired episode evidence incomplete`。它们必须保留，不能删除，也不能拿去当训练反馈。反复失败过、最后有合法版本的格子：

| cell | 失败情况 | 最终合法文件 |
|---|---|---|
| `20310008` costmap | 旧 Gazebo 上两次 evidence 不完整；换仿真前又失败过一次 | `...20310008_1791050429980788267.json` |
| `20310009` localization | 两次 evidence 不完整 | `...20310009_1791050764185317618.json` |
| `20310010` control | 连续多次失败。有的是某个 episode `inject_failed`，最后一次明确是 `Gazebo model reset failed: Service call timed out` | `...20310010_1791052759894997820.json` |

`20310010` control 是在停掉运行了约 4 小时的旧 Gazebo、重新启动一个干净仿真之后才通过的。以后如果重置服务超时或注入失败反复出现，先确认只有一个 Gazebo，再停掉整个 launch 进程树并重启一个，然后只 `--resume` 缺失 cell。不要同时启动第二个 Gazebo。

停旧仿真时，只杀 `ros2 launch` 不够，`gz sim`、`component_container_isolated`、`nav2_bringup_gate`、`episode_manager`、`episode_reset`、`fault_injector`、`eacr_localization_loop`、`phase2_episode_runner` 可能变成孤儿进程。重启前必须确认这些都不在。

---

## 4. Checkpoint

### 4.1 要用的完整 checkpoint

```text
results/phase4_experience_evolving_full_M_0.json
results/phase4_experience_evolving_full_M_20.json
results/phase4_experience_evolving_full_M_50.json
results/phase4_experience_evolving_full_manifest.json
```

生成命令已经跑过，不要为了“再生成一次”覆盖它们，除非训练 JSON 本身变了：

```bash
python3 scripts/build_phase3_experience_checkpoints.py \
  --results-dir results/phase4_evolving_training_full \
  --output-prefix results/phase4_experience_evolving_full \
  --prior-mode weak_shared_m0 \
  --protocol results/phase3_evolving_advantage_protocol.json
```

确认性评估里 M20/M50 的 snapshot 模板必须是：

```text
results/phase4_experience_evolving_full_{checkpoint}.json
```

### 4.2 不要拿来做最终结论的 planner-only checkpoint

```text
results/phase4_experience_evolving_M_0.json
results/phase4_experience_evolving_M_20.json
results/phase4_experience_evolving_M_50.json
results/phase4_experience_evolving_manifest.json
```

这份 manifest 仍是 `ready: false`，只有 planner 13 个 cell、52 个 episode。它只能证明早期机制和加载链路。最终测试不要把 snapshot 指到这些文件。

---

## 5. 协议和 seed：没有改

- 协议：`results/phase3_evolving_advantage_protocol.json`
- revision：`v0.3_pilot_exposure_amendment`
- SHA-256：`0c299464d2fabc24f96446153a60c3d07d2f951f4d31e14137fe17e9d24b2910`
- seed manifest：`results/phase3_evolving_advantage_seed_manifest.json`

最终测试 seed 仍是这 20 个，不要重抽，不要把暴露过的 `544047076` 加回去：

```text
1069364068, 683001511, 450637390, 1207356449, 1578549000,
252445555, 729528073, 1092085222, 200776800, 1464253601,
365260637, 225495283, 1725492561, 1054169594, 1613439514,
1691408245, 849115063, 1146002680, 1534671149, 1320660730
```

`544047076` 仍在 `pilot_seeds_excluded` 里，不在 `evaluation_seeds` 里。它只属于 checkpoint-load pilot。

确认性评估参数：

```text
fault_scale = 1.5
fault_repetitions = 4
prior_mode = weak_shared_m0
use_belief_action_scope = true
```

Static 与 Evolving 必须使用同一批 seed、同一故障序列、同一动作库和同一过滤器。不要为了让 Evolving 更好看而改 Static 的先验、范围、seed、强度或重复次数。

---

## 6. 下一位要做的事：确认性评估

这是长任务：20 seeds × 4 fault families × 4 methods = 320 cells，每个 cell 4 个 episode。一次只跑一个方法目录，一次只起一个 Gazebo。命令返回 0 不算完成，必须检查每个 JSON 的 `protocol_compliant` 和四条 `episode_evidence_valid`。

先启动 Gazebo：

```bash
cd /home/hu/文档/ChatGPT/论文/eacr_ws
source scripts/source_eacr.sh
ros2 launch eacr_sim eacr_episode.launch.py \
  headless:=True use_rviz:=False fault_scale:=1.5 \
  > results/phase4_final_gazebo.log 2>&1
```

四个结果目录分开：

```text
results/phase4_final_static_m0/
results/phase4_final_evolving_online_m0/
results/phase4_final_evolving_m20/
results/phase4_final_evolving_m50/
```

Static：

```bash
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
  --fault-repetitions 4 \
  --experience-prior-mode weak_shared_m0 \
  --use-belief-action-scope \
  --fault-scale 1.5 \
  --result-dir results/phase4_final_static_m0 \
  --timeout-sec 600 --retries 1 --resume
```

Online Evolving M0：同样的 20 个 seed 和四类故障，加上 `--baseline eacr_evolving --experience-checkpoint M_0`，结果目录 `results/phase4_final_evolving_online_m0`。不要加 `--no-online-experience-update`，也不要加载 M20/M50 snapshot。

M50：

```bash
python3 scripts/run_phase3_gazebo_matrix.py \
  --baseline eacr_evolving \
  --seed 1069364068 --seed 683001511 --seed 450637390 \
  --seed 1207356449 --seed 1578549000 --seed 252445555 \
  --seed 729528073 --seed 1092085222 --seed 200776800 \
  --seed 1464253601 --seed 365260637 --seed 225495283 \
  --seed 1725492561 --seed 1054169594 --seed 1613439514 \
  --seed 1691408245 --seed 849115063 --seed 1146002680 \
  --seed 1534671149 --seed 1320660730 \
  --fault-family localization --fault-family costmap \
  --fault-family planner --fault-family control \
  --fault-repetitions 4 \
  --experience-checkpoint M_50 \
  --experience-prior-mode weak_shared_m0 \
  --use-belief-action-scope \
  --fault-scale 1.5 \
  --experience-snapshot-template \
    'results/phase4_experience_evolving_full_{checkpoint}.json' \
  --no-online-experience-update \
  --result-dir results/phase4_final_evolving_m50 \
  --timeout-sec 600 --retries 1 --resume
```

M20 只把 checkpoint 和结果目录改成 M20。每个 M20/M50 结果必须满足：

```text
experience_checkpoint == M_20 或 M_50
experience_snapshot_path 非空
experience_snapshot_sha256 与 full checkpoint 文件一致
online_experience_update == false
resume_experience_state == false
```

四个目录都达到每个方法 80 cells、320 episodes 之后才聚合：

```bash
python3 scripts/aggregate_phase3_evolving_advantage.py \
  --input results/phase4_final_static_m0 \
  --input results/phase4_final_evolving_online_m0 \
  --input results/phase4_final_evolving_m20 \
  --input results/phase4_final_evolving_m50 \
  --output results/phase4_final_evolving_advantage_aggregate.json
```

不要把下面任何一个目录放进这次 aggregate：

```text
results/phase3_evolving_advantage_pilot*
results/phase4_checkpoint_load_pilot/
results/phase4_evolving_training_full/
results/phase4_evolving_training_planner/
```

---

## 7. 论文边界

现在可以写的是：四故障族训练矩阵已经完成，完整 M0/M20/M50 checkpoint 来自 52 个 cell、208 个反馈 episode。pilot 仍然只说明机制和 checkpoint 加载链路能在 Gazebo 里跑。

不能写：

- Evolving 在确认性测试上优于 Static。确认性测试还没跑。
- Static 必然失败，或某个 `0/4` stress cell 代表全局 Static。
- planner-only M50 是完整训练。
- 弱先验是完全无知识初始化。
- pilot 或单个 cell 是最终显著性结果。

如果最终配对置信区间包含 0，或者优势只集中在一个故障族，要如实写。不要删 seed、改先验或改重复次数。

---

## 8. 不要做的事

1. 不要删除任何 JSON、日志、失败尝试或 dispatch 文件。
2. 不要覆盖 `phase3_stage_gate.json`、旧 phase-3 aggregate、planner-only checkpoint。
3. 不要重新抽取最终测试 seed，不要把 `544047076` 放回去。
4. 不要把 pilot 并进最终 aggregate。
5. 不要用 planner-only M20/M50 当确认性测试的 snapshot。
6. 不要手改 episode 的 success、selected action、cost 或 SHA。
7. 不要在同一个 ROS domain 同时开两个 Gazebo。
8. 不要把命令退出码 0 当成 cell 成功。
9. 不要为了结果更好看而让 Static 和 Evolving 使用不同配置。
10. 不要把 `phase3_experience_eacr_evolving_*.json` 当成 checkpoint。那是在线经验状态，训练时 `resume_experience_state=false`，确认性测试也不要从这些状态热启动。
11. 改协议就必须升 revision，并记下旧 SHA 和新 SHA。这次没有改协议。

---

## 9. Git

仓库：`/home/hu/文档/ChatGPT/论文/eacr_ws`  
远端：`origin = https://github.com/1104546057-cloud/EACR.git`  
当前已提交的 HEAD：`170aded Document GitHub backup and authentication handoff`

未提交内容包括：

- `scripts/run_phase3_gazebo_matrix.py` 的 `--resume` 修复
- `results/phase4_experience_evolving_full_*` 四个新 checkpoint 文件
- `results/phase4_training_full_status.json`
- `results/phase4_evolving_training_full/` 里新增的训练 JSON、失败 JSON 和经验状态文件
- 本交接笔记

接手的人如果要备份，先提交这些审计文件，再推送。不要把 token、密码或私钥写进仓库、remote URL 或文档。不要覆盖已有结果来制造一个“干净 diff”。
