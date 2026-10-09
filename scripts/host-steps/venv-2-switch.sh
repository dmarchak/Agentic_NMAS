#!/usr/bin/env bash
# DRAFT, not approved to run (the operator, 2026-10-09). Phase 4 section 8, step 2 of 3: point
# everything that runs Mercury's code at Mercury's virtualenv (built and proved by
# venv-1-build.sh), restart what is running, and prove each runs from the venv. No unit file is
# edited, so venv-3-rollback.sh undoes this by removing three files. The operator's, on the app
# host:
#     bash <checkout>/scripts/host-steps/venv-2-switch.sh
#
# What it covers (section 8's inventory, the operator's request 2026-10-09):
#   flask-app.service    its own drop-in: ExecStart through the venv's interpreter, and PATH, so
#                        anything the app starts that names python3 finds the venv's too.
#   every nmas- unit     ONE drop-in in nmas-.service.d/: systemd applies it to every unit whose
#                        name begins "nmas-" (systemd.unit(5): a name is also searched truncated
#                        after each dash), templates' instances and units installed later
#                        included. It sets PATH, which their `#!/usr/bin/env python3` scripts
#                        resolve: heartbeat-check, job-finished@, netbox-backup,
#                        netbox-restore-test, startup-check, telemetry-check, ztp-responder, and
#                        update (root, the updater: stdlib and PyYAML, then the venv's).
#   login shells         /etc/profile.d/mercury-venv.sh puts the venv first, so a script a
#                        person runs (nmas-deploy, nmas-tier2-probe, nmas-breakglass, ...) and
#                        every `python3 scripts/...` the app prints find the venv's interpreter.
# Kept on /usr/bin/python3: the lab's topology service (lab tooling, deploy/topology/; it imports
# no Mercury module, names /usr/bin/python3 itself, and needs networkx, which the lock does not
# carry), and the host-step scripts' own `/usr/bin/python3 -c` lines (they measure the system
# interpreter on purpose).
#
# A restart of the app, and of the ZTP responder if it is running: no device is touched. It runs
# the heartbeat and telemetry checks once, the same runs their hourly timers make (Loki and
# Prometheus reads, no device session); the startup check (SSH to every device) and the NetBox
# backup and restore test are left to their timers, and Job health shows their next results.
. "$(dirname "$0")/lib.sh"

VENV=/opt/mercury-venv
APP_DROPIN_DIR=/etc/systemd/system/flask-app.service.d
APP_DROPIN=$APP_DROPIN_DIR/mercury-venv.conf
UNITS_DROPIN_DIR=/etc/systemd/system/nmas-.service.d
UNITS_DROPIN=$UNITS_DROPIN_DIR/mercury-venv.conf
PROFILE=/etc/profile.d/mercury-venv.sh
APP=$(systemctl show -p ExecStart --value flask-app.service | sed -n 's/.*argv\[\]=[^ ]* \([^ ;]*app\.py\).*/\1/p')
# systemd's own PATH for its units, measured here (2026-10-09: /usr/local/sbin:/usr/local/bin:
# /usr/sbin:/usr/bin:/snap/bin), with the venv first. Setting PATH replaces systemd's, so it is
# read, never typed.
UNIT_PATH="$VENV/bin:$(systemctl show-environment | sed -n 's/^PATH=//p')"
# Every nmas- service on this host, a template named by an instance so systemd resolves its
# drop-ins (showing an instance loads it; nothing starts).
UNITS="flask-app.service $(systemctl list-unit-files --no-legend --type=service 'nmas-*' \
    | awk '{print $1}' | sed 's/@\.service$/@venv-check.service/' | tr '\n' ' ')"
export VENV APP_DROPIN_DIR APP_DROPIN UNITS_DROPIN_DIR UNITS_DROPIN PROFILE APP UNIT_PATH UNITS

plan "run as the operator's own user, not root" \
     "venv-1-build.sh ran: the venv's interpreter exists" \
     "flask-app runs app.py today, and its path is read" \
     "systemd's PATH for units is read" \
     "the nmas- units on this host are listed" \
     "no unit sets its own PATH (the drop-ins' PATH would replace it)" \
     "flask-app runs from the venv" \
     "every unit takes the venv's drop-in" \
     "python3 on every unit's PATH is the venv's" \
     "flask-app is active" \
     "the app answers /health" \
     "the app's process is the venv's interpreter" \
     "every running unit's process has the venv first on its PATH" \
     "the heartbeat and telemetry checks run and succeed from the venv" \
     "the job-finished notices they started succeed from the venv" \
     "a login shell's python3 is the venv's"

not_root
check "venv-1-build.sh ran: the venv's interpreter exists" rc0 "" '[ -x "$VENV/bin/python" ]'
check "flask-app runs app.py today, and its path is read" re '/app\.py$' 'echo "$APP"'
check "systemd's PATH for units is read" re '/usr/bin' 'echo "$UNIT_PATH"'
# Measured 2026-10-09: flask-app and 8 nmas- services.
check "the nmas- units on this host are listed" ge 9 'echo $UNITS | wc -w'
check "no unit sets its own PATH (the drop-ins' PATH would replace it)" eq "" \
    'for u in $UNITS; do case " $(systemctl show -p Environment --value "$u")" in *" PATH="*) echo "$u";; esac; done'

