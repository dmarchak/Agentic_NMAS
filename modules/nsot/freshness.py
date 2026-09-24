"""modules/nsot/freshness.py — is Oxidized's copy of a device the approved one?

A redeploy replays **Oxidized's** copy of a config into a containerlab
startup file. So whatever Oxidized last polled is what the device boots with
next, whether or not anybody approved it. That is the whole risk, and it is a
**freshness** question rather than a source one: the sanitiser is not cleaning
up Oxidized's quirks, it compensates for two facts about running configs in
general (`no shutdown` re-injection, and the RSA key that is not in a running
config), and a golden has both blind spots identically.
:doc:`docs/STARTUP_FROM_GOLDEN.md` records how that was got wrong first.

**CONTENT, with time as CONTEXT.** *"Oxidized is newer"* on its own fires
constantly and means nothing — Oxidized polls, so its copy is newer than the
golden most of the time, including immediately after an approved save. The
finding is that the content **differs**; the timestamp then says which way:

=========  ========================  ====================================
content    Oxidized vs golden time   reading
=========  ========================  ====================================
same       any                       nothing to report — the normal case
differs    Oxidized **newer**        **a change nobody approved**
differs    golden newer              the approved state moved, Oxidized has
                                     not polled yet — a race, not a finding
=========  ========================  ====================================

WHAT IS COMPARED, AND WHY IT IS NOT THE SANITISED OUTPUT
-------------------------------------------------------
The **raw** config as Oxidized stores it, against the **golden**. Never the
sanitiser's output.

Both raw-Oxidized and golden are *captured running configs* — records of the
device. The sanitised file is a **derived** artefact: it adds its own
``! <host> - from Oxidized HEAD <sha>`` header, re-injects ``no shutdown``
into every addressed interface, appends ``crypto key generate rsa`` for
switches, and drops some twenty-five classes of line and block. Comparing a
transformation against its own input reports **every sanitiser rule as
drift**, permanently, on every device.

The header is only the loudest of those — and the least of them, since it is
a comment and :func:`normalize.strip_for_diff` removes it anyway. The
re-injected ``no shutdown`` and the ``crypto key`` lines are ordinary
configuration and would survive any normalisation, so a gate pointed at the
sanitised file would fire for ever on rules the sanitiser is *supposed* to
apply. Pointing it at the raw config also makes the answer independent of the
sanitiser: changing a sanitising rule cannot make the gate fire.

The question the gate asks is *"has this device's state moved away from the
approved one"*, which is a question about the **device**. The sanitiser's
compensations are not device state.

WHERE THIS IS CONSUMED — TWO MOMENTS, ONE MEASUREMENT
-----------------------------------------------------
* **The gate** (:func:`check` with configs supplied) — the sanitiser's
  pre-write check, the last moment before an unapproved state becomes
  durable. Refuses per device and names what differs.
* **The signal** (:func:`check` with none supplied, reading through the
  Oxidized client) — a report, continuous and cheap. It cannot refuse
  anything and should not try. Its value is **timing**: the gate discovers
  divergence when somebody is already preparing a redeploy; the signal
  discovers it while the person who caused it still remembers what they did.

THE GATE'S OWN WRONG-AND-LOOKS-RIGHT STATE
------------------------------------------
*The comparison could not run and the sanitiser wrote anyway.* Named before
building, because it is the state this whole module exists to make
impossible. It has five distinct causes and each is a **refusal**, never a
pass:

1. the NMAS could not be asked — the script stops, exactly as it does for the
   lab map, rather than writing unchecked;
2. a device has **no golden** — a device the gate could not check is not a
   device the gate passed (a pending device is exactly this);
3. a golden or a supplied config is **unreadable** — same rule as an
   unparseable file counting as a reference in the removed-definition check;
4. the verdicts do not **account for** every device asked about, and a run
   that checked **zero** devices refuses outright — a scan that found no
   offenders is indistinguishable from a scan that could not run;
5. the content differs and the **time is unknown** — *golden newer* is the
   only benign reading and it requires proof. Absent proof it is not a race.

And a sixth this module has to defend against by construction: **an
authorisation that outlives what it authorised.** A per-device flag would let
the *next* divergence through while the gate reported ``authorised``, which is
a wrong thing wearing a passing result. :func:`authorise` is therefore keyed
on a fingerprint of **the divergence itself**, so any change to what differs
invalidates it — the confirm-hash construction, applied here.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

#: Nothing to report: the content is the approved state.
MATCH = "match"
#: The finding. Content differs and Oxidized's copy is the newer one, so a
#: redeploy would bake in a change nobody approved.
UNAPPROVED = "unapproved"
#: Content differs and the GOLDEN is newer: the approved state has moved and
#: Oxidized has not polled yet. A race, not a finding.
POLL_RACE = "poll_race"
#: Content differs and a person authorised **this exact divergence**.
AUTHORISED = "authorised"
#: The comparison could not run. Never a pass — see the module docstring.
INCONCLUSIVE = "inconclusive"

VERDICTS = (MATCH, UNAPPROVED, POLL_RACE, AUTHORISED, INCONCLUSIVE)

#: What stops a write. `POLL_RACE` does not: the copy about to be written
#: predates an approved change rather than carrying an unapproved one, and it
#: is self-correcting at Oxidized's next poll. It is reported and counted,
#: never silent.
BLOCKING = (UNAPPROVED, INCONCLUSIVE)

AUTHORISATION_FILE = "freshness_authorisations.json"
DEFAULT_AUTHORISATION_HOURS = 24


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def parse_time(value):
    """A timestamp as an aware ``datetime``, or ``None``.

    ``None`` is a real answer and the caller must treat it as one: an
    unparseable time means the two copies **cannot be placed on a timeline**,
    which is a different fact from them being equal.

    A naive timestamp is read as UTC, and :func:`compare_device` records that
    it did so, so an assumption is never silent. Oxidized's index serialises
    times in several shapes depending on version; git's ``%cI`` is always
    offset-qualified.
    """
    text = (value or "").strip()
    if not text:
        return None
    # `UTC`/`GMT` as a trailing word: strptime's %Z parses it and returns a
    # NAIVE datetime, which is the one outcome that must not look aware.
    for suffix in (" UTC", " GMT", " utc"):
        if text.endswith(suffix):
            text = text[: -len(suffix)] + "+0000"
            break
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                    "%a %b %d %H:%M:%S %Y %z", "%a %b %d %H:%M:%S %Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _was_naive(value) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    return parse_time(text) is not None and not any(
        mark in text for mark in ("Z", "UTC", "GMT", "utc", "+"))


# ---------------------------------------------------------------------------
# The divergence fingerprint
# ---------------------------------------------------------------------------

def divergence_fingerprint(list_name: str, hostname: str,
                           only_left, only_right) -> str:
    """A hash of **what differs**, which is what an authorisation covers.

    Keyed on the list as well as the device, for the same reason a template
    secret is (``<list-slug>:<hostname>``): two lists may each hold an ``r1``,
    and an authorisation granted in one must not silently cover the other.

    The sorted line sets, not the raw diff, so a reordering that
    :func:`roundtrip.configs_equivalent` already treats as equivalent cannot
    change the fingerprint by itself.
    """
    payload = "\n".join([
        f"list={list_name}", f"device={hostname}",
        "left:", *sorted(only_left or []),
        "right:", *sorted(only_right or []),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The authorisation path — explicit, recorded, and scoped to one divergence
# ---------------------------------------------------------------------------

def _authorisation_path(list_name: str) -> str:
    """Where a list's authorisations live — **resolved, never created**.

    Deliberately not `get_list_data_dir()`, which calls `os.makedirs()`: this
    is read on the comparison path for every device, so resolving a path would
    bring a list into existence merely by asking whether a divergence was
    authorised. A typo would create a list; a read would leave a directory
    behind. `LISTS_DIR` is read at call time, which is also what lets a test
    point it somewhere else.
    """
    from modules import config as _config

    return os.path.join(_config.LISTS_DIR, _config.list_slug(list_name),
                        AUTHORISATION_FILE)


def _load_authorisations(list_name: str) -> list:
    try:
        with open(_authorisation_path(list_name), encoding="utf-8") as fh:
            records = json.load(fh)
    except (OSError, ValueError):
        return []
    return records if isinstance(records, list) else []


def authorisations(list_name: str, include_expired: bool = False) -> list:
    """Every recorded authorisation, newest last."""
    now = datetime.now(timezone.utc)
    rows = []
    for record in _load_authorisations(list_name):
        expires = parse_time(record.get("expires_at"))
        record = dict(record)
        record["expired"] = bool(expires and expires <= now)
        if record["expired"] and not include_expired:
            continue
        rows.append(record)
    return rows


def authorise(list_name: str, hostname: str, fingerprint: str,
              actor: str = "user", reason: str = "",
              hours: int = DEFAULT_AUTHORISATION_HOURS) -> dict:
    """Deliberately allow **this one divergence** to be written.

    The way through the gate, and there is no other — no switch, no per-device
    flag, no environment variable. A gate with no way through teaches
    operators to disable it, which is how the drift checker came to be off for
    24 days; a gate with a *switch* is one nobody turns back on.
    :func:`hostvars.authorise_retry` is the precedent: an explicit action,
    recorded with who and why.

    It expires, and it is keyed on the fingerprint of what differs. The
    legitimate case is an approved change whose golden is not saved yet, which
    is resolved in minutes to hours by saving it — an authorisation outliving
    that has stopped describing anything real.
    """
    if not (fingerprint or "").strip():
        return {"ok": False, "error": "no divergence fingerprint given"}
    if not (actor or "").strip():
        return {"ok": False,
                "error": ("an authorisation needs an actor — one with nobody "
                          "behind it is a bypass wearing a better name")}
    if not (reason or "").strip():
        return {"ok": False,
                "error": ("an authorisation needs a reason: it records why an "
                          "unapproved state was written")}

    now = datetime.now(timezone.utc)
    record = {
        "device": hostname,
        "list": list_name,
        "fingerprint": fingerprint,
        "actor": actor,
        "reason": reason,
        "at": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "expires_at": (now + timedelta(hours=max(1, int(hours)))).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"),
    }
    records = _load_authorisations(list_name)
    records.append(record)
    path = _authorisation_path(list_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    from modules.config import open_secure

    with open_secure(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(records, fh, indent=2, sort_keys=True)
        fh.write("\n")
    log.warning("freshness: divergence authorised for %s in %s by %s — %s",
                hostname, list_name, actor, reason)
    return {"ok": True, "record": record}


def _active_authorisation(list_name: str, hostname: str, fingerprint: str):
    for record in reversed(authorisations(list_name)):
        if (record.get("device") == hostname
                and record.get("fingerprint") == fingerprint):
            return record
    return None


# ---------------------------------------------------------------------------
# One device
# ---------------------------------------------------------------------------

def compare_device(list_name: str, hostname: str, golden_text, golden_at,
                   oxidized_text, oxidized_at) -> dict:
    """One device's verdict. Never raises; an unreadable side is inconclusive.

    ``golden_text`` / ``oxidized_text`` of ``None`` mean *could not be read*,
    which is not the same as empty and is never a match.
    """
    row = {"device": hostname, "verdict": INCONCLUSIVE, "reason": "",
           "only_left": [], "only_right": [],
           "golden_at": golden_at or "", "oxidized_at": oxidized_at or "",
           "fingerprint": "", "time_assumed_utc": False}

    if golden_text is None:
        row["reason"] = ("no golden config — nothing to compare against, so "
                         "this device cannot be said to be approved")
        return row
    if oxidized_text is None:
        row["reason"] = "Oxidized's copy could not be read"
        return row

    try:
        from modules.nsot import normalize, roundtrip

        # PROVENANCE COMMENTS OUT, BOTH SIDES, BEFORE THE COMPARATOR.
        # Measured: `strip_for_diff` drops NMAS's OWN header (that prefix is
        # in DIFF_PREFIXES) and keeps every other comment -- so Oxidized's
        # metadata header survives it and the gate would differ on Oxidized's
        # first line for every device on every run. The noise floor arriving
        # in the artefact chosen to avoid it, on the side nobody checked:
        # the store this project does not write.
        result = roundtrip.configs_equivalent(
            "\n".join(normalize.strip_provenance_comments(golden_text)),
            "\n".join(normalize.strip_provenance_comments(oxidized_text)))
    except Exception as exc:                   # noqa: BLE001
        row["reason"] = f"the comparison itself failed: {exc}"
        log.exception("freshness: comparison failed for %s", hostname)
        return row

    row["only_left"] = result["only_left"]
    row["only_right"] = result["only_right"]

    if result["equal"]:
        row["verdict"] = MATCH
        return row

    row["fingerprint"] = divergence_fingerprint(
        list_name, hostname, result["only_left"], result["only_right"])

    granted = _active_authorisation(list_name, hostname, row["fingerprint"])
    if granted:
        row["verdict"] = AUTHORISED
        row["authorisation"] = granted
        row["reason"] = (f"authorised by {granted.get('actor')} — "
                         f"{granted.get('reason')}")
        return row

    row["time_assumed_utc"] = _was_naive(golden_at) or _was_naive(oxidized_at)
    g_time, o_time = parse_time(golden_at), parse_time(oxidized_at)
    if g_time is None or o_time is None:
        missing = "the golden's" if g_time is None else "Oxidized's"
        row["reason"] = (
            f"the content differs and {missing} timestamp could not be read, "
            "so the two copies cannot be placed on a timeline. Only "
            "'the golden is newer' is benign, and that needs proving")
        return row

    if g_time > o_time:
        row["verdict"] = POLL_RACE
        row["reason"] = ("the approved state has moved and Oxidized has not "
                         "polled yet — writing this now gives the device a "
                         "startup config that predates the approved change")
        return row

    row["verdict"] = UNAPPROVED
    row["reason"] = ("Oxidized's copy is newer than the approved one and "
                     "differs from it — a change nobody approved, and a "
                     "redeploy would bake it in")
    return row


# ---------------------------------------------------------------------------
# A fleet
# ---------------------------------------------------------------------------

class PopulationUnaccounted(RuntimeError):
    """Verdicts and population disagree — a defect, reported as one."""


def _goldens(list_name: str) -> dict:
    from modules.nsot import repo as _repo

    out = {}
    for entry in _repo.list_goldens(list_name):
        name = (entry.get("hostname") or "").strip()
        if name:
            out[name.lower()] = entry
    return out


def _read_golden(entry) -> tuple:
    """``(text, saved_at)``; ``text`` is None when it could not be read."""
    if not entry:
        return None, ""
    try:
        with open(entry["path"], encoding="utf-8", errors="replace") as fh:
            return fh.read(), entry.get("saved_at") or ""
    except OSError as exc:
        log.warning("freshness: golden unreadable at %s: %s",
                    entry.get("path"), exc)
        return None, entry.get("saved_at") or ""


def check(list_name: str, supplied: dict = None, timeout: float = 15.0) -> dict:
    """Compare a fleet's Oxidized copies against its goldens.

    Two callers, one measurement:

    * **the gate** passes ``supplied`` — ``{hostname: raw config text}``, the
      exact bytes the sanitiser is about to write from. That removes both the
      poll race between the sanitiser's read and ours, and the question of
      which Oxidized revision was compared: there is only one copy, and it is
      the one in the caller's hand.
    * **the signal** passes nothing and the configs are fetched through the
      Oxidized client. Its population is **the inventory**, not the golden
      store — the drift checker iterated the golden store and a device with no
      golden was therefore in no count at all, not an error and not a skip,
      simply absent.

    Every device in the population lands in exactly one bucket and the totals
    are reconciled against it; a remainder is reported as a defect rather than
    dropped. A run that checked **zero** devices is a refusal.
    """
    report = {"ok": True, "list": list_name, "source": "supplied" if supplied
              else "oxidized", "devices": [], "counts": {}, "blocked": [],
              "errors": [], "checked": 0, "population": 0}

    goldens = _goldens(list_name)
    oxidized_times, population, nodes = {}, [], {}

    # THE DEVICE -> OXIDIZED NODE MAP, IN BOTH PATHS. `sync_targets()` is the
    # one producer of it, and the gate needs it as much as the signal: the
    # index that carries the TIMES is keyed on the node name, which is not
    # always the hostname.
    from modules.nsot.credential_rotation import sync_targets

    targets = sync_targets(list_name)
    if targets.get("ok"):
        for row in targets.get("targets", []):
            name = row.get("hostname") or ""
            if not name:
                continue
            if supplied is None:
                population.append(name)
            if not row.get("error") and row.get("oxidized_node"):
                nodes[name] = row["oxidized_node"]
    elif supplied is None:
        return {"ok": False, "list": list_name,
                "error": f"could not enumerate devices: {targets.get('error')}"}
    else:
        report["errors"].append(
            f"the device map could not be read ({targets.get('error')}), so "
            "Oxidized's timestamps cannot be matched to these devices")

    if supplied is not None:
        population = sorted(supplied.keys())
    else:
        population.sort()

    if not population:
        return {"ok": False, "list": list_name,
                "error": ("no devices to check. That is a fact about this "
                          "answer, not about the fleet — a comparison over an "
                          "empty population passes vacuously")}

    # THE TIMES ARE FETCHED IN BOTH PATHS TOO, and the gate is why.
    #
    # The first version read them only on the signal path, so every device
    # whose content differed came back INCONCLUSIVE — the gate could never
    # report the finding it exists for, and never distinguish an unapproved
    # change from a poll race. It would have refused every difference,
    # including the benign ones, which is how a gate gets switched off.
    #
    # Caught by a negative control aimed at something else: forcing an unknown
    # timestamp to read as a poll race broke the route test asserting 409,
    # which should not have depended on the timestamp at all.
    from modules.integrations.oxidized import OxidizedIntegration

    client = OxidizedIntegration(timeout=timeout)
    if not client.is_configured():
        if supplied is None:
            return {"ok": False, "list": list_name,
                    "error": "Oxidized is not configured — set its URL in Settings"}
        report["errors"].append(
            "Oxidized is not configured, so no timestamps are available: a "
            "differing device cannot be told from a poll race and is reported "
            "inconclusive")
    else:
        times = client.node_times()
        if not times.get("ok"):
            report["errors"].append(
                f"Oxidized's index could not be read: {times.get('error')} — "
                "every differing device is therefore inconclusive")
        oxidized_times = times.get("times", {})

    for hostname in population:
        golden_text, golden_at = _read_golden(goldens.get(hostname.lower()))

        node = nodes.get(hostname, hostname)
        oxidized_at = oxidized_times.get(node) or oxidized_times.get(hostname, "")

        if supplied is not None:
            oxidized_text = supplied.get(hostname)
            if oxidized_text is not None and not str(oxidized_text).strip():
                oxidized_text = None
        else:
            if hostname not in nodes:
                oxidized_text = None
                report["errors"].append(
                    f"{hostname}: no Oxidized node name in the device map")
            else:
                fetched = client.fetch_config(node)
                oxidized_text = fetched.get("config") if fetched.get("ok") else None
                if not fetched.get("ok"):
                    report["errors"].append(f"{hostname}: {fetched.get('error')}")

        try:
            row = compare_device(list_name, hostname, golden_text, golden_at,
                                 oxidized_text, oxidized_at)
        except Exception as exc:               # noqa: BLE001
            # A device that raised is INCONCLUSIVE, which blocks. It must not
            # vanish from the population: a device checked by nothing and
            # counted by nothing is the state the reconciliation below exists
            # to catch, and catching it here as well means it never gets that
            # far.
            log.exception("freshness: %s raised during comparison", hostname)
            row = {"device": hostname, "verdict": INCONCLUSIVE,
                   "reason": f"the comparison raised: {exc}",
                   "only_left": [], "only_right": [], "golden_at": golden_at,
                   "oxidized_at": oxidized_at, "fingerprint": "",
                   "time_assumed_utc": False}
        report["devices"].append(row)

    return reconcile(report, population)


def reconcile(report: dict, population: list) -> dict:
    """Counts, blocked list, and the accounting — every device in one bucket.

    Separate from :func:`check` so it can be exercised against a report with a
    verdict missing. *"All 9 clean"* over a ten-device fleet is textually
    identical to the same sentence over nine, which is how the drift checker
    lost a device for 24 days; a reconciliation only tested through the loop
    that feeds it is tested by a loop that never drops anything.
    """
    report["population"] = len(population)
    report["checked"] = len(report["devices"])
    counts = {verdict: 0 for verdict in VERDICTS}
    report["blocked"] = []
    for row in report["devices"]:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
        if row["verdict"] in BLOCKING:
            report["blocked"].append(row["device"])
    report["counts"] = counts

    missing = sorted(set(population) - {r["device"] for r in report["devices"]})
    accounted = sum(counts.values())
    if (accounted != report["population"]
            or report["checked"] != report["population"] or missing):
        report["ok"] = False
        report["defect"] = (
            f"{accounted} verdict(s) for {report['population']} device(s)"
            + (f", missing: {', '.join(missing)}" if missing else "")
            + " — the comparison did not account for every device it was "
              "asked about, so its answer covers an unknown subset")
    return report


def gate_summary(report: dict) -> str:
    """One line a human reads before an irreversible write."""
    if not report.get("ok"):
        return f"REFUSED — {report.get('error') or report.get('defect')}"
    counts = report.get("counts", {})
    return (f"{report.get('checked', 0)} of {report.get('population', 0)} "
            f"checked: {counts.get(MATCH, 0)} approved, "
            f"{counts.get(UNAPPROVED, 0)} unapproved, "
            f"{counts.get(POLL_RACE, 0)} poll race, "
            f"{counts.get(AUTHORISED, 0)} authorised, "
            f"{counts.get(INCONCLUSIVE, 0)} inconclusive")
