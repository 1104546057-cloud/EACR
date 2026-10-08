#!/usr/bin/env bash
# Run the four frozen final-evaluation methods one Gazebo at a time, then
# write the confirmatory aggregate and paper report. This script does not
# edit src/, scripts/, docs/, or checkpoints.
set -euo pipefail

ROOT="/home/hu/文档/ChatGPT/论文/eacr_ws"
cd "$ROOT"
LOG="$ROOT/results/phase4_final_orchestrator.log"
LOCK="$ROOT/results/phase4_final_orchestrator.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "orchestrator already running" >&2
  exit 1
fi

SEEDS=(
  1069364068 683001511 450637390 1207356449 1578549000
  252445555 729528073 1092085222 200776800 1464253601
  365260637 225495283 1725492561 1054169594 1613439514
  1691408245 849115063 1146002680 1534671149 1320660730
)

log() {
  printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG"
}

ps_match_count() {
  local needle="$1"
  ps -eo args | awk -v needle="$needle" '
    index($0, "awk") { next }
    index($0, needle) { n++ }
    END { print n + 0 }
  '
}

matrix_running() {
  [[ "$(ps_match_count 'python3 scripts/run_phase3_gazebo_matrix.py')" != "0" ]]
}

gazebo_count() {
  ps_match_count 'gz sim -r'
}

launch_running() {
  [[ "$(ps_match_count '/opt/ros/jazzy/bin/ros2 launch eacr_sim')" != "0" ]]
}

