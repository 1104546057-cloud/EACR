# EACR-Evolving 经验演化评估：Cursor 接手工作文档

> 这是给下一位执行代理（Cursor）的工作交接文档。请先完整阅读本文件，再执行任何实验。本文档记录的是当前工作区的真实状态，不代表最终论文结论。

## 0. 工作区与当前停止状态

- 工作区：`/home/hu/文档/ChatGPT/论文/eacr_ws`
- 当前环境：ROS 2 Jazzy，当前机器是与 Ubuntu 24.04/Jazzy 配套的环境。
- 用户另有一块 Ubuntu 20.04 的 64G 显存板子，但本轮没有迁移到那块板子；不要直接把当前 Jazzy 工作区当作 20.04/ROS Foxy 环境运行。
- 训练和 Gazebo 已按用户要求停止；停止时没有残留 `ros2 launch`、`gz sim` 或 `phase3_gazebo_runner` 进程。
- 用户停止原因：当前账户额度不足，不是实验失败。
- 所有已经落盘且通过协议校验的 JSON 结果必须保留，不要删除或覆盖。

最权威的当前状态文件：

- `results/phase4_training_full_status.json`
- `results/phase4_training_status.json`
- `results/phase4_evolving_training_full/`
- `results/phase4_evolving_training_planner/`

当前状态文件的关键值：

```json
{
  "status": "stopped_for_quota",
  "expected_training_cells": 52,
  "valid_training_cells_across_preserved_dirs": 23,
  "valid_training_cells_by_family": {
    "planner": 13,
    "localization": 4,
    "costmap": 3,
    "control": 3
  },
  "checkpoint_ready": false
}
```

完整训练矩阵应为 `13 training seeds × 4 fault families = 52 cells`。一个 cell 是一个 seed、一个故障族、4 次重复故障的完整 Gazebo 运行。

---

## 1. 原始研究目标

目标是建立一套可以写入论文、能够公平检验 EACR-Evolving 相对 EACR-Static 的经验演化评估：

1. 训练集与独立测试集分离；
2. 训练反馈形成 M0/M20/M50 checkpoint；
3. 测试阶段真正加载 checkpoint，并记录 snapshot 路径和 SHA-256；
4. 每个故障族重复出现 4 次，使在线演化有机会改变后续动作；
5. Static 与 Evolving 使用相同 seed、相同故障序列、相同动作库和相同过滤器；
6. 使用预先冻结的真实随机测试 seed；
7. 同时报告干预恢复、持续恢复、MTTR、干预成本和无效探测；
8. 按 seed×故障族配对计算差值与置信区间；
9. 最终结果必须覆盖四类故障，不能用 planner-only pilot 代替完整结论。

研究目标不是通过挑选场景制造 Static 失败。当前 pilot 中出现过 Static `0/4`，但完整 pilot aggregate 中 Static 并非全为零；论文必须展示全部 cell、分母和分层结果。

---

## 2. 协议文件与 seed 规则

### 2.1 主协议

- `results/phase3_evolving_advantage_protocol.json`
- `docs/EACR_Evolving_优势评估协议_v0.1.md`
- 协议当前 revision：`v0.3_pilot_exposure_amendment`
- 当前协议 SHA-256：
  `0c299464d2fabc24f96446153a60c3d07d2f951f4d31e14137fe17e9d24b2910`

协议中的固定训练 seed：

```text
20310001, 20310002, 20310003, 20310004, 20310005,
20310006, 20310007, 20310008, 20310009, 20310010,
20310011, 20310012, 20310013
```

故障族：

```text
localization, costmap, planner, control
```

每个故障族重复 4 次。

训练参数：

```text
fault_scale = 1.0
prior_mode = weak_shared_m0
use_belief_action_scope = true
online_experience_update = true
resume_experience_state = false
experience_checkpoint = M_0
```

最终确认性测试参数：

```text
fault_scale = 1.5
fault_repetitions = 4
prior_mode = weak_shared_m0
use_belief_action_scope = true
```

### 2.2 最终测试 seed 的重要修订

