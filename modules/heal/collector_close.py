"""Mercury's half of closing ONE telemetry session the collector still holds (C3078): the
request written, the root-owned helper run, its outcome read back; and the peers the helper may
close, read from committed intent.

**Why it exists.** A dial-out stream can stop while the collector on Mercury's host still holds
its TCP session ESTABLISHED and the device's own connection is "Disconnecting": the device
cannot connect again until the collector's socket is closed. Closing another process's socket
needs root, and Mercury runs as an ordinary user, so the close is one root-owned helper,
`deploy/collector/mercury-collector-close`, installed by a person
(scripts/host-steps/c3078-collector-close-install.sh) and run only as `sudo -n <helper>` with
no argument. What it may close is its root-owned configuration's: one listener, and the peers
listed. Mercury chooses neither.

**Its home is `modules/heal/`** because the close is a step of the lost stream's repair, the
operation `modules/heal/resubscribe.py`, and reads intent as that operation and the stream's
diagnosis do (`diagnose_stream.receiver_of`, `resubscribe.Sources.addresses`). `modules/apps/`
is the controller's apps.

**ONE OPERATION CALLS IT** (C3078): the re-subscribe with the collector step
(`resubscribe.Sources.close`): its preview asks a dry run, which closes nothing, and its apply,
holding the device and confirmed by a verified person's hash, the one close. Beside it only
the dry-run script (`scripts/nmas-collector-close-dry-run`, which never closes) and the peers
script reach this module; no other screen or job closes a session.

- `request(peer, port, dry_run=, run_id=)`: one request and its outcome,
  ``{"ok", "code", "exit", "words", "tuple", "at"}``, for an operation's record and stepper.
  *code* is the helper's own (`closed`, `would_close`, `no_match`, `refused_peer`, ...; the
  helper's header lists each with its exit code), or one of this module's: `not_installed`
  and `sudo_refused` (`NOT_INSTALLED`: the helper is not there to run, with what to run),
  `busy`, `caller_bound`, `no_outcome`, `outcome_unmatched`, `caller_error`. It never raises.
- `peers(listener)`: each address a session to *listener* can come from, by committed intent.
  The install step writes them into the helper's configuration, as root; Mercury cannot change
  that list, so a new device's telemetry needs the install step run again.
"""

import fcntl
import ipaddress
import json
import logging
import os
import subprocess
import time

log = logging.getLogger(__name__)

#: Where the install step puts the helper and its configuration (the helper's own `INSTALLED`
#: and `CONFIG_PATH`; tests/test_collector_close_caller.py holds the three together).
HELPER = "/usr/local/sbin/mercury-collector-close"
CONFIG = "/etc/mercury/collector-close.conf"
#: sudo, never asking: a missing sudoers line is a refusal, never a prompt.
SUDO = ("sudo", "-n")
INSTALL_STEP = "scripts/host-steps/c3078-collector-close-install.sh"
MANUAL = ('the manual\'s "Re-subscribe a lost telemetry stream", under "Closing the '
          'collector\'s session"')
#: The helper bounds its own work: three `ss` runs at 5 s each (the find, the close, the last
#: read-back), its 2 s read-back wait and one 0.25 s pause, 17.25 s at the worst, and it names
#: the bound that fired. This bound is above that, so the helper's own words arrive, and it
#: fires only when sudo or the helper itself hangs. REASONED from the helper's bounds, not 2.5
#: times a measured run: no run on a host has been timed yet (C3078).
HELPER_WORST_S = 17.25
BOUND_S = 20
BOUND_WHY = (f"above the {HELPER_WORST_S} s the helper bounds its own work at (three `ss` "
             "runs at 5 s each, its 2 s read-back wait and one pause); reasoned, no run on a "
             "host has been timed yet")
#: The codes that mean the helper is not there to run: a person installs it.
NOT_INSTALLED = ("not_installed", "sudo_refused")
_SHOWN = 160


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _printable(text) -> str:
    return "".join(c if " " <= c <= "~" else "?" for c in str(text or "")[:_SHOWN])


def _to_install() -> str:
    return f"A person installs it once on Mercury's host with {INSTALL_STEP} ({MANUAL})"


