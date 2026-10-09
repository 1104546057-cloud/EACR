#!/usr/bin/env bash
# Continue frozen M50 evaluation after the bounded orchestrator exits.
# This script waits on the orchestrator's shared lock before touching Gazebo.
set -euo pipefail

ROOT="/home/hu/文档/ChatGPT/论文/eacr_ws"
cd "$ROOT"
LOCK="$ROOT/results/phase4_final_orchestrator.lock"
LOG="$ROOT/results/phase4_final_m50_resume.log"
mkdir -p "$ROOT/results"
exec 9>>"$LOCK"
flock 9

log() {
  printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG"
}

gazebo_count() {
  ps -eo comm,args | awk '$1 == "gz" && $2 == "sim" { n++ } END { print n + 0 }'
}

count_valid() {
  local output
  output="$(python3 "$ROOT/results/phase4_final_count_cells.py" eacr_evolving_m50 "$ROOT/results/phase4_final_evolving_m50")"
  printf '%s\n' "$output" >>"$LOG"
  printf '%s\n' "$output" | awk -F= '/^valid=/{print $2; exit}'
}

start_gazebo() {
  local log_path="$ROOT/results/phase4_final_gazebo_evolving_m50_resume_$(date +%Y%m%dT%H%M%S).log"
  local launch_state
  if [[ "$(gazebo_count)" != "0" ]]; then
    log "ERROR refusing to start Gazebo while another gz sim is running"
    return 1
  fi
  setsid bash -lc 'source scripts/source_eacr.sh && exec ros2 launch eacr_sim eacr_episode.launch.py headless:=True use_rviz:=False fault_scale:=1.5' \
    >"$log_path" 2>&1 &
  launch_pid=$!
  launch_pgid="$(ps -o pgid= -p "$launch_pid" | tr -d ' ')"
  log "started single Gazebo launch pid=$launch_pid pgid=$launch_pgid log=$log_path"
  local ready_deadline=$((SECONDS + 180))
  while ((SECONDS < ready_deadline)); do
    if grep -q 'Nav2 localization and navigation are active.' "$log_path"; then
      log "Gazebo ready"
      return 0
    fi
    launch_state="$(ps -p "$launch_pid" -o stat= 2>/dev/null || true)"
    if [[ -z "$launch_state" || "$launch_state" == Z* ]]; then
      log "ERROR Gazebo launch exited before ready"
      return 1
    fi
    sleep 2
  done
  log "ERROR Gazebo ready timeout"
  return 1
}

stop_owned_gazebo() {
  [[ -n "${launch_pgid:-}" ]] || return 0
  kill -TERM -- "-$launch_pgid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    if ! ps -eo pgid= | awk -v group="$launch_pgid" '$1 == group { found=1 } END { exit !found }'; then
      break
    fi
    sleep 1
  done
  if ps -eo pgid= | awk -v group="$launch_pgid" '$1 == group { found=1 } END { exit !found }'; then
    kill -KILL -- "-$launch_pgid" 2>/dev/null || true
  fi
  wait "$launch_pid" 2>/dev/null || true
  launch_pid=""
  launch_pgid=""
  if [[ "$(gazebo_count)" != "0" ]]; then
    log "ERROR Gazebo remains after stopping owned launch"
    return 1
  fi
  log "stopped owned Gazebo"
}

log "acquired orchestrator lock; resuming M50"
launch_pid=""
launch_pgid=""
valid="$(count_valid)"
passes=0

while [[ "$valid" != "80" ]]; do
  if [[ "$(gazebo_count)" == "0" ]]; then
    start_gazebo
  elif [[ "$(gazebo_count)" != "1" ]]; then
    log "ERROR expected at most one Gazebo, found $(gazebo_count)"
    exit 1
  fi

  passes=$((passes + 1))
  matrix_log="$ROOT/results/phase4_final_evolving_m50_resume_pass${passes}.log"
  args=(
    --baseline eacr_evolving
    --experience-checkpoint M_50
    --experience-snapshot-template 'results/phase4_experience_evolving_full_{checkpoint}.json'
    --no-online-experience-update
    --result-dir results/phase4_final_evolving_m50
    --fault-repetitions 4
    --goal-timeout-sec 60
    --experience-prior-mode weak_shared_m0
    --use-belief-action-scope
    --fault-scale 1.5
    --timeout-sec 600
    --retries 1
    --resume
  )
  seeds=(
    1069364068 683001511 450637390 1207356449 1578549000
    252445555 729528073 1092085222 200776800 1464253601
    365260637 225495283 1725492561 1054169594 1613439514
    1691408245 849115063 1146002680 1534671149 1320660730
  )
  for seed in "${seeds[@]}"; do args+=(--seed "$seed"); done
  for family in localization costmap planner control; do args+=(--fault-family "$family"); done

  printf -v quoted '%q ' "${args[@]}"
  setsid bash -lc "source scripts/source_eacr.sh && exec python3 scripts/run_phase3_gazebo_matrix.py ${quoted}" \
    >"$matrix_log" 2>&1 &
  matrix_pid=$!
  log "matrix pid=$matrix_pid pass=$passes log=$matrix_log"
  wait "$matrix_pid" || log "matrix exit=$?"
  valid="$(count_valid)"
  log "M50 valid=$valid/80 after pass=$passes"
  if [[ "$valid" != "80" ]]; then
    # Refresh our own long-lived simulator between complete matrix passes.
    # No cell is active here, and the next pass still uses identical frozen flags.
    stop_owned_gazebo
  fi
done

stop_owned_gazebo

for pair in \
  'eacr_static_m0 results/phase4_final_static_m0' \
  'eacr_evolving_online_m0 results/phase4_final_evolving_online_m0' \
  'eacr_evolving_m20 results/phase4_final_evolving_m20' \
  'eacr_evolving_m50 results/phase4_final_evolving_m50'; do
  read -r method dir <<<"$pair"
  output="$(python3 "$ROOT/results/phase4_final_count_cells.py" "$method" "$ROOT/$dir")"
  printf '%s\n' "$output" | tee -a "$LOG"
  [[ "$(printf '%s\n' "$output" | awk -F= '/^valid=/{print $2; exit}')" == "80" ]]
done

log "running frozen 20,000-draw aggregate and report"
python3 scripts/aggregate_phase4_final.py \
  --repo-root "$ROOT" \
  --input results/phase4_final_static_m0 \
  --input results/phase4_final_evolving_online_m0 \
  --input results/phase4_final_evolving_m20 \
  --input results/phase4_final_evolving_m50 \
  --output results/phase4_final_aggregate.json \
  --bootstrap-draws 20000 | tee -a "$LOG"
python3 results/phase4_final_make_report.py | tee -a "$LOG"
python3 - <<'PY'
import json
from pathlib import Path
p = json.loads(Path("results/phase4_final_aggregate.json").read_text())
if p.get("confirmatory_ready") is not True:
    raise SystemExit("confirmatory aggregate did not pass every gate")
if p.get("bootstrap", {}).get("draws") != 20000:
    raise SystemExit("aggregate does not record 20,000 bootstrap draws")
print("confirmatory aggregate ready; 20,000 bootstrap draws")
PY
log "M50 complete; aggregate and report verified"