最初的最终测试清单中有 `544047076`。这个 seed 后来被用于一次真实 planner/M50 checkpoint-load pilot，Static 和 Evolving 的结果已经被观察，因此它不能继续作为盲的确认性测试 seed。

处理方式已经写入协议：

- `544047076` 被排除；
- 用 `secrets.SystemRandom.randrange(100000000, 2000000000)` 抽取的 `1069364068` 替换；
- 替换不依据 pilot 结果的方向或大小；
- 最终测试仍保持 20 个 seed；
- 该修订记录在 `results/phase3_evolving_advantage_seed_manifest.json` 和协议文档中。

必须使用当前 manifest，不得恢复旧清单，也不得重新抽取 seed：

- `results/phase3_evolving_advantage_seed_manifest.json`

当前最终测试 seed 为：

```text
1069364068, 683001511, 450637390, 1207356449, 1578549000,
252445555, 729528073, 1092085222, 200776800, 1464253601,
365260637, 225495283, 1725492561, 1054169594, 1613439514,
1691408245, 849115063, 1146002680, 1534671149, 1320660730
```

禁止把训练 seed、pilot seed 或暴露过的 `544047076` 放入最终确认性推断。

---

## 3. 当前结果目录的真实含义

### 3.1 Planner 训练目录：已完成但不完整

目录：

```text
results/phase4_evolving_training_planner/
```

这里有 13 个合法 planner cell，每个 4 个 episode，共 52 个训练反馈 episode：

```text
coverage_by_family = {
  "localization": 0,
  "costmap": 0,
  "planner": 13,
  "control": 0
}
```

对应的 planner 训练 seed 全部为 `20310001..20310013`。seed `20310011` 曾经有两个无效尝试，后来用修复后的 runner 成功重跑；只使用最后那个 protocol-compliant JSON。

目录中可能保留两个旧的无效 JSON。它们不能删除，也不能纳入训练反馈；builder 会根据 `protocol_compliant`、episode evidence 和参数一致性排除它们。

### 3.2 统一训练目录：当前 23/52

目录：

```text
results/phase4_evolving_training_full/
```

该目录中：

- 13 个 planner 结果最初从 planner 目录建立过符号链接；在提交到 GitHub 前已物化为普通 JSON 文件，避免 clone 后出现绝对路径断链；
- 新增的 localization/costmap/control 结果是实际 Gazebo 运行得到的 JSON；
- 当前有效 cell 共 23 个：
  - planner：13
  - localization：4
  - costmap：3
  - control：3
- 其余 29 个 cell 尚未完成；当前不应生成 `ready: true` 的完整 checkpoint。

用下面命令重新确认当前覆盖，不要只看旧状态文件：

```bash
cd /home/hu/文档/ChatGPT/论文/eacr_ws
python3 - <<'PY'
import glob, json, collections
valid = set()
for path in glob.glob('results/phase4_evolving_training_full/phase3_gazebo_eacr_evolving_*.json'):
    try:
        data = json.load(open(path))
    except Exception:
        continue
    rows = data.get('episodes', [])
    if (data.get('protocol_compliant') is True
        and len(rows) == 4
        and all(row.get('episode_evidence_valid') for row in rows)):
        valid.add((int(data['seed']), rows[0]['fault_family']))
print('valid cells:', len(valid))
print('by family:', collections.Counter(family for _, family in valid))
print('cells:', sorted(valid))
PY
```

### 3.3 当前已有 checkpoint：只能作为 planner pilot

以下文件存在：

```text
results/phase4_experience_evolving_M_0.json
results/phase4_experience_evolving_M_20.json
results/phase4_experience_evolving_M_50.json
results/phase4_experience_evolving_manifest.json
```

它们由 planner-only 的 52 个反馈 episode 构成，manifest 的 `ready` 必须保持 `false`。这些文件可以用于机制和加载链路 pilot，但不能用于宣称完整四故障族最终结果。

完成四类训练后，应使用新的 output prefix，例如：

```text
results/phase4_experience_evolving_full_M_0.json
results/phase4_experience_evolving_full_M_20.json
results/phase4_experience_evolving_full_M_50.json
results/phase4_experience_evolving_full_manifest.json
```