# Rendered into one fresh folder, installed by name.
RENDER=$(mktemp -d)
export RENDER
step "render the two drop-ins and the login-shell PATH" \
    'printf "[Service]\nEnvironment=\"PATH=%s\"\nExecStart=\nExecStart=%s %s\n" "$UNIT_PATH" "$VENV/bin/python" "$APP" > "$RENDER/flask-app.conf" \
     && printf "[Service]\nEnvironment=\"PATH=%s\"\n" "$UNIT_PATH" > "$RENDER/nmas.conf" \
     && printf "# Mercury: its virtualenv first (Phase 4 section 8; removed by venv-3-rollback.sh).\ncase \":\$PATH:\" in *\":%s:\"*) ;; *) PATH=\"%s:\$PATH\"; export PATH ;; esac\n" "$VENV/bin" "$VENV/bin" > "$RENDER/profile.sh"'
step "install them, by name" \
    'sudo install -d -m 0755 "$APP_DROPIN_DIR" "$UNITS_DROPIN_DIR" \
     && sudo install -m 0644 "$RENDER/flask-app.conf" "$APP_DROPIN" \
     && sudo install -m 0644 "$RENDER/nmas.conf" "$UNITS_DROPIN" \
     && sudo install -m 0644 "$RENDER/profile.sh" "$PROFILE"'
step "reload systemd, restart the app, and the ZTP responder if it is running" \
    'sudo systemctl daemon-reload && sudo systemctl restart flask-app.service \
     && sudo systemctl try-restart nmas-ztp-responder.service'

check "flask-app runs from the venv" has "$VENV/bin/python" \
    'systemctl show -p ExecStart --value flask-app.service'
check "every unit takes the venv's drop-in" eq "" \
    'for u in $UNITS; do case " $(systemctl show -p Environment --value "$u")" in *" PATH=$VENV/bin:"*) ;; *) echo "$u";; esac; done'
# What `#!/usr/bin/env python3` finds on each unit's own PATH, read back from systemd.
check "python3 on every unit's PATH is the venv's" eq "" \
    'for u in $UNITS; do p=$(systemctl show -p Environment --value "$u" | tr " " "\n" | sed -n "s/^PATH=//p"); \
       [ "$(env -i PATH="$p" python3 -c "import sys; print(sys.prefix)" 2>&1)" = "$VENV" ] || echo "$u"; done'
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
check "the app's process is the venv's interpreter" has "$VENV/bin/python" \
    'tr "\0" " " < /proc/$(systemctl show -p MainPID --value flask-app.service)/cmdline'
# Every unit running now (flask-app; the ZTP responder when a request started it): its process's
# own environment, which the operator's user can read (the units run as that user).
check "every running unit's process has the venv first on its PATH" eq "" \
    'for u in $UNITS; do pid=$(systemctl show -p MainPID --value "$u"); [ "$pid" -gt 0 ] 2>/dev/null || continue; \
       tr "\0" "\n" < /proc/$pid/environ | grep -q "^PATH=$VENV/bin:" || echo "$u (pid $pid)"; done'
# The same runs their hourly timers make. Measured 2026-10-09: the heartbeat check 13 s, the
# telemetry check under 1 s; bounded at 40 s. Each one's end starts nmas-job-finished@<check>;
# when each last started is read first, so an earlier run's result never answers for this one.
FINISHED=$(for c in nmas-heartbeat-check nmas-telemetry-check; do
    printf 'nmas-job-finished@%s.service ' "$c"; done)
BEFORE=$(for u in $FINISHED; do systemctl show -p ExecMainStartTimestampMonotonic --value "$u"; done | tr '\n' ' ')
export FINISHED BEFORE
step "run the heartbeat and telemetry checks once" \
    'sudo timeout 40 systemctl start nmas-heartbeat-check.service nmas-telemetry-check.service'
check "the heartbeat and telemetry checks run and succeed from the venv" eq "success success" \
    'echo $(systemctl show -p Result --value nmas-heartbeat-check.service) $(systemctl show -p Result --value nmas-telemetry-check.service)'
# The notice posts to the app; it ran under 1 s when measured. Up to 10 s for both to finish.
for i in $(seq 1 10); do
    [ "$(systemctl is-active $FINISHED | sort -u)" = inactive ] && break
    sleep 1
done
# Each: "success" only when it started after the value read before the runs, else what it was.
check "the job-finished notices they started succeed from the venv" eq "success success" \
    'set -- $BEFORE; for u in $FINISHED; do now=$(systemctl show -p ExecMainStartTimestampMonotonic --value "$u"); \
       if [ "$now" -gt "$1" ]; then printf "%s " "$(systemctl show -p Result --value "$u")"; else printf "%s " "not-started-since($u)"; fi; shift; done | sed "s/ $//"'
check "a login shell's python3 is the venv's" eq "$VENV/bin/python3" \
    'env -i HOME="$HOME" bash -lc "command -v python3"'
echo "Left to their timers, read in Job health after their next runs: the startup check, the"
echo "NetBox backup and the NetBox restore test. The updater's first run from the venv is the"
echo "next Update."
echo "To undo: bash scripts/host-steps/venv-3-rollback.sh (removes the three files, restarts)."
summary
