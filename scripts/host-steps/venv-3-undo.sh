#!/usr/bin/env bash
# DRAFT, not approved to run (Phase 4 section 8.3, signed off by the operator 2026-10-09). Only
# if needed: undo the first switch (venv-2-switch.sh) by removing the two drop-ins it installed,
# so flask-app and every nmas- unit run /usr/bin/python3 again, as before. The link and the
# venvs stay where they are, unused, until a person removes them; the scripts follow, since each
# takes the interpreter flask-app runs (section 8.1). Going back to the PREVIOUS venv is
# venv-rollback.sh, not this. The operator's, on the app host:
#     bash <checkout>/scripts/host-steps/venv-3-undo.sh
#
# It restarts the app, and the ZTP responder if it is running; the units their timers start
# take the system interpreter at their next run. No device is touched.
. "$(dirname "$0")/lib.sh"

VENV=/opt/mercury-venv
FILES="/etc/systemd/system/flask-app.service.d/mercury-venv.conf /etc/systemd/system/nmas-.service.d/mercury-venv.conf"
UNITS="flask-app.service $(systemctl list-unit-files --no-legend --type=service 'nmas-*' \
    | awk '{print $1}' | sed 's/@\.service$/@venv-check.service/' | tr '\n' ' ')"
export VENV FILES UNITS

plan "run as the operator's own user, not root" \
     "the nmas- units on this host are listed" \
     "the two drop-ins venv-2-switch.sh installed are gone" \
     "no unit's environment names the venv" \
     "python3 on every unit's PATH is /usr/bin's" \
     "flask-app runs /usr/bin/python3 again" \
     "flask-app is active" \
     "the app answers /health" \
     "the app's process is the system interpreter" \
     "no running unit's process has the venv on its PATH"

not_root
check "the nmas- units on this host are listed" ge 9 'echo $UNITS | wc -w'
for f in $FILES; do
    if [ -e "$f" ]; then
        F=$f; export F
        step "remove $f, by name" 'sudo rm "$F"'
    else
        echo "== $f is not there: nothing to remove; the checks below say what runs"
    fi
done
step "reload systemd, restart the app, and the ZTP responder if it is running" \
    'sudo systemctl daemon-reload && sudo systemctl restart flask-app.service \
     && sudo systemctl try-restart nmas-ztp-responder.service'
check "the two drop-ins venv-2-switch.sh installed are gone" eq "" \
    'for f in $FILES; do [ -e "$f" ] && echo "$f"; done; true'
check "no unit's environment names the venv" eq "" \
    'for u in $UNITS; do systemctl show -p Environment --value "$u" | grep -qF "$VENV" && echo "$u"; done; true'
# systemd's own PATH again: what `#!/usr/bin/env python3` finds for every unit.
check "python3 on every unit's PATH is /usr/bin's" eq "/usr" \
    'env -i PATH="$(systemctl show-environment | sed -n "s/^PATH=//p")" python3 -c "import sys; print(sys.prefix)"'
check "flask-app runs /usr/bin/python3 again" has "/usr/bin/python3" \
    'systemctl show -p ExecStart --value flask-app.service'
check "flask-app is active" eq "active" 'systemctl is-active flask-app.service'
echo "== waiting for /health (up to 60 s)"
for i in $(seq 1 30); do
    [ "$(curl -s -o /dev/null -m 3 -w '%{http_code}' http://127.0.0.1:5000/health)" = 200 ] \
        && { echo "   answering after about $((i * 2)) s"; break; }
    sleep 2
done
check "the app answers /health" eq "200" \
    'curl -s -o /dev/null -m 5 -w "%{http_code}" http://127.0.0.1:5000/health'
check "the app's process is the system interpreter" has "/usr/bin/python3" \
    'tr "\0" " " < /proc/$(systemctl show -p MainPID --value flask-app.service)/cmdline'
check "no running unit's process has the venv on its PATH" eq "" \
    'for u in $UNITS; do pid=$(systemctl show -p MainPID --value "$u"); [ "$pid" -gt 0 ] 2>/dev/null || continue; \
       tr "\0" "\n" < /proc/$pid/environ | grep -q "^PATH=.*$VENV" && echo "$u (pid $pid)"; done; true'
summary
