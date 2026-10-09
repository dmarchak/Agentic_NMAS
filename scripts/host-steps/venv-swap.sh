#!/usr/bin/env bash
# DRAFT, not approved to run (Phase 4 section 8.3, signed off by the operator 2026-10-09). A lock
# change after the first switch: move the link /opt/mercury-venv to the release's proved venv
# (venv-1-build.sh), restart, and prove the app and its checks run from it. ON ANY FAILED PROOF
# IT POINTS THE LINK BACK ITSELF, restarts, and proves the previous venv answers; the result
# stays FAIL, naming what failed. After a proved swap it removes venvs older than the previous
# one that no process has loaded. The drop-ins name the link, so no unit changes.
#
# Until the deploy carries the swap (section 8.4), run it in the same sitting as the release's
# deploy, from that release's checkout on the app host:
#     bash <checkout>/scripts/host-steps/venv-swap.sh
. "$(dirname "$0")/lib.sh"

VENV=/opt/mercury-venv
PREVIOUS=/opt/mercury-venv.previous
ID=$(cd "$CHECKOUT" && /usr/bin/python3 -m modules.app_interpreter venv-id "$CHECKOUT" 2>&1)
DIR="/opt/mercury-venv-$ID"
FROM=$(readlink -f "$VENV" 2>/dev/null)
FROM_NAME=$(basename "${FROM:-none}")
FINISHED=$(for c in nmas-heartbeat-check nmas-telemetry-check; do
    printf 'nmas-job-finished@%s.service ' "$c"; done)
export VENV PREVIOUS ID DIR FROM FROM_NAME FINISHED

# Waits for the app's /health, up to 60 s (not measured: the app's start time after a restart),
# saying how long it took.
wait_health() {
    echo "== waiting for /health (up to 60 s)"
    for i in $(seq 1 30); do
        [ "$(curl -s -o /dev/null -m 3 -w '%{http_code}' http://127.0.0.1:5000/health)" = 200 ] \
            && { echo "   answering after about $((i * 2)) s"; return 0; }
        sleep 2
    done
}
export -f wait_health

plan "run as the operator's own user, not root" \
     "the first switch was made (the link exists)" \
     "the release's venv is built and proved" \
     "the release's venv is not the one running" \
     "the link points at the release's venv" \
     "flask-app is active" \
     "the app answers /health" \
     "the app's process loads from the release's venv" \
     "the heartbeat and telemetry checks run and succeed from the venv" \
     "the job-finished notices they started succeed from the venv" \
     "the previous venv is kept and the link to it recorded" \
     "only the current and previous venvs remain, or a running process holds the rest"

not_root
check "the first switch was made (the link exists)" re '^/opt/mercury-venv-[0-9a-f]{12}$' 'echo "$FROM"'
check "the release's venv is built and proved" has "id $ID" 'cat "$DIR/.mercury-proved"'
check "the release's venv is not the one running" eq "" \
    '[ "$FROM" = "$DIR" ] && echo "the link already points at $DIR: nothing to swap"; true'

step "record the running venv as the previous one ($PREVIOUS -> $FROM_NAME)" \
    'sudo ln -s "$FROM_NAME" "$PREVIOUS.new" && sudo mv -T "$PREVIOUS.new" "$PREVIOUS"'
# From here a failed step or check points the link back and proves the previous venv answers.
ON_FAIL_WHAT="point $VENV back to $FROM_NAME, restart, and prove it answers"
ON_FAIL='sudo ln -s "$FROM_NAME" "$VENV.back" && sudo mv -T "$VENV.back" "$VENV" \
  && sudo systemctl restart flask-app.service && sudo systemctl try-restart nmas-ztp-responder.service \
  && wait_health; echo "   link: $(readlink "$VENV")"; \
  echo "   /health: $(curl -s -o /dev/null -m 5 -w "%{http_code}" http://127.0.0.1:5000/health)"; \
  echo "   the app loads from: $(grep -o "/opt/mercury-venv-[0-9a-f]*/" /proc/$(systemctl show -p MainPID --value flask-app.service)/maps | sort -u | tr "\n" " ")"'
