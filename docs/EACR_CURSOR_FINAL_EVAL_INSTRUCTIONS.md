# 给 Cursor：EACR 最终确认性评估执行指令

## 任务范围

你只负责执行 Gazebo 最终评估和保存原始结果。不要修改算法、runner、统计脚本、协议 JSON、seed manifest 或 checkpoint。所有方法必须在同一工作区、同一 ROS 环境和同一冻结协议下运行。

统计口径已经冻结在：

```text
docs/EACR_FINAL_STATISTICAL_SPEC_v1.md
```

开始前先阅读它。训练已经完成并核验为 52/52；不要重新跑训练，也不要使用 planner-only checkpoint。

## 只读输入

```text
results/phase3_evolving_advantage_protocol.json
results/phase3_evolving_advantage_seed_manifest.json
results/phase4_experience_evolving_full_M_0.json
results/phase4_experience_evolving_full_M_20.json
results/phase4_experience_evolving_full_M_50.json
results/phase4_experience_evolving_full_manifest.json
scripts/run_phase3_gazebo_matrix.py
src/eacr_sim/eacr_sim/phase3_gazebo_runner.py
```

最终 seed 必须从当前 protocol/manifest 读取，不要手打旧清单，不要把 `544047076` 加回去。当前确认性 seed 是：

```text
1069364068 683001511 450637390 1207356449 1578549000
252445555 729528073 1092085222 200776800 1464253601
365260637 225495283 1725492561 1054169594 1613439514
1691408245 849115063 1146002680 1534671149 1320660730
```

参数固定为：

```text
fault_scale=1.5
fault_repetitions=4
experience_prior_mode=weak_shared_m0
use_belief_action_scope=true
goal_timeout_sec=60
resume_experience_state=false
```

## 文件所有权和并行规则

你可以创建或更新：

```text
results/phase4_final_static_m0/
results/phase4_final_evolving_online_m0/
results/phase4_final_evolving_m20/
results/phase4_final_evolving_m50/
results/phase4_final_eval_status.json
results/phase4_final_gazebo_*.log
```

不要修改：

```text
src/
scripts/
docs/
results/phase3_evolving_advantage_protocol.json
results/phase3_evolving_advantage_seed_manifest.json
results/phase4_experience_evolving_full_*
```

不要和其他代理并行启动 Gazebo。一个 ROS domain 同时只能有一个 Gazebo。一次只跑一个 method 目录；方法之间通过停止旧 launch、确认进程清空后再启动新 launch。

## 每次启动前检查

```bash
cd /home/hu/文档/ChatGPT/论文/eacr_ws
source scripts/source_eacr.sh
ps -eo pid,ppid,pgid,stat,etime,cmd | rg \
  'run_phase3_gazebo_matrix|phase3_gazebo_runner|ros2 launch eacr_sim|gz sim -r|nav2_bringup_gate' || true
```

若仍有旧进程，先停止整个 launch 进程树，确认没有 `gz sim`、`component_container_isolated`、`nav2_bringup_gate`、`episode_reset`、`fault_injector` 或 runner，再启动一个新的 Gazebo。不要在旧 Gazebo 上叠加第二次 launch。

运行前做一次只读编译检查；如果失败，停止并报告，不要自行修改源文件：

```bash
python3 -m py_compile scripts/run_phase3_gazebo_matrix.py \
  src/eacr_sim/eacr_sim/phase3_gazebo_runner.py
```

因为 runner 已加入 `time_to_recovery_sec` 字段，正式评估前还必须重新构建 ROS 包；这一步只构建，不修改源代码：

```bash
source scripts/source_eacr.sh
colcon build --symlink-install --packages-select eacr_core eacr_sim
source install/setup.bash
```

构建失败就停止并报告，不要在最终评估过程中改 `src/`。

## Gazebo 启动

```bash
source scripts/source_eacr.sh
ros2 launch eacr_sim eacr_episode.launch.py \
  headless:=True use_rviz:=False fault_scale:=1.5 \
  > results/phase4_final_gazebo_<method>.log 2>&1
```