不要覆盖 planner-only checkpoint，以便保留审计轨迹。

---

## 4. 已完成的 pilot 证据

### 4.1 Online Evolving M0 pilot

聚合文件：

```text
results/phase3_evolving_advantage_pilot_aggregate.json
results/phase3_evolving_advantage_pilot_report.md
```

包含 4 个 paired cells、16 个 episode/方法：

| 指标 | Static M0 | Evolving online M0 | paired delta |
|---|---:|---:|---:|
| intervention recovery | 0.250 | 0.563 | +0.313 |
| sustained recovery | 0.250 | 0.500 | +0.250 |
| useless probe | 0.750 | 0.438 | -0.313 |
| mean intervention cost | 0.240 | 0.363 | +0.123 |

这是适应机制的 pilot 证据，不是最终统计结论。Evolving 成功更多，但成本也更高，论文中必须保留这一点。

### 4.2 M50 checkpoint-load pilot

文件：

```text
results/phase4_checkpoint_load_pilot_report.md
results/phase4_checkpoint_load_pilot_aggregate.json
results/phase4_checkpoint_load_pilot/
```

一个 held-out planner stress cell，seed `544047076`：

- Static：intervention recovery `0/4`，sustained recovery `0/4`；
- Evolving M50：intervention recovery `4/4`，sustained recovery `3/4`；
- snapshot 路径和 SHA 已核对；
- M50 测试阶段 `online_experience_update=false`。

这个 seed 已从最终确认性测试中排除。该 pilot 只用于证明 checkpoint 真正被加载和机制能运行，不得并入最终置信区间。

---

## 5. 已修改的实现与已修复问题

### 5.1 ExperienceModel

文件：

```text
src/eacr_core/eacr_core/experience.py
```

已经加入：

```python
ExperienceModel.seed_weak_prior(...)
ExperienceModel.from_snapshot(...)
```

weak_shared_m0 的恢复动作偏好：

```text
localization_drift -> relocalize_amcl
costmap_blockage  -> clear_costmaps
planner_failure   -> reconfigure_planner
controller_failure -> reconfigure_controller
```

Static 与 Evolving 的 M0 必须使用完全相同的 weak prior。

### 5.2 Gazebo runner

文件：

```text
src/eacr_sim/eacr_sim/phase3_gazebo_runner.py
```

已实现或修复：

- 从 snapshot 实际加载 M20/M50；
- 缺少 M20/M50 snapshot 时抛错；
- 结果记录 snapshot path 和 SHA-256；
- 测试阶段可关闭 online update；
- `resume_experience_state=false` 时不读取旧运行状态；
- 重复同类故障序列；
- action scope 过滤；
- fault scale 写入记录并传入 fault injector；
- online update 使用正确的 `self._experience_context`；
- 修复了结果字典引用局部 `snapshot_path` 导致的 NameError；
- `experience_updated_online` 会记录每个 episode 是否更新。

训练结果必须满足：

```text
protocol_compliant == true
len(episodes) == 4
每个 episode_evidence_valid == true
experience_prior_mode == weak_shared_m0
fault_scale == 1.0
fault_repetitions == 4
resume_experience_state == false
experience_updated_online == true
```

### 5.3 Matrix dispatcher

文件：

```text
scripts/run_phase3_gazebo_matrix.py
```

当前已加入：

- 每个 cell 使用独立 process group；
- timeout 时清理整个 ROS 子进程组，防止 stale runner；
- `--resume` 现在会检查完整配置一致性，不只看 `protocol_compliant`：
  - episode 数量和 evidence；
  - checkpoint；
  - prior mode；
  - action scope；
  - fault scale；
  - repetitions；
  - online update；
  - resume state；
  - snapshot path。

每次继续前都先确认没有 stale 进程：

```bash
ps -eo pid,ppid,stat,etime,cmd | rg \
  'run_phase3_gazebo_matrix|phase3_gazebo_runner|ros2 launch eacr_sim|gz sim -r' || true
```

