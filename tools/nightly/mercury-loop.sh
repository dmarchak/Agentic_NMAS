#!/usr/bin/env bash
# tools/nightly/mercury-loop.sh: fresh Mercury sessions back to back until the 02:30 Denver handover.
set -u
REPO="$HOME/Documents/Python/Agentic_NMAS"
RUNS="$HOME/mercury-runs"
LOG="$RUNS/loop.log"
mkdir -p "$RUNS"
exec 9>"$RUNS/loop.lock"
flock -n 9 || exit 0                       # one loop at a time

quick=0
while :; do
  now=$(TZ=America/Denver date +%H%M)
  if [ "$now" -ge 0230 ] && [ "$now" -lt 0335 ]; then
    echo "$(date -Is) handover window; loop ends" >>"$LOG"; exit 0
  fi
  state=$(cat "$RUNS/STATE" 2>/dev/null || echo RUNNING)
  if [ "$state" != "RUNNING" ]; then
    echo "$(date -Is) STATE=$state; loop ends" >>"$LOG"; exit 0
  fi
  start=$(date +%s)
  "$REPO/tools/nightly/mercury-session.sh"; rc=$?
  dur=$(( $(date +%s) - start ))
  echo "$(date -Is) session ended rc=$rc after ${dur}s" >>"$LOG"
  if [ "$dur" -lt 300 ]; then quick=$((quick + 1)); else quick=0; fi
  if [ "$quick" -ge 3 ]; then
    echo "$(date -Is) 3 sessions under 5 min in a row; loop ends" >>"$LOG"; exit 1
  fi
  sleep 60
done