def _run(argv, timeout: float) -> tuple:
    """``(exit, output, errors)`` of *argv*; raises what `subprocess.run` raises."""
    proc = subprocess.run(list(argv), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          timeout=timeout, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _outcome(text: str):
    """The helper's outcome from its last printed line, or None."""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return None
    try:
        got = json.loads(lines[-1])
    except ValueError:
        return None
    return got if isinstance(got, dict) and isinstance(got.get("code"), str) else None


def request(peer, port, *, dry_run, run_id, run=None, clock=time.time) -> dict:
    """Ask the helper to close the established session from *peer*:*port* to the configured
    listener (or, with *dry_run*, to say what it would close), as run *run_id*:
    ``{"ok", "code", "exit", "words", "tuple", "at"}``. *exit* is the helper's exit code, None
    when it was not run; *tuple* its ``{"local", "peer"}``, None when it gave none. Never
    raises: what went wrong here is a code and words too. *run(argv, timeout)* (tests) stands
    in for the one command."""
    def answer(code, words, *, ok=False, exit_code=None, session=None, at=None):
        return {"ok": ok, "code": code, "exit": exit_code, "words": words, "tuple": session,
                "at": at or _iso(clock())}

    try:
        return _request(peer, port, dry_run, run_id, run or _run, answer)
    except Exception as exc:                          # noqa: BLE001 (never into the caller)
        log.warning("collector_close: %s: %s", type(exc).__name__, exc)
        return answer("caller_error", f"the close was not asked for: {type(exc).__name__}: "
                                      f"{_printable(exc)}")


def _request(peer, port, dry_run, run_id, run, answer) -> dict:
    from modules import config

    if not isinstance(dry_run, bool):
        return answer("caller_error", f"dry_run is {type(dry_run).__name__}, not True or "
                                      "False, so nothing was asked")
    if not os.path.lexists(HELPER):
        return answer("not_installed", "the collector's close helper is not installed: "
                                       f"{HELPER} does not exist. {_to_install()}")
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
        req_path, out_path = cfg["request"], cfg["outcome"]
        if not isinstance(req_path, str) or not isinstance(out_path, str):
            raise ValueError("its request and outcome are not two paths")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return answer("not_installed", "the collector's close helper's configuration "
                                       f"{CONFIG} could not be read ({type(exc).__name__}: "
                                       f"{_printable(exc)}). {_to_install()}")
    folder = os.path.dirname(req_path)
    if not os.path.isdir(folder) or not os.access(folder, os.W_OK):
        return answer("not_installed", f"the request folder {folder} is absent or not "
                                       "writable by Mercury's user, so the helper was "
                                       "installed for another account or not at all. "
                                       f"{_to_install()}")
    lock = os.open(os.path.join(folder, "lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return answer("busy", f"another close is being asked for ({folder}/lock is "
                                  "held): one at a time, never queued. Nothing was asked")
        doc = {"id": str(run_id), "peer": str(peer), "port": str(port), "dry_run": dry_run}
        tmp = req_path + ".new"
        with config.open_secure(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, sort_keys=True) + "\n")
        os.replace(tmp, req_path)
        argv = [*SUDO, HELPER]
        try:
            rc, out, err = run(argv, BOUND_S)
        except subprocess.TimeoutExpired:
            return answer("caller_bound", f"`{' '.join(argv)}` did not end within {BOUND_S} s "
                                          f"({BOUND_WHY}): whether a session was closed is "
                                          "not known")
        except OSError as exc:
            return answer("not_installed", f"`{' '.join(argv)}` could not be run "
                                           f"({exc.strerror or type(exc).__name__}). "
                                           f"{_to_install()}")
        finally:
            # The helper removes the request it read; one it never read is not left for a
            # later run to find.
            try:
                os.unlink(req_path)
            except OSError:
                pass
        got = _outcome(out)
        if got is None and rc == 1:
            return answer("sudo_refused", f"sudo would not run {HELPER} without asking "
                                          f"(exit 1: {_printable(err.strip()) or 'no words'}): "
                                          "its sudoers line is absent or names another "
                                          f"account. {_to_install()}", exit_code=rc)
        if got is None:
            got = _outcome_file(out_path, str(run_id))
        if got is None:
            return answer("no_outcome", f"`{' '.join(argv)}` exited {rc} and printed no "
                                        f"outcome, and {out_path} holds none of run {run_id}: "
                                        "whether a session was closed is not known",
                          exit_code=rc)
        theirs = got.get("id")
        if theirs != str(run_id) and not (theirs == "" and got.get("ok") is not True):
            return answer("outcome_unmatched",
                          f"the helper's outcome carries the id {_printable(theirs)!r}, not "
                          f"this run's {str(run_id)!r}: it is another run's, so nothing is "
                          "known about this one", exit_code=rc)
        words = str(got.get("words") or "")
        ok = got.get("ok") is True and rc == 0
        if got.get("exit") != rc:
            ok = False
            words += f" (the helper exited {rc}, and its outcome says {got.get('exit')})"
        session = got.get("tuple") if isinstance(got.get("tuple"), dict) else None
        return answer(got["code"], words, ok=ok, exit_code=rc, session=session,
                      at=got.get("finished") if isinstance(got.get("finished"), str) else None)
    finally:
        os.close(lock)


def _outcome_file(path: str, run_id: str):
    """The outcome the helper wrote at *path*, when it is run *run_id*'s; else None."""
    try:
        with open(path, encoding="utf-8") as fh:
            got = _outcome(fh.read())
    except OSError:
        return None
    return got if got and got.get("id") == run_id else None


# ── The peers: from committed intent ────────────────────────────────────────────────────────

def _listener(text) -> tuple:
    """``(address, port, why)`` of ``<IPv4 address>:<port>``."""
    host, sep, port = str(text or "").rpartition(":")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return "", 0, f"{text!r} is not <IPv4 address>:<port>"
    if address.version != 4:
        return "", 0, (f"{text!r} is an IPv6 listener: an IPv6 listener is not served by the "
                       "close helper yet")
    if not sep or not port.isascii() or not port.isdigit() or not 0 < int(port) < 65536:
        return "", 0, f"{text!r} is not <IPv4 address>:<port>, the port 1 to 65535"
    return str(address), int(port), ""


def peers(listener, *, networks=None, intents_of=None) -> dict:
    """Every address a telemetry session to *listener* (``<IPv4 address>:<port>``) can come
    from, by committed intent: ``{"ok", "peers", "notes", "error", "failed"}`` (*failed*
    ``listener`` or ``intent`` when not ok). A device counts when a
    subscription's receiver (`diagnose_stream.receiver_of`) is *listener*; its addresses are
    the `source-address` its subscriptions declare, and, for a subscription declaring none,
    every IPv4 address intent gives its interfaces (the addresses the stream's diagnosis reads
    its sessions from). *notes* say, per device, what was left out and why (no IPv4 address;
    an IPv6 address, which the helper does not serve yet). A network whose intent cannot be
    read whole fails the whole read, naming it: a list missing a network's devices would look
    complete. Reads only; *networks* and *intents_of(network) -> (intents, error)* default to
    every network and its committed intent."""
    from modules.heal.diagnose_stream import receiver_of
    from modules.heal.resubscribe import Sources

    address, port, why = _listener(listener)
    if why:
        return {"ok": False, "peers": [], "notes": [], "error": why, "failed": "listener"}
    if networks is None:
        from modules.nsot import listref
        networks = listref.names()
    if intents_of is None:
        from modules.heal.bounce import committed_intents_of as intents_of
    found, notes = set(), []
    for network in networks:
        intents, err = intents_of(network)
        if intents is None:
            return {"ok": False, "peers": [], "notes": notes, "failed": "intent",
                    "error": f"{network}'s committed intent could not be read ({err}), so "
                             "the list would miss its devices: nothing is listed"}
        for device in sorted(intents):
            hv = intents[device] or {}
            mine = [r for r in (receiver_of(s.get("settings"))
                                for s in hv.get("telemetry") or [] if isinstance(s, dict))
                    if r.get("address") == address and r.get("port") == port]
            if not mine:
                continue
            candidates = [r["source"] for r in mine if r["source"]]
            if any(not r["source"] for r in mine):
                notes.append(f"{network} {device}: a subscription names no source-address, "
                             "so each of its interface addresses is listed")
                candidates += Sources(network).addresses(hv)
            v4, v6 = set(), set()
            for text in candidates:
                try:
                    got = ipaddress.ip_address(str(text))
                except ValueError:
                    notes.append(f"{network} {device}: its source-address {text!r} is not "
                                 "an address, so it is left out")
                    continue
                (v4 if got.version == 4 else v6).add(str(got))
            if v6:
                notes.append(f"{network} {device}: {len(v6)} IPv6 address"
                             f"{'' if len(v6) == 1 else 'es'} left out: an IPv6 peer is not "
                             "served by the close helper yet")
            if not v4:
                notes.append(f"{network} {device}: left out: intent gives it no IPv4 address "
                             f"a session to {address}:{port} can come from")
            found |= v4
    return {"ok": True, "notes": notes, "error": "", "failed": "",
            "peers": sorted(found, key=lambda a: int(ipaddress.ip_address(a)))}