export ON_FAIL ON_FAIL_WHAT
step "swap the link to mercury-venv-$ID (a rename: never half there)" \
    'sudo ln -s "mercury-venv-$ID" "$VENV.new" && sudo mv -T "$VENV.new" "$VENV"'
check "the link points at the release's venv" eq "$DIR" 'readlink -f "$VENV"'
step "restart the app, and the ZTP responder if it is running" \
    'sudo systemctl restart flask-app.service && sudo systemctl try-restart nmas-ztp-responder.service'
check "flask-app is active" eq "active" 'systemctl is-active flask-app.service'
wait_health
check "the app answers /health" eq "200" \
    'curl -s -o /dev/null -m 5 -w "%{http_code}" http://127.0.0.1:5000/health'
# Its maps name the REAL folder its extension modules came from: exactly the release's venv.
check "the app's process loads from the release's venv" eq "$DIR/" \
    'grep -o "/opt/mercury-venv-[0-9a-f]*/" /proc/$(systemctl show -p MainPID --value flask-app.service)/maps | sort -u'
# The same runs their hourly timers make (Loki and Prometheus reads, no device session).
# Measured 2026-10-09: 13 s and under 1 s; bounded at 40 s. When each notice last started is
# read first, so an earlier run's result never answers for this one.
BEFORE=$(for u in $FINISHED; do systemctl show -p ExecMainStartTimestampMonotonic --value "$u"; done | tr '\n' ' ')
export BEFORE
step "run the heartbeat and telemetry checks once" \
    'sudo timeout 40 systemctl start nmas-heartbeat-check.service nmas-telemetry-check.service'
check "the heartbeat and telemetry checks run and succeed from the venv" eq "success success" \
    'echo $(systemctl show -p Result --value nmas-heartbeat-check.service) $(systemctl show -p Result --value nmas-telemetry-check.service)'
for i in $(seq 1 10); do
    [ "$(systemctl is-active $FINISHED | sort -u)" = inactive ] && break
    sleep 1
done
check "the job-finished notices they started succeed from the venv" eq "success success" \
    'set -- $BEFORE; for u in $FINISHED; do now=$(systemctl show -p ExecMainStartTimestampMonotonic --value "$u"); \
       if [ "$now" -gt "$1" ]; then printf "%s " "$(systemctl show -p Result --value "$u")"; else printf "%s " "not-started-since($u)"; fi; shift; done | sed "s/ $//"'
# Proved: no more swapping back. Keep the current and the previous (the operator, 2026-10-09);
# remove the older ones no process has loaded (every process's maps, read as root), each named.
ON_FAIL=""
check "the previous venv is kept and the link to it recorded" eq "$FROM" 'readlink -f "$PREVIOUS"'
step "remove venvs older than the previous one that no process has loaded" \
    'for d in /opt/mercury-venv-*; do
        [[ "$d" =~ ^/opt/mercury-venv-[0-9a-f]{12}$ ]] || continue
        [ "$d" = "$DIR" ] || [ "$d" = "$FROM" ] && continue
        if sudo grep -qs -- "$d/" /proc/[0-9]*/maps; then echo "   kept $d: a running process has it loaded"; continue; fi
        sudo rm -rf -- "$d" && echo "   removed $d"
     done'
check "only the current and previous venvs remain, or a running process holds the rest" eq "" \
    'for d in /opt/mercury-venv-*; do [[ "$d" =~ ^/opt/mercury-venv-[0-9a-f]{12}$ ]] || continue; \
       [ "$d" = "$DIR" ] || [ "$d" = "$FROM" ] && continue; \
       sudo grep -qs -- "$d/" /proc/[0-9]*/maps || echo "$d"; done'
echo "Left to their timers, read in Job health after their next runs: the startup check, the"
echo "NetBox backup and the NetBox restore test. To go back: bash scripts/host-steps/venv-rollback.sh."
summary
