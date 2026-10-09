#!/usr/bin/env bash
# DRAFT, not approved to run (Phase 4 section 8.3, signed off by the operator 2026-10-09). Go
# back to the PREVIOUS venv after a swap: point the link /opt/mercury-venv at what
# /opt/mercury-venv.previous names (refused when it is absent or unproved), record the venv left
# as the new previous (so the swap can be made again), restart, and prove as the swap does. It
# never swaps back on its own: if the previous venv does not answer either, it stops FAIL with
# both venvs in place, and venv-3-undo.sh returns everything to /usr/bin/python3. Run it with
# the release that venv was built for checked out (the deploy's rollback), on the app host:
#     bash <checkout>/scripts/host-steps/venv-rollback.sh
. "$(dirname "$0")/lib.sh"

VENV=/opt/mercury-venv
PREVIOUS=/opt/mercury-venv.previous
FROM=$(readlink -f "$VENV" 2>/dev/null)
TO=$(readlink -f "$PREVIOUS" 2>/dev/null)
FINISHED=$(for c in nmas-heartbeat-check nmas-telemetry-check; do
    printf 'nmas-job-finished@%s.service ' "$c"; done)
export VENV PREVIOUS FROM TO FINISHED

plan "run as the operator's own user, not root" \
     "the link and the previous venv are read" \
     "the previous venv is proved" \
     "the link points at the previous venv" \
     "the venv left is recorded as the previous one" \
     "flask-app is active" \
     "the app answers /health" \
     "the app's process loads from the previous venv" \
     "the heartbeat and telemetry checks run and succeed from the venv" \
     "the job-finished notices they started succeed from the venv"

not_root
check "the link and the previous venv are read" re '^/opt/mercury-venv-[0-9a-f]{12} /opt/mercury-venv-[0-9a-f]{12}$' \
    'echo "$FROM $TO"'
check "the previous venv is proved" re '^id [0-9a-f]{12}$' 'head -1 "$TO/.mercury-proved"'
step "point the link at $(basename "${TO:-none}") (a rename: never half there)" \
    'sudo ln -s "$(basename "$TO")" "$VENV.new" && sudo mv -T "$VENV.new" "$VENV"'
check "the link points at the previous venv" eq "$TO" 'readlink -f "$VENV"'
step "record the venv left as the previous one" \
    'sudo ln -s "$(basename "$FROM")" "$PREVIOUS.new" && sudo mv -T "$PREVIOUS.new" "$PREVIOUS"'
check "the venv left is recorded as the previous one" eq "$FROM" 'readlink -f "$PREVIOUS"'
step "restart the app, and the ZTP responder if it is running" \
    'sudo systemctl restart flask-app.service && sudo systemctl try-restart nmas-ztp-responder.service'
check "flask-app is active" eq "active" 'systemctl is-active flask-app.service'
# Not measured: the app's start time after a restart; up to 60 s, saying how long it took.
echo "== waiting for /health (up to 60 s)"
for i in $(seq 1 30); do
    [ "$(curl -s -o /dev/null -m 3 -w '%{http_code}' http://127.0.0.1:5000/health)" = 200 ] \
        && { echo "   answering after about $((i * 2)) s"; break; }
    sleep 2
done
check "the app answers /health" eq "200" \
    'curl -s -o /dev/null -m 5 -w "%{http_code}" http://127.0.0.1:5000/health'
check "the app's process loads from the previous venv" eq "$TO/" \
    'grep -o "/opt/mercury-venv-[0-9a-f]*/" /proc/$(systemctl show -p MainPID --value flask-app.service)/maps | sort -u'
# The same runs their hourly timers make; measured 13 s and under 1 s, bounded at 40 s.
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
summary