stop_sim() {
  local pgid
  local -a groups=()
  while read -r pgid; do
    [[ -n "$pgid" ]] && groups+=("$pgid")
  done < <(ps -eo pgid,args | awk '
    index($0, "awk") { next }
    index($0, "gz sim -r") ||
    index($0, "/opt/ros/jazzy/bin/ros2 launch eacr_sim") ||
    index($0, "python3 scripts/run_phase3_gazebo_matrix.py") ||
    index($0, "phase3_gazebo_runner") { print $1 }
  ' | sort -u)
  if ((${#groups[@]} == 0)); then
    return 0
  fi
  for pgid in "${groups[@]}"; do
    [[ "$pgid" =~ ^[0-9]+$ ]] || continue
    kill -TERM -- "-$pgid" 2>/dev/null || true
  done
  sleep 8
  groups=()
  while read -r pgid; do
    [[ -n "$pgid" ]] && groups+=("$pgid")
  done < <(ps -eo pgid,args | awk '
    index($0, "awk") { next }
    index($0, "gz sim -r") ||
    index($0, "/opt/ros/jazzy/bin/ros2 launch eacr_sim") ||
    index($0, "python3 scripts/run_phase3_gazebo_matrix.py") ||
    index($0, "phase3_gazebo_runner") { print $1 }
  ' | sort -u)
  for pgid in "${groups[@]}"; do
    [[ "$pgid" =~ ^[0-9]+$ ]] || continue
    kill -KILL -- "-$pgid" 2>/dev/null || true
  done
  sleep 2
  if [[ "$(gazebo_count)" != "0" ]]; then
    log "ERROR gazebo still present after stop"
    return 1
  fi
}

start_gazebo() {
  local method="$1"
  local log_path="$ROOT/results/phase4_final_gazebo_${method}.log"
  local launch_pid launch_state
  if [[ "$(gazebo_count)" != "0" ]]; then
    log "ERROR refusing to start Gazebo while another gz sim is running"
    return 1
  fi
  if [[ -s "$log_path" ]]; then
    cp -a "$log_path" "${log_path}.prev-$(date +%Y%m%dT%H%M%S)"
  fi
  setsid bash -lc 'source scripts/source_eacr.sh && exec ros2 launch eacr_sim eacr_episode.launch.py headless:=True use_rviz:=False fault_scale:=1.5' \
    >"$log_path" 2>&1 &
  launch_pid=$!
  local ready_deadline=$((SECONDS + 180))
  while ((SECONDS < ready_deadline)); do
    if [[ -f "$log_path" ]] && grep -q 'Nav2 localization and navigation are active.' "$log_path"; then
      log "gazebo ready for $method"
      return 0
    fi
    launch_state="$(ps -p "$launch_pid" -o stat= 2>/dev/null || true)"
    if [[ -z "$launch_state" || "$launch_state" == Z* ]]; then
      log "ERROR gazebo launch exited before ready"
      return 1
    fi
    sleep 2
  done
  log "ERROR gazebo ready timeout for $method"
  return 1
}

count_valid() {
  local method="$1"
  local dir="$2"
  local output
  output="$(python3 "$ROOT/results/phase4_final_count_cells.py" "$method" "$dir")"
  printf '%s\n' "$output" >>"$LOG"
  printf '%s\n' "$output" | awk -F= '/^valid=/{print $2; exit}'
}

run_matrix() {
  local log_path="$1"
  shift
  local quoted pid
  printf -v quoted '%q ' "$@"
  setsid bash -lc "source scripts/source_eacr.sh && exec python3 scripts/run_phase3_gazebo_matrix.py ${quoted}" \
    >"$log_path" 2>&1 &
  pid=$!
  log "matrix pid=$pid log=$log_path"
  wait "$pid" || log "matrix exit=$?"
}

finish_method() {
  local slug="$1"
  local method="$2"
  local dir="$3"
  shift 3
  local -a args=("$@")
  local seed family passes=0 valid matrix_log
  for seed in "${SEEDS[@]}"; do
    args+=(--seed "$seed")
  done
  for family in localization costmap planner control; do
    args+=(--fault-family "$family")
  done
  args+=(
    --fault-repetitions 4 --goal-timeout-sec 60
    --experience-prior-mode weak_shared_m0
    --use-belief-action-scope --fault-scale 1.5
    --timeout-sec 600 --retries 1 --resume
  )
  mkdir -p "$ROOT/$dir"
  while ((passes < 3)); do
    valid="$(count_valid "$method" "$ROOT/$dir")"
    log "$slug valid=$valid pass=$passes"
    if [[ "$valid" == "80" ]]; then
      log "$slug complete"
      return 0
    fi
    if matrix_running; then
      log "$slug waiting for the matrix already in progress"
      while matrix_running; do
        sleep 60
      done
      continue
    fi
    if [[ "$(gazebo_count)" != "1" ]]; then
      log "$slug gazebo count=$(gazebo_count); restarting a single simulator"
      stop_sim
      start_gazebo "$slug"
    fi
    passes=$((passes + 1))
    matrix_log="$ROOT/results/phase4_final_${slug}_matrix_pass${passes}.log"
    run_matrix "$matrix_log" "${args[@]}"
  done
  valid="$(count_valid "$method" "$ROOT/$dir")"
  log "$slug stopped short valid=$valid"
  return 1
}

log "orchestrator start"
while matrix_running; do
  log "waiting for the Static M0 matrix already running; valid=$(count_valid eacr_static_m0 "$ROOT/results/phase4_final_static_m0") gazebo=$(gazebo_count)"
  sleep 60
done

short=0
finish_method static_m0 eacr_static_m0 results/phase4_final_static_m0 \
  --baseline eacr_static --experience-checkpoint M_0 --no-online-experience-update \
  --result-dir results/phase4_final_static_m0 || short=1
stop_sim

finish_method evolving_online_m0 eacr_evolving_online_m0 results/phase4_final_evolving_online_m0 \
  --baseline eacr_evolving --experience-checkpoint M_0 \
  --result-dir results/phase4_final_evolving_online_m0 || short=1
stop_sim

finish_method evolving_m20 eacr_evolving_m20 results/phase4_final_evolving_m20 \
  --baseline eacr_evolving --experience-checkpoint M_20 \
  --experience-snapshot-template 'results/phase4_experience_evolving_full_{checkpoint}.json' \
  --no-online-experience-update \
  --result-dir results/phase4_final_evolving_m20 || short=1
stop_sim

finish_method evolving_m50 eacr_evolving_m50 results/phase4_final_evolving_m50 \
  --baseline eacr_evolving --experience-checkpoint M_50 \
  --experience-snapshot-template 'results/phase4_experience_evolving_full_{checkpoint}.json' \
  --no-online-experience-update \
  --result-dir results/phase4_final_evolving_m50 || short=1
stop_sim

log "running frozen aggregate short=$short"
set +e
python3 scripts/aggregate_phase4_final.py \
  --repo-root "$ROOT" \
  --input results/phase4_final_static_m0 \
  --input results/phase4_final_evolving_online_m0 \
  --input results/phase4_final_evolving_m20 \
  --input results/phase4_final_evolving_m50 \
  --output results/phase4_final_aggregate.json \
  | tee -a "$LOG"
python3 results/phase4_final_make_report.py | tee -a "$LOG"
set -e
log "orchestrator done short=$short"
exit "$short"
