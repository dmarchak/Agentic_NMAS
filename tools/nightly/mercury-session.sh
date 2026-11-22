#!/usr/bin/env bash
# One automatic Mercury work session (docs/handoff/START.md is its prompt), started by the
# operator's user crontab at 03:35 America/Denver. Never two at once: `flock -n` on a lock file
# outside the repository; a second start while one runs exits at once, saying so in the log.
#
#   tools/nightly/mercury-session.sh              the session, START.md as its prompt
#   tools/nightly/mercury-session.sh --prompt P   the same launch with prompt P (a dry run)
#
# The log is ~/mercury-runs/<yyyy-mm-dd>.log (Denver's date), outside the repository.
set -u

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runs="$HOME/mercury-runs"
mkdir -p "$runs"
log="$runs/$(TZ=America/Denver date +%F).log"
lock="$runs/session.lock"
model="${MERCURY_SESSION_MODEL:-claude-opus-5-5}"

prompt_file="$repo/docs/handoff/START.md"
prompt=""
if [ "${1:-}" = "--prompt" ]; then
  prompt="${2:-}"
fi

# Cron's environment is minimal: find claude on PATH, else the newest VS Code extension's binary.
claude_bin="${CLAUDE_BIN:-}"
if [ -z "$claude_bin" ]; then
  claude_bin="$(command -v claude 2>/dev/null || true)"
fi
if [ -z "$claude_bin" ]; then
  claude_bin="$(ls -d "$HOME"/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude \
                 2>/dev/null | sort -V | tail -1)"
fi

exec 9>"$lock"
if ! flock -n 9; then
  echo "$(date -u +%FT%TZ) another session holds $lock: not starting" >>"$log"
  exit 0
fi

cd "$repo" || { echo "$(date -u +%FT%TZ) cannot cd to $repo" >>"$log"; exit 1; }
if [ -z "$claude_bin" ] || [ ! -x "$claude_bin" ]; then
  echo "$(date -u +%FT%TZ) no claude binary found (PATH or ~/.vscode/extensions)" >>"$log"
  exit 1
fi
if [ -z "$prompt" ]; then
  prompt="$(cat "$prompt_file")"
fi

{
  echo "=== $(date -u +%FT%TZ) session start: $claude_bin, model $model"
  "$claude_bin" -p "$prompt" --model "$model" --permission-mode bypassPermissions
  echo "=== $(date -u +%FT%TZ) session end: exit $?"
} >>"$log" 2>&1