如果确实没有进程，再启动一个 Gazebo。不要同时启动多个相同 ROS domain 的 Gazebo。

### 5.4 Aggregator

文件：

```text
scripts/aggregate_phase3_evolving_advantage.py
```

已经修复 M20/M50 method identifier：

```text
eacr_evolving_m20
eacr_evolving_m50
```

不要把 pilot 目录和最终确认性目录混在同一次 aggregate 中。

---

## 6. Cursor 下一步的准确执行顺序

### Step A：恢复前检查

```bash
cd /home/hu/文档/ChatGPT/论文/eacr_ws
source scripts/source_eacr.sh
python3 -m py_compile \
  scripts/run_phase3_gazebo_matrix.py \
  scripts/build_phase3_experience_checkpoints.py \
  scripts/aggregate_phase3_evolving_advantage.py \
  src/eacr_sim/eacr_sim/phase3_gazebo_runner.py
```

再次确认没有运行中的 Gazebo 或 runner。不要删除已有 JSON。

### Step B：继续训练矩阵

先启动一个 Gazebo：

```bash
source scripts/source_eacr.sh
ros2 launch eacr_sim eacr_episode.launch.py \
  headless:=True use_rviz:=False fault_scale:=1.0 \
  > results/phase4_training_full_gazebo.log 2>&1
```

然后在另一个终端运行以下命令。它会跳过统一目录里已经通过完整配置检查的 23 个 cell，只运行缺失 cell：

```bash
source scripts/source_eacr.sh
python3 scripts/run_phase3_gazebo_matrix.py \
  --baseline eacr_evolving \
  --seed 20310001 --seed 20310002 --seed 20310003 \
  --seed 20310004 --seed 20310005 --seed 20310006 \
  --seed 20310007 --seed 20310008 --seed 20310009 \
  --seed 20310010 --seed 20310011 --seed 20310012 \
  --seed 20310013 \
  --fault-family localization \
  --fault-family costmap \
  --fault-family planner \
  --fault-family control \
  --fault-repetitions 4 \
  --experience-prior-mode weak_shared_m0 \
  --use-belief-action-scope \
  --fault-scale 1.0 \
  --result-dir results/phase4_evolving_training_full \
  --timeout-sec 600 \
  --retries 1 \
  --resume
```

矩阵完成的判据不是命令返回 0，而是 52 个 distinct `(seed, fault_family)` 都有合法 JSON。若某个 cell timeout，先检查 process group 是否已清理，再只依赖 `--resume` 重跑；不要手工伪造或复制 episode。

### Step C：训练覆盖审计

完成后运行：

```bash
python3 - <<'PY'
import glob, json, collections
valid = set()
for path in glob.glob('results/phase4_evolving_training_full/phase3_gazebo_eacr_evolving_*.json'):
    try:
        data = json.load(open(path))
    except Exception:
        continue
    rows = data.get('episodes', [])
    if (data.get('protocol_compliant') is True
        and len(rows) == 4
        and all(row.get('episode_evidence_valid') for row in rows)):
        valid.add((int(data['seed']), rows[0]['fault_family']))
print('valid cells:', len(valid))
print('by family:', collections.Counter(f for _, f in valid))
assert len(valid) == 52
assert collections.Counter(f for _, f in valid) == {
    'localization': 13, 'costmap': 13, 'planner': 13, 'control': 13
}
PY
```

### Step D：生成完整训练 checkpoint

不要覆盖 planner-only checkpoint：

```bash
python3 scripts/build_phase3_experience_checkpoints.py \
  --results-dir results/phase4_evolving_training_full \
  --output-prefix results/phase4_experience_evolving_full \
  --prior-mode weak_shared_m0 \
  --protocol results/phase3_evolving_advantage_protocol.json
```

验收：

```text
results/phase4_experience_evolving_full_manifest.json:
  ready == true
  feedback_episodes_applied == 208
  unique_training_cells == 52
  retained_training_episodes == 208
  coverage_by_family == 13 for all four families
  checkpoints includes M_0, M_20, M_50
```

208 是 `52 cells × 4 repeated episodes`。M20/M50 必须来自完整四故障训练顺序，不能从 planner-only 目录拼接为最终 checkpoint。