`<method>` 用 `static_m0`、`evolving_online_m0`、`evolving_m20` 或 `evolving_m50`。保持这个 launch 运行，另一个终端运行矩阵；一个 method 完成后再停它。

## 四个 method 的执行命令

下面的 seed/family 参数必须完全相同。每次命令都加 `--resume`，让合法 cell 自动跳过。命令退出 0 不是完成判据，必须检查 JSON。

### 1. Static M0

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
  --fault-repetitions 4 --goal-timeout-sec 60 \
  --experience-checkpoint M_0 \
  --experience-prior-mode weak_shared_m0 \
  --use-belief-action-scope --fault-scale 1.5 \
  --result-dir results/phase4_final_static_m0 \
  --timeout-sec 600 --retries 1 --resume
```

### 2. Online Evolving M0

使用同一条命令，将 `--baseline eacr_static` 改为 `--baseline eacr_evolving`，将结果目录改为 `results/phase4_final_evolving_online_m0`。保留 `experience_checkpoint M_0`，不要加 `--no-online-experience-update`，不要提供 M20/M50 snapshot template。

### 3. Frozen Evolving M20

使用同一条命令，改为：

```text
--baseline eacr_evolving
--experience-checkpoint M_20
--experience-snapshot-template results/phase4_experience_evolving_full_{checkpoint}.json
--no-online-experience-update
--result-dir results/phase4_final_evolving_m20
```

### 4. Frozen Evolving M50

使用同一条命令，改为：

```text
--baseline eacr_evolving
--experience-checkpoint M_50
--experience-snapshot-template results/phase4_experience_evolving_full_{checkpoint}.json
--no-online-experience-update
--result-dir results/phase4_final_evolving_m50
```

不要使用 `results/phase4_experience_evolving_M_20.json` 或 `M_50.json`；那是 planner-only pilot checkpoint。

## 每个 method 完成后的验收

把下面脚本中的 `METHOD_DIR` 改成实际目录后运行：

```bash
python3 - <<'PY'
import glob, json, collections, pathlib
method = pathlib.Path('METHOD_DIR')
valid = {}
for path in method.glob('phase3_gazebo_*.json'):
    try:
        item = json.loads(path.read_text())
    except Exception:
        continue
    rows = item.get('episodes') or []
    if item.get('protocol_compliant') is not True or len(rows) != 4:
        continue
    if not all(row.get('episode_evidence_valid') for row in rows):
        continue
    family = rows[0].get('fault_family')
    key = (int(item['seed']), family)
    valid[key] = path
print('valid cells:', len(valid))
print('by family:', collections.Counter(f for _, f in valid))
print('episodes:', len(valid)*4)
assert len(valid) == 80
assert collections.Counter(f for _, f in valid) == {
    'localization': 20, 'costmap': 20, 'planner': 20, 'control': 20
}
PY
```

对 M20/M50 额外检查每个 JSON：

```text
experience_checkpoint == M_20 或 M_50
experience_snapshot_path == 对应 full checkpoint 路径
experience_snapshot_sha256 == 该文件当前 SHA-256
online_experience_update == false
resume_experience_state == false
```

如果一个 cell 失败，不删除失败 JSON；确认进程树清空后再次运行同一命令的 `--resume`。不要手改结果或复制其他 seed 的 JSON。

## 停止条件与交回内容

四个方法都达到 80 cells 后停止 Gazebo，并交回：

1. 四个结果目录的 valid cell 数量；
2. 每个方法的无效尝试数量及原因；
3. M20/M50 的 snapshot SHA 核对结果；
4. `results/phase4_final_eval_status.json`；
5. 各方法日志路径；
6. 当前 Git status 和未提交文件清单。

不要运行最终 aggregate 脚本；统计汇总由 Codex 按 `EACR_FINAL_STATISTICAL_SPEC_v1.md` 执行。不要把 pilot、训练目录或 planner-only checkpoint 作为 aggregate 输入。
