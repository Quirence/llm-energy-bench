#!/usr/bin/env bash
# Run the quality-v3 series on the RTX 5060 stand (docs/quality-v3-preregistration.md).
# Usage: bash scripts/run_quality_v3.sh   (from the repository root, Git Bash)
# Stops at the first failed preflight or run; completed runs are kept.
set -euo pipefail

cd "$(dirname "$0")/.."
PY=".venv/Scripts/python"
export PYTHONPATH=src
# Run paths contain Cyrillic; keep Python stdio in UTF-8.
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
RUNS="experiments/runs/quality-v3"
EXPECTED_COMMIT_TAG="quality-v3-prereg"
EXPECTED_POWER_W="80.0"
BLOCKS=(mgsm-ru-direct mgsm-ru-cot det-direct det-cot ifeval-a ifeval-b ifeval-c
        mgsm-ru-direct-p2 mgsm-ru-cot-p2 mgsm-ru-direct-p3 mgsm-ru-cot-p3)
HOST_ID="maibenben-x16c-rtx5060"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

"$PY" --version | grep -q '^Python 3\.12\.' || { log "CPython 3.12 required"; exit 1; }
tag_commit="$(git rev-list -n1 "$EXPECTED_COMMIT_TAG")"
if ! git merge-base --is-ancestor "$tag_commit" HEAD; then
    log "HEAD does not contain $EXPECTED_COMMIT_TAG"; exit 1
fi
if [ -n "$(git status --porcelain -- src prompts configs/quality-v3 requirements)" ]; then
    log "code, prompts or configs differ from the commit"; exit 1
fi
# Keep Windows from idle-sleeping while the series runs (no settings are changed).
"$PY" -I -c "import ctypes, time; ctypes.windll.kernel32.SetThreadExecutionState(0x80000001); time.sleep(10**7)" &
KEEP_AWAKE_PID=$!
trap 'kill "$KEEP_AWAKE_PID" 2>/dev/null || true' EXIT

log "series start at $(git rev-parse HEAD)"

completed_run() {  # newest completed run directory of one block, if any
    local dir
    for dir in $(ls -d "$RUNS/quality-v3-$1-$HOST_ID-"* 2>/dev/null | sort -r); do
        if "$PY" -I -c 'import json,sys; sys.exit(json.load(open(sys.argv[1], encoding="utf-8"))["status"] != "completed")' "$dir/manifest.json" 2>/dev/null; then
            echo "$dir"; return 0
        fi
    done
    return 1
}

for block in "${BLOCKS[@]}"; do
    config="configs/quality-v3/${block}.toml"
    if done_dir="$(completed_run "$block")"; then
        [ -f "$done_dir/report.md" ] || "$PY" -m llm_energy_bench report "$done_dir" > /dev/null
        log "$block: already completed -> $done_dir (skipped)"
        continue
    fi
    power="$("$PY" -m llm_energy_bench doctor --config "$config" --json \
        | "$PY" -I -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"], d; print(d["gpu"]["power_limit_watts"])')"
    if [ "$power" != "$EXPECTED_POWER_W" ]; then
        log "$block: power limit $power W, expected $EXPECTED_POWER_W W (Gaming mode)"; exit 1
    fi
    log "$block: preflight ok, power limit ${power} W"
    "$PY" -m llm_energy_bench run --config "$config" > /dev/null
    run_dir="$(completed_run "$block")" || { log "$block: no completed run directory"; exit 1; }
    log "$block: run finished -> $run_dir"
    "$PY" -m llm_energy_bench report "$run_dir" > /dev/null
    log "$block: report written"
done
log "series complete"