### Step E：最终确认性评估（后续任务）

最终测试矩阵是 20 seeds × 4 fault families × 4 methods = 320 cells，每个 cell 4 episodes。它是长任务，可以在有足够额度或 64G 机器上执行。

四个方法目录建议分开：

```text
results/phase4_final_static_m0/
results/phase4_final_evolving_online_m0/
results/phase4_final_evolving_m20/
results/phase4_final_evolving_m50/
```

所有方法都必须使用当前 manifest 的 20 个测试 seed和四类故障。Static 命令示例：

```bash
python3 scripts/run_phase3_gazebo_matrix.py \
  --baseline eacr_static \
  --seed 1069364068 ...其余19个当前manifest seed... \
  --fault-family localization --fault-family costmap \
  --fault-family planner --fault-family control \
  --fault-repetitions 4 \
  --experience-prior-mode weak_shared_m0 \
  --use-belief-action-scope \
  --fault-scale 1.5 \
  --result-dir results/phase4_final_static_m0 \
  --timeout-sec 600 --retries 1 --resume
```

Online M0 示例：

```bash
python3 scripts/run_phase3_gazebo_matrix.py \
  --baseline eacr_evolving \
  ...相同20个seed和四类fault-family... \
  --experience-checkpoint M_0 \
  --experience-prior-mode weak_shared_m0 \
  --use-belief-action-scope \
  --fault-scale 1.5 \
  --result-dir results/phase4_final_evolving_online_m0 \
  --timeout-sec 600 --retries 1 --resume
```

M20/M50 示例：

```bash
python3 scripts/run_phase3_gazebo_matrix.py \
  --baseline eacr_evolving \
  ...相同20个seed和四类fault-family... \
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

M20 只需把 checkpoint 和 result directory 改为 M20 对应名称。每个 M20/M50 结果必须检查：

```text
experience_checkpoint == M_20 或 M_50
experience_snapshot_path 非空
experience_snapshot_sha256 与实际文件一致
online_experience_update == false
resume_experience_state == false
```

不要把 `results/phase4_checkpoint_load_pilot/` 纳入最终 aggregate。

### Step F：最终聚合

将四个最终目录作为四个 `--input` 传给：

```bash
python3 scripts/aggregate_phase3_evolving_advantage.py \
  --input results/phase4_final_static_m0 \
  --input results/phase4_final_evolving_online_m0 \
  --input results/phase4_final_evolving_m20 \
  --input results/phase4_final_evolving_m50 \
  --output results/phase4_final_evolving_advantage_aggregate.json
```

最终聚合必须满足：

- 4 个方法都存在；
- 每个方法 80 cells（20 seeds × 4 families）；
- 每个方法 320 episodes；
- paired static cells 完整；
- 同一 seed×fault family 对齐；
- prior、scope、fault scale 一致；
- M20/M50 的 snapshot path/SHA 完整；
- 输出每个故障族的结果；
- 输出 intervention recovery、sustained recovery、MTTR、cost、useless probe；
- 输出 paired bootstrap CI。

---

## 7. 论文结论的安全边界

在完整最终矩阵完成之前，只能写：

- pilot 显示 Evolving 能利用重复反馈改变动作选择；
- checkpoint 加载链路经过真实 Gazebo 验证；
- 某些 stress cell 中 Evolving 表现优于 Static；
- 当前证据还不是四故障族的确认性统计结论。

不能写：

- “Evolving 在所有场景都优于 Static”；
- “Static 必然失败”；
- “M50 已完成完整训练”；
- “pilot 结果是最终显著性结果”；
- “弱先验是完全无知识初始化”；
- 把 `0/4` 的单个 stress cell 当作全局 Static 性能。

最终论文应展示：

1. cell-level 成功数和分母；
2. 每个故障族的 aggregate；
3. seed-paired delta 与置信区间；
4. intervention cost，即便 Evolving 成本更高也必须保留；
5. Static 在 nominal 场景表现正常的结果；
6. pilot 与 confirmatory evaluation 分开；
7. 所有 seed 替换和排除记录。

如果最终 CI 包含 0，或者优势只集中于一个故障族，必须如实报告，不要通过删除 seed、调整先验或改变重复次数来修饰结果。

---

## 8. 禁止事项与防止返工的规则

1. 不要删除任何已有 JSON、dispatch 文件、日志或旧的无效尝试；它们用于审计。
2. 不要覆盖 `phase3_stage_gate.json` 或旧 phase-3 aggregate；协议明确要求原第三阶段冻结。
3. 不要重新生成最终测试 seed。
4. 不要把 `544047076` 放回最终测试。
5. 不要把 pilot 目录合并进最终确认性 aggregate。
6. 不要用 planner-only M50 作为完整 checkpoint。
7. 不要人工修改 episode 的 success、selected_action、cost 或 SHA。
8. 不要在同一个 ROS domain 同时启动多个 Gazebo。
9. 不要把“命令返回 0”当作实验完成判据，必须检查每个 JSON 的 protocol compliance 和 evidence。
10. 不要为了让 Evolving 看起来更好而改变 Static 的先验、动作范围、seed、故障强度或重复次数。
11. 如果改协议，必须提升 revision、写明原因、保存旧 SHA 和新 SHA。
12. 在 20.04 板子上运行前，先确认 ROS 发行版；不要直接在 Jazzy/Ubuntu 24.04 编译产物上混跑。

---

## 9. 推荐的交接操作

Cursor 开始时应按以下顺序回复/记录：

1. 读取本文件；
2. 运行进程检查和 23/52 覆盖审计；
3. 确认 `phase4_training_full_status.json` 为 `stopped_for_quota`；
4. 先用 `--resume` 继续训练，不要重跑 23 个有效 cell；
5. 每完成一个故障族或一组 seed，更新状态 JSON，但不要伪造 ready；
6. 52/52 后才运行 checkpoint builder；
7. builder 通过后才开始最终 20-seed paired evaluation；
8. 最后把完成情况、manifest、aggregate 和所有限制写入新的工作报告。

当 Cursor 交回新的工作文档时，下一次接手应优先核对：

```text
训练 coverage 是否 52/52
manifest.ready 是否 true
M20/M50 是否来自 full training
final eval 是否 4×80 cells
所有 M20/M50 SHA 是否匹配
544047076 是否仍被排除
最终 aggregate 是否没有混入 pilot
```

---

## 10. 当前交接结论

截至本文件生成时：

- 有效训练 cell：23/52；
- 已完成的 13 个 planner seed 是可靠的；
- localization/costmap/control 正在补齐但尚未完成；
- 完整 checkpoint 尚未生成；
- 最终测试矩阵尚未开始；
- pilot 已证明机制和 checkpoint 加载链路可运行；
- 最终论文优越性结论尚未成立；
- 所有运行已停止，后续应从 `--resume` 继续。

## 11. GitHub 备份状态

本地工作区已经初始化为独立 Git 仓库，并配置：

```text
origin = https://github.com/1104546057-cloud/EACR.git
```

已经创建的本地提交：

```text
95e1b0d Link the reproducible handoff from README
aadc9de Preserve EACR evolving evaluation and handoff state
```

`build/`、`install/`、`log/` 和 Python 缓存已由 `.gitignore` 排除；源码、脚本、协议、结果 JSON、日志型审计文件和本交接文档已纳入提交。训练目录中的原绝对路径符号链接已在提交前物化为普通 JSON，避免 clone 后断链。

本环境没有 GitHub CLI 登录状态、HTTPS credential 或 SSH key，因此自动 `git push` 返回 `could not read Username for 'https://github.com'`，远端尚未收到提交。拥有仓库权限的用户或 Cursor 应先完成一次 GitHub 登录，然后在本目录执行：

```bash
cd /home/hu/文档/ChatGPT/论文/eacr_ws
git push -u origin master
```

如果远端策略要求 `main`，可以在认证后执行：

```bash
git branch -M main
git push -u origin main
```

不要把 token、密码或私钥写入仓库、脚本、remote URL 或交接文档。
