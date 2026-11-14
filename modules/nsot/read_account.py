"""nsot/read_account.py — the read-only account as a feature, across the fleet (board R,
Credentials › Profiles › Read-only account; provisional, operator review pending: the operator,
2026-11-13, "Read-only account as a feature: Credentials shows fleet coverage …; "Add the
read-only account" as a chosen action (one device or many, no hand-typed YAML); rollout through
batch deploy (one preview, canary …, then waves, each verified)").

Three parts, each through a path that already exists (one home per action):

**Coverage** (`judge`, `read_coverage`, `view`): per device, the account its profiles give it
(`credentials.read_chain`, the chain the AI's reads resolve on), what its COMMITTED intent says
of it (its ``users`` entry naming ``read-account:profile:<profile>`` and the level),
what its COMMITTED golden holds (the ``username <account>`` line and its level: the device as
last captured, read through `repo.committed_golden_for`), and its newest probe record
(`scripts/nmas-read-account-probe` writes them under the data directory's
``probes/read-account/``). Never a password: names, levels, times and results. The reading is
a reader's (`modules/readers/read_account_coverage.py`): every device's intent and golden is
per-device work, which no page request does (CLAUDE.md, "No page load or badge poll waits on Grafana, Loki, NetBox, a device or a
computation"); the page draws
the held value and its age.

**Add the read-only account** (`add_preview`, `add_commit`): each chosen device's committed
intent gains its account's ``users`` entry at the account's level (`hostvars.with_read_account`)
and the level's lines for its dialect (`privilege_exec.read_account_lines`, through
`privilege_exec.with_entries`), as structured entries, never typed text; checked by the intent
editor's own `intent_edit.validate`; committed through `intent_edit.commit_many`, one commit per
network, as the verified person with their reason. The preview writes nothing; its hash binds
each device's base and the document that would be committed, and the commit recomputes it and
refuses, naming both hashes, when anything moved. A device is refused by name when no read-only
account resolves for it, or when its golden holds the account at another line (a deploy adds an
account, never changes one: `deploy.assert_credentials_unchanged` would refuse it).

**The rollout** (`rollout_plan`, `rollout_start`, `rollout_go_on`): the committed intent of the
chosen devices deployed through the batch deploy (`routes.deploy.plan_devices` for the one
preview, `fleet_change.run_batches` over `routes.deploy.apply_batch` for the run: each device's
program recomputed and refused if it moved, held, sent, verified, saved to startup only once it
verified, rolled back on failure, its receipt written), the first failure stopping it. The order:
the canary alone (the person's choice, else the first device the plan sends to), then waves of
the chosen size, then each device that carries Mercury's management path to another device (from
the Topology read, `paired_deploy.topology`), last and alone. The run pauses after the canary
for Go on, and before each management-path device for a confirm naming that device. One hash
binds every device's program, the order and the repository's HEAD.

IPv6: nothing here parses, compares or connects to an address; the account's lines and the
reads they open are the same for IPv4 and IPv6 (`privilege_exec`'s forms carry both).
"""

import hashlib
import json
import logging
import os
import re

log = logging.getLogger(__name__)

#: The Source: of an Add's commit (`repo.commit()`'s trailer, a slug).
SOURCE = "read-account-add"
#: Update the read-only account's lines' commit (C3583): its own source, its own action.
UPDATE_SOURCE = "read-account-update"
#: How many rows an open group lists before it says how many it leaves out (large fleets).
GROUP_ROWS = 50
#: The default wave size after the canary.
WAVE = 4
WAVE_MAX = 50

#: Each device's state, in the order the card leads with them: the states to act on first.
STATES = ("would_change", "no_account", "pending", "not_yet", "device_only", "holds")
STATE_WORDS = {
    "would_change": "can't be added",
    "no_account": "no read-only account",
    "pending": "intent says it, not deployed yet",
    "not_yet": "not yet",
    "device_only": "on the device, not in intent",
    "holds": "hold it",
}
STATE_KIND = {"would_change": "danger", "no_account": "warn", "pending": "info",
              "not_yet": "muted", "device_only": "warn", "holds": "ok"}
#: The states an Add may take: the rest hold it already or are refused by name.
ADDABLE = ("pending", "not_yet", "device_only")
#: A probe record's results, as the card words them.
PROBE_RESULTS = ("PASS", "INCOMPLETE", "FAIL", "UNREADABLE", "SIGN-IN REFUSED")

_PRIV = re.compile(r"\bprivilege\s+(\d{1,2})\b")


def level() -> int:
    """The read-only account's level (the operator's decision, 2026-11-13)."""
    from modules.nsot import privilege_exec
    return privilege_exec.READ_ACCOUNT_LEVEL


# ── coverage ──────────────────────────────────────────────────────────────────────────────────

def golden_accounts(text: str) -> dict:
    """``{username: level}`` for every ``username`` line *text* (a golden) holds; a line naming
    no privilege is level 1 (the device's default, which it never prints). Names and levels
    only, never the line, which carries the secret's form."""
    from modules.nsot.render_artifact import credential_lines

    out = {}
    for key, line in credential_lines(text or "").items():
        if not key.startswith("username:"):
            continue
        m = _PRIV.search(line)
        out[key.split(":", 1)[1]] = int(m.group(1)) if m else 1
    return out


def intent_account(doc) -> dict:
    """``{"profile", "level"}``: the read-only account *doc* (committed intent) names, or ``{}``."""
    from modules.nsot import hostvars

    for user in (doc or {}).get("users") or [] if isinstance(doc, dict) else []:
        if not isinstance(user, dict):
            continue
        profile = hostvars.read_account_profile(user.get("secret_ref"))
        if profile:
            try:
                lvl = int(user.get("privilege", 1))
            except (TypeError, ValueError):
                lvl = 1
            return {"profile": profile, "level": lvl}
    return {}


def resolved_profile(row: dict, accounts: dict) -> str:
    """The profile whose read-only account *row* (an inventory row) signs in with: the first of
    its chain carrying one (`credentials.read_chain`, as `credential_profiles_page.read_coverage`
    counts), or ``""``."""
    from modules import credentials

    chain = credentials.read_chain(row.get("role", ""), row.get("_site", ""),
                                   row.get("_platform", ""))
    return next((p for p in chain if (accounts.get(p) or {}).get("password_set")), "")


def judge(row: dict, network: str, intent_doc, golden: dict, accounts: dict,
          probe: dict = None, target: int = None, ping: bool = None) -> dict:
    """One device's coverage row: ``{"network", "device", "platform", "dialect", "profile",
    "account", "intent", "holds", "state", "why", "probe", "other_form"}``. *golden* is
    `golden_accounts` of its committed golden, or None when none is recorded; *accounts*
    `credentials.read_accounts` (names only); *probe* its newest probe record's summary;
    *update* the account's lines its committed intent holds in another form
    (`lines_to_update`), which Update the read-only account's lines changes."""
    from modules.nsot import platform as P

    target = level() if target is None else target
    device = row.get("hostname") or ""
    dialect = P.platform_for_device(row)
    profile = resolved_profile(row, accounts)
    account = (accounts.get(profile) or {}).get("username", "") if profile else ""
    intent = intent_account(intent_doc)
    update = lines_to_update(intent_doc, dialect, target, ping) if intent else []
    held = None
    if golden is not None and account and account in golden:
        held = {"level": golden[account]}
    out = {"network": network, "device": device, "dialect": dialect,
           "platform": P.FACT_WORDS.get(dialect, dialect or "unknown"),
           "profile": profile, "account": account, "intent": intent or None, "holds": held,
           "probe": probe or None, "state": "", "why": "", "golden": golden is not None,
           "other_form": update}
    if not profile:
        from modules import credentials
        chain = credentials.read_chain(row.get("role", ""), row.get("_site", ""),
                                       row.get("_platform", ""))
        return dict(out, state="no_account", why=(
            f"no read-only account resolves for {device}: none of its profiles "
            f"({', '.join(chain)}) carries one; set one on a profile first"))
    if held and held["level"] != target:
        return dict(out, state="would_change", why=(
            f"its golden holds {account} at level {held['level']}, and the account's level is "
            f"{target}: an account is added, never changed, so a deploy would refuse it "
            "(CredentialWouldChange)"))
    if held and intent and intent["level"] == target:
        return dict(out, state="holds", why="")
    if held:
        return dict(out, state="device_only", why=(
            f"its golden holds {account} at level {target}, and its committed intent "
            + (f"names it at level {intent['level']}" if intent else "does not name it")))
    if intent:
        return dict(out, state="pending", why=(
            "its committed intent names it" + (f" at level {intent['level']}"
                                               if intent["level"] != target else "")
            + ("; no golden is recorded yet" if golden is None else
               ", and its golden does not hold it: deploy it")))
    return dict(out, state="not_yet", why=("" if golden is not None
                                           else "no golden is recorded yet"))


def _golden_blobs(repo: str) -> dict:
    """``{path: blob}`` for every committed golden at HEAD (one ``git ls-tree``)."""
    from modules.nsot.repo import git

    rc, out, err = git(repo, "ls-tree", "-r", "HEAD", "--", "golden")
    if rc != 0:
        if "Not a valid object name" in (err or "") or "not a tree" in (err or ""):
            return {}
        raise RuntimeError(f"git ls-tree HEAD golden/ failed: {err or rc}")
    found = {}
    for line in out.splitlines():
        meta, _tab, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            found[path] = parts[2]
    return found


def read_network(network: str, accounts: dict, known: dict = None) -> dict:
    """*network*'s coverage: ``{"rows", "goldens": {blob: {username: level}}, "error"}``. Its
    devices as the AI's reads load them (`credential_profiles_page._read_rows`), its committed
    intent in two git calls (`neighbours.committed_intents`), and each committed golden read
    through `repo.committed_golden_for` only when its blob is not one *known* (the previous
    cycle's) has judged: a golden's text never changes for its blob."""
    from modules import credential_profiles_page as CP
    from modules.neighbours import committed_intents
    from modules.nsot import listref, manifest
    from modules.nsot import read_account_op as RAO
    from modules.nsot.repo import committed_golden_for

    rows = CP._read_rows(network)
    repo = listref.resolve(network).repo_dir
    intents, why = committed_intents(repo)
    if why:
        raise RuntimeError(why)
    blobs = _golden_blobs(repo)
    ping = _ping_choice()
    known, kept = dict(known or {}), {}
    out = []
    for row in rows:
        host = row.get("hostname") or ""
        if not host:
            continue
        ident, entry = manifest.find_by_name(repo, host)
        golden = None
        if entry and entry.get("golden"):
            rel = os.path.relpath(manifest.golden_path_for(repo, entry), repo).replace(os.sep, "/")
            blob = blobs.get(rel)
            if blob and blob in known:
                golden = known[blob]
            elif blob:
                text = committed_golden_for(repo, entry).get("text")
                golden = golden_accounts(text) if text is not None else None
                if golden is not None:
                    known[blob] = golden
            if blob and golden is not None:
                kept[blob] = golden
        probe = RAO.newest(network, host, identity=ident or "")
        out.append(judge(row, network, intents.get(host), golden, accounts, probe,
                         ping=ping))
    return {"rows": out, "goldens": kept, "error": ""}


def read_coverage(previous: dict = None) -> dict:
    """The reader's value: ``{"devices": [row], "networks": {network id: {"name", "error"}},
    "level", "goldens": {network id: {blob: summary}}}`` for every registered network, each map
    keyed by the network's one id (`listref.network_id`, C1903) and read through
    `listref.keyed`; the display name a screen draws is kept in the value (a row's
    ``network``, a network's ``name``). A network that cannot be read is named with its error,
    never left out."""
    from modules import credentials
    from modules.nsot import listref

    accounts = credentials.read_accounts()
    prev = (previous or {}).get("goldens") or {}
    devices, networks, goldens = [], {}, {}
    for name in sorted(listref._registry()):
        try:
            got = read_network(name, accounts, listref.keyed(prev, name, {}))
        except Exception as exc:                      # noqa: BLE001 (said per network)
            log.warning("read account coverage: %s was not read: %s", name, exc)
            networks[listref.network_id(name)] = {"name": name,
                                                  "error": f"{type(exc).__name__}: {exc}"}
            continue
        networks[listref.network_id(name)] = {"name": name, "error": ""}
        devices += got["rows"]
        goldens[listref.network_id(name)] = got["goldens"]
    return {"devices": devices, "networks": networks, "level": level(), "goldens": goldens}


def reads_as_unready(value: dict) -> list:
    """Why the read-only account cannot be what the AI's device reads sign in as
    ("AI device reads sign in as", C3661), from a coverage *value* (`read_coverage`'s):
    ``["<network> <device>: <why>", ...]``, one per device that does not hold the account at its
    level or whose newest probe did not PASS, and one per network that could not be read; ``[]``
    when every device in scope holds it and passed. A coverage that names no device is not
    ready either (nothing shows the account is held)."""
    out = []
    for nid, net in sorted(((value or {}).get("networks") or {}).items()):
        if (net or {}).get("error"):
            out.append(f"{net.get('name') or nid}: its devices could not be read "
                       f"({net['error']})")
    rows = (value or {}).get("devices") or []
    for row in rows:
        name = f"{row.get('network') or '?'} {row.get('device') or '?'}"
        if row.get("state") != "holds":
            out.append(f"{name}: {STATE_WORDS.get(row.get('state'), row.get('state') or '?')}")
            continue
        result = ((row.get("probe") or {}).get("result") or "")
        if result != "PASS":
            out.append(f"{name}: its newest probe " + (f"was {result}" if result
                                                       else "has not run"))
    if not rows and not out:
        out.append("no device is known to hold it: the coverage names none")
    return out


def reads_as_refusal(value: dict = None) -> str:
    """``""`` when "the read-only account" may be saved as whom the AI's device reads sign in
    as, else why, naming the devices that do not hold it with a passed probe (at most eight,
    then how many more). *value* is a coverage value; by default the coverage is read now
    (`read_coverage`, a decision reads live: CLAUDE.md, "Display only"), its golden summaries
    kept from the reader's last value by blob."""
    if value is None:
        prev = held().get("value") or {}
        try:
            value = read_coverage(prev)
        except Exception as exc:                      # noqa: BLE001 (closed, and said)
            return (f"the read-only account's coverage could not be read "
                    f"({type(exc).__name__}: {exc}), so it is not known that every device "
                    "holds it")
    missing = reads_as_unready(value)
    if not missing:
        return ""
    shown = missing[:8] + ([f"{len(missing) - 8} more"] if len(missing) > 8 else [])
    return ("the read-only account is offered only when every device holds it and its probe "
            f"passed, and {len(missing)} do not: " + "; ".join(shown))


def held() -> dict:
    """The reader's last good value and when it was read: ``{"value", "at", "why"}``; *value*
    None with *why* when nothing is held yet or the store cannot be read."""
    from modules import reader_job
    from modules.readers import read_account_coverage as RC

    got = reader_job.read_cached(RC.NAME)
    good = (got.get("doc") or {}).get("last_good") or {}
    if got["state"] != "ok" or not good:
        return {"value": None, "at": "", "why": got.get("why") or "not read yet"}
    return {"value": good.get("value") or {}, "at": good.get("value_at") or "", "why": ""}


def _matches(row: dict, q: str, network: str, platform: str, state: str) -> bool:
    if q and q.lower() not in (row.get("device") or "").lower():
        return False
    if network and row.get("network") != network:
        return False
    if platform and row.get("platform") != platform:
        return False
    if state == "probe_fail":
        return ((row.get("probe") or {}).get("result") or "") == "FAIL"
    return not state or row.get("state") == state


def view(value: dict, *, q: str = "", network: str = "", platform: str = "",
         state: str = "", open_group: str = "") -> dict:
    """The coverage region: the summary by result first, then the groups (the states to act on
    first), each collapsed unless *open_group*, an open one listing its first `GROUP_ROWS`
    rows; filters and search narrow every group and the view says it is a subset."""
    rows = list((value or {}).get("devices") or [])
    target = (value or {}).get("level") or level()
    shown = [r for r in rows if _matches(r, q, network, platform, state)]
    counts = {s: sum(1 for r in shown if r["state"] == s) for s in STATES}
    probe = {}
    for r in shown:
        key = (r.get("probe") or {}).get("result") or "never probed"
        probe[key] = probe.get(key, 0) + 1
    groups = []
    for s in STATES:
        members = [r for r in shown if r["state"] == s]
        if not members:
            continue
        words = STATE_WORDS[s] + (f" at level {target}" if s == "holds" else "")
        groups.append({"state": s, "words": words, "kind": STATE_KIND[s], "count": len(members),
                       "open": s == open_group, "rows": members[:GROUP_ROWS],
                       "left": max(0, len(members) - GROUP_ROWS)})
    summary = [{"state": s, "count": counts[s], "kind": STATE_KIND[s],
                "words": (STATE_WORDS[s] + (f" at level {target}" if s == "holds" else ""))}
               for s in STATES if counts[s]]
    return {"total": len(rows), "matching": len(shown),
            "subset": len(shown) != len(rows) or bool(q or network or platform or state),
            "summary": summary, "probe": sorted(probe.items(), key=lambda kv: -kv[1]),
            "groups": groups,
            "networks": sorted({r["network"] for r in rows}),
            "platforms": sorted({r["platform"] for r in rows}),
            "states": [(s, STATE_WORDS[s]) for s in STATES] + [("probe_fail", "probe FAIL")],
            "errors": sorted((n.get("name", ""), n.get("error", "")) for n in
                             ((value or {}).get("networks") or {}).values()
                             if isinstance(n, dict) and n.get("error")),
            "chosen": {"q": q, "network": network, "platform": platform, "state": state}}


# ── Add the read-only account ─────────────────────────────────────────────────────────────────

def _ping_choice() -> bool:
    from modules.ai import router_reads
    return bool(router_reads.ping_traceroute_on())


def _held_rows() -> dict:
    """``{(network, device): coverage row}`` from the held value (its golden as last read)."""
    value = held()["value"] or {}
    return {(r["network"], r["device"]): r for r in value.get("devices") or []}


def candidates() -> dict:
    """The picker: the held coverage's devices grouped by network, each with its state and
    whether an Add may take it; and the quick ticks (all not yet, a network's, a platform's)."""
    got = held()
    value = got["value"] or {}
    nets = {}
    for r in value.get("devices") or []:
        nets.setdefault(r["network"], []).append(
            {"device": r["device"], "platform": r["platform"],
             "words": STATE_WORDS.get(r["state"], r["state"]),
             "kind": STATE_KIND.get(r["state"], "muted"),
             "addable": r["state"] in ADDABLE or bool(r.get("other_form")),
             "other_form": len(r.get("other_form") or [])})
    return {"at": got["at"], "why": got["why"],
            "networks": [{"name": n, "devices": ds, "addable": sum(d["addable"] for d in ds)}
                         for n, ds in sorted(nets.items())],
            "not_yet": sum(1 for ds in nets.values() for d in ds if d["addable"]),
            "platforms": sorted({d["platform"] for ds in nets.values() for d in ds}),
            "level": value.get("level") or level()}


def picks_of(values) -> list:
    """``[(network, device)]`` from the form's ``device`` values, each ``<network>/<device>``
    (a network's name may hold a slash, a device's name never does: split at the last one)."""
    out = []
    for v in values or []:
        network, _sep, device = str(v).rpartition("/")
        if network and device and (network, device) not in out:
            out.append((network, device))
    return out


def _lines_for(dialect: str, account: str, profile: str, target: int, ping: bool) -> list:
    """What a deploy will send for the account on a device of *dialect*, masked, in order: the
    level's lines with their effect on other accounts, then the account's own line as the
    template renders it (`_common.j2`'s ``users``) with its value masked by reference. The
    level's lines are `privilege_exec.rendered`'s, so a line the template writes for an entry's
    leading words is shown too (C3580); an entry's effect stays on its own line."""
    from modules.nsot import hostvars, privilege_exec

    wanted = privilege_exec.read_account_lines(dialect, target, ping_traceroute=ping)
    effects = {privilege_exec.render_line(l["entry"]): l["effect"] for l in wanted}
    out = [{"line": line,
            "effect": effects.get(line, "the device writes this leading word's line with the "
                                        "line above it; no other command changes level")}
           for line in privilege_exec.rendered([l["entry"] for l in wanted])]
    ref = f"{hostvars.READ_ACCOUNT_PREFIX}{profile}"
    out.append({"line": (f"username {account}" + (f" privilege {target}" if target != 1 else "")
                         + f" {hostvars.READ_ACCOUNT_TYPED_KIND} <redacted:{ref}>"),
                "effect": "adds the account; a device that holds it at another line is refused"})
    return out


def add_preview(picks: list, *, target: int = None) -> dict:
    """What Add would commit for each of *picks* (``[(network, device)]``). Writes nothing.
    ``{"ok", "error", "taking": [{"network", "device", "platform", "change", "base", "text",
    "lines"}], "groups", "refused": [{"network", "device", "why"}], "holding": [...],
    "networks": {network id: {"name", "devices"}}, "hash", "level", "ping", "judged_at"}``, the
    per-network map keyed by the network's one id (C1903). A device is refused by name when no read-only account resolves for it, its golden (as the coverage last
    read it) holds the account at another level, its intent's own entry cannot take the level's
    lines (`privilege_exec.with_entries`), or the editor's checks refuse the result
    (`intent_edit.validate`)."""
    from modules.nsot import hostvars, intent_edit, listref, privilege_exec

    target = level() if target is None else target
    ping = _ping_choice()
    rows = _held_rows()
    out = {"ok": False, "error": "", "taking": [], "groups": [], "refused": [], "holding": [],
           "updating": [], "networks": {}, "hash": "", "level": target, "ping": ping,
           "judged_at": held()["at"]}
    if not picks:
        out["error"] = "no device is ticked"
        return out
    for network, device in picks:
        def refuse(why):
            out["refused"].append({"network": network, "device": device, "why": why})
        if not listref.exists(network):
            refuse(f"no network is named {network}")
            continue
        row = rows.get((network, device))
        if row is None:
            refuse(f"{device} is not in {network}'s devices as the coverage last read them")
            continue
        if row.get("other_form"):
            # Its intent holds the account's lines in another form: Add never changes a held
            # line in passing (`privilege_exec.with_entries`); Update the read-only account's
            # lines is the edit of its own (`update_preview`), offered here.
            out["updating"].append({"network": network, "device": device,
                                    "lines": list(row["other_form"])})
            continue
        if row["state"] == "holds":
            out["holding"].append({"network": network, "device": device})
            continue
        if row["state"] not in ADDABLE:
            refuse(row["why"])
            continue
        opened = intent_edit.open_doc(network, device)
        if not opened.get("ok"):
            refuse(opened.get("error") or "its committed intent could not be read")
            continue
        doc = hostvars.from_yaml(opened["yaml"])
        try:
            doc, change = hostvars.with_read_account(doc, row["profile"], target)
            doc, added = privilege_exec.with_entries(
                doc, [l["entry"] for l in privilege_exec.read_account_lines(
                    row["dialect"], target, ping_traceroute=ping)])
        except ValueError as exc:
            refuse(str(exc))
            continue
        if not change and not added:
            out["holding"].append({"network": network, "device": device})
            continue
        text = hostvars.to_yaml(doc)
        checked = intent_edit.validate(device, text, network)
        if not checked.get("ok"):
            refuse(f"the intent editor refuses the result: {checked.get('error')}")
            continue
        words = ([f"users gains {row['account']} (read-account:profile:{row['profile']}) at "
                  f"level {target}" if change == "added" else f"users: {row['account']} "
                  f"{change}"] if change else [])
        words += [f"privilege_exec gains `{privilege_exec.render_line(e)}`" for e in added]
        out["taking"].append({"network": network, "device": device, "platform": row["platform"],
                              "change": words, "base": opened["base"], "text": text,
                              "lines": _lines_for(row["dialect"], row["account"],
                                                  row["profile"], target, ping)})
        out["networks"].setdefault(listref.network_id(network),
                                   {"name": network, "devices": []})["devices"].append(device)
    groups = {}
    for t in out["taking"]:
        key = (t["platform"], tuple(t["change"]), tuple(l["line"] for l in t["lines"]))
        groups.setdefault(key, []).append(t)
    out["groups"] = [{"platform": k[0], "change": list(k[1]), "lines": ts[0]["lines"],
                      "devices": [t["device"] for t in ts]}
                     for k, ts in sorted(groups.items(), key=lambda g: (-len(g[1]), g[0]))]
    out["hash"] = hashlib.sha256(json.dumps({
        "level": target, "ping": ping,
        "taking": sorted((t["network"], t["device"], t["base"], t["text"])
                         for t in out["taking"]),
        "refused": sorted((r["network"], r["device"]) for r in out["refused"]),
        "holding": sorted((h["network"], h["device"]) for h in out["holding"]),
        "updating": sorted((u["network"], u["device"]) for u in out["updating"])},
        sort_keys=True).encode()).hexdigest()
    out["ok"] = True
    return out


def lines_to_update(intent_doc, dialect: str, target: int = None, ping: bool = None) -> list:
    """``[{"old", "new"}]``, each a rendered line: the account's lines (`privilege_exec.
    read_account_lines`) that *intent_doc* holds in another form (another level or ``all``),
    as `privilege_exec.with_updated_entries` would change them. A READ: nothing is written. An
    intent the key's checks refuse names nothing here (the update refuses it by name)."""
    from modules.nsot import privilege_exec

    if not isinstance(intent_doc, dict):
        return []
    target = level() if target is None else target
    try:
        _doc, changed = privilege_exec.with_updated_entries(
            intent_doc, [l["entry"] for l in privilege_exec.read_account_lines(
                dialect, target, ping_traceroute=ping)])
    except ValueError:
        return []
    return [{"old": privilege_exec.render_line(c["old"]),
             "new": privilege_exec.render_line(c["new"])} for c in changed]


def update_preview(picks: list, *, target: int = None) -> dict:
    """What Update the read-only account's lines would commit for each of *picks*
    (``[(network, device)]``; C3583): each device's committed intent with the account's lines
    it holds in another form changed to the account's set (`privilege_exec.
    with_updated_entries`, THE edit of its own: any other held entry stays as it is), each line
    old -> new, and the lines a deploy will then send, masked. Writes nothing. ``{"ok",
    "error", "taking": [{"network", "device", "platform", "changes": [{"old", "new"}], "base",
    "text", "lines"}], "groups", "current", "refused", "networks", "hash", "level", "ping",
    "judged_at"}``; *current* holds the devices whose lines are the set's already."""
    from modules.nsot import hostvars, intent_edit, listref, privilege_exec

    target = level() if target is None else target
    ping = _ping_choice()
    rows = _held_rows()
    out = {"ok": False, "error": "", "taking": [], "groups": [], "current": [], "refused": [],
           "networks": {}, "hash": "", "level": target, "ping": ping,
           "judged_at": held()["at"]}
    if not picks:
        out["error"] = "no device is ticked"
        return out
    for network, device in picks:
        def refuse(why):
            out["refused"].append({"network": network, "device": device, "why": why})
        if not listref.exists(network):
            refuse(f"no network is named {network}")
            continue
        row = rows.get((network, device))
        if row is None:
            refuse(f"{device} is not in {network}'s devices as the coverage last read them")
            continue
        opened = intent_edit.open_doc(network, device)
        if not opened.get("ok"):
            refuse(opened.get("error") or "its committed intent could not be read")
            continue
        doc = hostvars.from_yaml(opened["yaml"])
        try:
            doc, changed = privilege_exec.with_updated_entries(
                doc, [l["entry"] for l in privilege_exec.read_account_lines(
                    row["dialect"], target, ping_traceroute=ping)])
        except ValueError as exc:
            refuse(str(exc))
            continue
        if not changed:
            out["current"].append({"network": network, "device": device})
            continue
        text = hostvars.to_yaml(doc)
        checked = intent_edit.validate(device, text, network)
        if not checked.get("ok"):
            refuse(f"the intent editor refuses the result: {checked.get('error')}")
            continue
        out["taking"].append({
            "network": network, "device": device, "platform": row["platform"],
            "changes": [{"old": privilege_exec.render_line(c["old"]),
                         "new": privilege_exec.render_line(c["new"])} for c in changed],
            "base": opened["base"], "text": text,
            "lines": _lines_for(row["dialect"], row["account"], row["profile"], target, ping)})
        out["networks"].setdefault(listref.network_id(network),
                                   {"name": network, "devices": []})["devices"].append(device)
    groups = {}
    for t in out["taking"]:
        key = (t["platform"], tuple((c["old"], c["new"]) for c in t["changes"]),
               tuple(l["line"] for l in t["lines"]))
        groups.setdefault(key, []).append(t)
    out["groups"] = [{"platform": k[0], "changes": [{"old": o, "new": n} for o, n in k[1]],
                      "lines": ts[0]["lines"], "devices": [t["device"] for t in ts]}
                     for k, ts in sorted(groups.items(), key=lambda g: (-len(g[1]), g[0]))]
    out["hash"] = hashlib.sha256(json.dumps({
        "update": True, "level": target, "ping": ping,
        "taking": sorted((t["network"], t["device"], t["base"], t["text"])
                         for t in out["taking"]),
        "current": sorted((c["network"], c["device"]) for c in out["current"]),
        "refused": sorted((r["network"], r["device"]) for r in out["refused"])},
        sort_keys=True).encode()).hexdigest()
    out["ok"] = True
    return out


def update_commit(picks: list, confirmed: str, reason: str, actor: str) -> dict:
    """Commit the previewed Update as *actor* with *reason*, as Add commits (`_commit_previewed`:
    refused, naming both hashes and writing nothing, unless the preview made again has the
    confirmed hash; one commit per network, ``Source: read-account-update``)."""
    reason = " ".join((reason or "").split())
    if not reason:
        return {"ok": False, "error": "a reason is needed: it is recorded with the commit",
                "commits": []}
    p = update_preview(picks)
    return _commit_previewed(p, confirmed, reason, actor, source=UPDATE_SOURCE,
                             message=f"update the read-only account's lines at level "
                                     f"{p['level']}")


def add_commit(picks: list, confirmed: str, reason: str, actor: str) -> dict:
    """Commit the previewed Add as *actor* with *reason*: the preview made again and refused,
    naming both hashes and writing nothing, unless its hash is *confirmed*; then one
    `intent_edit.commit_many` per network (one commit each, ``Source: read-account-add``, the
    reason and the preview's hash as trailers). ``{"ok", "error", "commits": [{"network",
    "commit", "devices", "error"}], "preview"}``: a network refused after another committed says
    so, the committed one kept (each network's commit is whole or nothing)."""
    reason = " ".join((reason or "").split())
    if not reason:
        return {"ok": False, "error": "a reason is needed: it is recorded with the commit",
                "commits": []}
    p = add_preview(picks)
    return _commit_previewed(p, confirmed, reason, actor, source=SOURCE,
                             message=f"add the read-only account at level {p['level']}")


def _commit_previewed(p: dict, confirmed: str, reason: str, actor: str, *, source: str,
                      message: str) -> dict:
    """Add's and Update's one commit path: the preview *p* (made again) refused, naming both
    hashes and writing nothing, unless its hash is *confirmed*; then one
    `intent_edit.commit_many` per network (one commit each, *source*, the reason and the
    preview's hash as trailers)."""
    from modules.nsot import intent_edit

    if not p["ok"]:
        return {"ok": False, "error": p["error"], "commits": [], "preview": p}
    if p["hash"] != (confirmed or "").strip():
        return {"ok": False, "commits": [], "preview": p, "error": (
            f"the change moved since the preview you confirmed ({(confirmed or 'none')[:12]} -> "
            f"{p['hash'][:12]}): a device's intent, its golden or the account changed. Nothing "
            "was written; read the new preview and confirm it")}
    if not p["taking"]:
        return {"ok": False, "commits": [], "preview": p,
                "error": "no ticked device takes the change: there is nothing to commit"}
    commits = []
    for _nid, net in sorted(p["networks"].items()):
        network, devices = net["name"], net["devices"]
        edits = [(t["device"], t["text"], t["base"]) for t in p["taking"]
                 if t["network"] == network]
        got = intent_edit.commit_many(
            network, edits, message, actor,
            source=source, extra_trailers=[f"Reason: {reason}", f"Preview: {p['hash']}"])
        commits.append({"network": network, "devices": devices,
                        "commit": got.get("commit", "") if got.get("ok") else "",
                        "error": "" if got.get("ok") else (got.get("error") or "not committed")})
    failed = [c for c in commits if c["error"]]
    return {"ok": not failed, "commits": commits, "preview": p,
            "error": "; ".join(f"{c['network']}: {c['error']}" for c in failed)}


# ── the rollout ───────────────────────────────────────────────────────────────────────────────

def pending_of(network: str) -> list:
    """*network*'s devices whose committed intent names the account and whose golden does not
    hold it yet (the held coverage): the rollout's devices unless the person ticks others."""
    value = held()["value"] or {}
    return [r["device"] for r in value.get("devices") or []
            if r["network"] == network and r["state"] == "pending"]


def management_carriers(network: str, hosts: list) -> dict:
    """``{"carries": {device: [devices reached through it]}, "why"}``: for each of *hosts*, the
    other devices of *network* whose every shortest path from Mercury's host passes through it
    or may (`paired_deploy._paths_to`'s transit: with equal paths any may carry the traffic), from
    the Topology read. *why* says why it cannot be told (no read, no attachment), and then no
    device is known to carry it: the preview says so."""
    from modules.network_model import MANAGER_ID
    from modules.nsot import paired_deploy as PD

    topo = PD.topology(network)
    if topo.get("why"):
        return {"carries": {}, "why": topo["why"]}
    ids = topo.get("names") or {}
    g = PD._graph(topo.get("cables"))
    if MANAGER_ID not in g:
        return {"carries": {}, "why": ("the Topology read shows nowhere Mercury's host attaches, "
                                       "so its management path is unknown")}
    dist = PD._distances(g)
    label = {i: n for n, i in ids.items()}
    carries = {h: [] for h in hosts}
    for other, oid in sorted(ids.items()):
        paths = PD._paths_to(g, dist, oid)
        for node in (paths or {}).get("transit") or ():
            host = label.get(node)
            if host in carries and host != other:
                carries[host].append(other)
    return {"carries": {h: sorted(v) for h, v in carries.items() if v}, "why": ""}


#: The program lines that cannot cut a management path (the operator, 2026-11-14: "a program
#: that touches no interface, route, ACL or management-plane line (accounts and privilege lines
#: only) can't cut a management path"): an ALLOWLIST of exact shapes, the account's own
#: ``username`` line (its value masked or a device form) and a ``privilege exec`` line, each
#: top-level. Allowing by resemblance is not safe: any other line, an indented one included,
#: keeps a carrier last and alone.
_CANNOT_CUT = (
    re.compile(r"^username [A-Za-z0-9][A-Za-z0-9_.@-]{0,63}( privilege [0-9]{1,2})?"
               r"( algorithm-type (scrypt|sha256))? secret \S.*$"),
    re.compile(r"^privilege exec (all )?level [0-9]{1,2} [a-z0-9][a-z0-9 -]{0,120}$"),
)


def cannot_cut(program: list) -> bool:
    """Whether every line of *program* is one of `_CANNOT_CUT`'s exact shapes (accounts and
    privilege lines only), so the program cannot cut a management path. An empty program is
    not judged here (it sends nothing)."""
    lines = [l for l in program or [] if l.strip()]
    return bool(lines) and all(any(p.match(l) for p in _CANNOT_CUT) for l in lines)


def carrier_order(carriers: dict) -> tuple:
    """``(order, why)``: *carriers* (``{device: [devices reached through it]}``) in dependency
    order, each after every carrier reached through it (a carrier B reached through A goes
    before A, so A's change cannot cut Mercury off from B before B is changed), ties by name;
    *why* names the devices of a cycle (each reached through the other), which no order keeps
    reachable, and the order is then empty."""
    pending = {h: {d for d in reached if d in carriers and d != h}
               for h, reached in carriers.items()}
    out = []
    while pending:
        ready = sorted(h for h, needs in pending.items() if not needs)
        if not ready:
            cycle = sorted(pending)
            return [], (f"the devices carrying Mercury's management path reach each other "
                        f"({', '.join(cycle)}): no order changes each after every device "
                        "reached through it")
        for h in ready:
            out.append(h)
            del pending[h]
        for needs in pending.values():
            needs.difference_update(ready)
    return out, ""


def canary_refusal(canary: str, hosts: list, carriers: dict, unchanged=(), refused=()) -> str:
    """Why the person's *canary* cannot be the canary, or ``""`` (none chosen, or it can): it
    is not among the devices chosen, its program sends nothing, the deploy refuses it, or it
    carries Mercury's management path (naming the devices reached through it), which keeps it
    last. Said before the plan, never replaced silently (the operator, 2026-11-14)."""
    if not canary:
        return ""
    if canary in refused:
        return f"the canary you chose, {canary}, is refused by the deploy (see Refused below)"
    if canary in unchanged:
        return (f"the canary you chose, {canary}, has nothing to send: its device holds what "
                "its intent says")
    if canary not in hosts:
        return f"the canary you chose, {canary}, is not one of the devices to deploy"
    if canary in carriers:
        reached = carriers[canary]
        return (f"the canary you chose, {canary}, carries Mercury's management path"
                + (f" to {', '.join(reached)}" if reached else " (named by you)")
                + ", so it goes last, after every device reached through it; choose another")
    return ""


def order(hosts: list, canary: str, size: int, carriers: dict) -> tuple:
    """``(batches, confirm_at)``: the canary alone (the person's choice when it is one of
    *hosts* and carries no management path, else the first that carries none), then the rest in
    waves of *size*, then each management-path carrier alone, last, in dependency order
    (`carrier_order`: each after every carrier reached through it); *confirm_at* the indexes of
    the carriers' batches."""
    size = max(1, min(WAVE_MAX, int(size or WAVE)))
    plain = [h for h in hosts if h not in carriers]
    ranked, _why = carrier_order({h: carriers[h] for h in hosts if h in carriers})
    held_back = ranked or sorted(h for h in hosts if h in carriers)
    if not plain:
        return [[h] for h in held_back], list(range(len(held_back)))
    first = canary if canary in plain else plain[0]
    rest = [h for h in plain if h != first]
    batches = [[first]] + [rest[i:i + size] for i in range(0, len(rest), size)]
    confirm_at = list(range(len(batches), len(batches) + len(held_back)))
    return batches + [[h] for h in held_back], confirm_at


#: The longest settle between waves the rollout's form offers (the engine's own bound).
SETTLE_MAX = 3600


def fleet_change_options(options) -> dict:
    """The engine's options (`fleet_change.options_of`): the pause after the canary, off unless
    chosen, and the settle between waves."""
    from modules.nsot import fleet_change
    return fleet_change.options_of(options)


def blocked_words(why: str) -> str:
    """Why a rollout whose management path could not be measured is not offered: the
    comparison and both operands (an unreadable read neither passes nor fails)."""
    return (f"Mercury's management path could not be measured ({why}): the Topology read must "
            "be usable (it is not), or you name the devices that carry it (you named none). "
            "A guard that cannot read its input neither passes nor fails, so nothing is sent")


def rollout_plan(network: str, devices: list, canary: str = "", size: int = WAVE,
                 named=(), options=None) -> dict:
    """The rollout's ONE preview: each device's program from the deploy's own plan
    (`routes.deploy.plan_devices`: its exact lines, masked on the way out, its gates and its
    hash), the devices it sends nothing to, those it refuses with the deploy's reasons, the
    order (`order`) with each management-path carrier last and alone, and one hash over all of
    it and the repository's HEAD. Reads only; contacts no device; writes nothing.

    *named*: devices the person names as carrying Mercury's management path; each is a carrier
    too, last and alone on its own confirm. When the Topology read cannot be used and the
    person names none, the plan is ``blocked`` (`blocked_words`): it is drawn, and no confirm
    is offered or accepted."""
    from modules.nsot import listref
    from modules.nsot.repo import git
    from routes.deploy import plan_devices

    hosts = [d for d in dict.fromkeys(devices or []) if d]
    out = {"ok": False, "error": "", "network": network, "devices": [], "unchanged": [],
           "refused": [], "batches": [], "confirm_at": [], "carries": {}, "carries_why": "",
           "hash": "", "base": "", "canary": "", "size": max(1, min(WAVE_MAX, int(size or WAVE))),
           "named": [], "blocked": "", "account_only": [],
           "options": fleet_change_options(options)}
    if not listref.exists(network):
        out["error"] = f"no network is named {network}"
        return out
    if not hosts:
        out["error"] = "no device is chosen: none is waiting to be deployed"
        return out
    try:
        entries = {e["device"]: e for e in plan_devices(network, hosts)}
    except Exception as exc:                          # noqa: BLE001 (refused, by its words)
        out["error"] = f"the plan could not be made: {type(exc).__name__}: {exc}"
        return out
    value = held()["value"] or {}
    accounts = {(r["network"], r["device"]): r.get("account") or ""
                for r in value.get("devices") or []}
    for host in hosts:
        e = entries.get(host) or {}
        reasons = list(e.get("blocking_reasons") or [])
        if not e or not e.get("deployable", True) or reasons:
            out["refused"].append({"device": host,
                                   "reasons": reasons or ["not deployable, or not planned"]})
            continue
        lines = list(e.get("to_add") or [])
        if not lines:
            out["unchanged"].append(host)
            continue
        account = accounts.get((network, host), "")
        own = [l for l in lines if l.startswith("privilege exec ")
               or (account and l.startswith(f"username {account} "))]
        out["devices"].append({"device": host, "program": lines,
                               "besides": len(lines) - len(own),
                               "command_hash": e.get("command_hash", "")})
    # Each device's probe is part of its verify (`probe_after_verify`): planned here, touching
    # no device, its hash in the plan's; a device whose probe cannot be planned is refused.
    for d in list(out["devices"]):
        probe = _probe_plan(network, d["device"])
        if probe.get("refused"):
            out["devices"].remove(d)
            out["refused"].append({"device": d["device"], "reasons": [
                "its read-only account cannot be probed after verify: "
                + probe["refused"].replace("REFUSED: ", "", 1)]})
            continue
        d["probe"] = {"hash": probe["hash"], "account": probe["account"]["username"],
                      "reads": sum(1 for r in probe["reads"] if r.get("command")),
                      "refused": len(probe["refused_steps"]),
                      "not_measured": sorted(r["op"] for r in probe["reads"]
                                             if r.get("result") == "NOT MEASURED")}
    planned = [d["device"] for d in out["devices"]]
    carried = management_carriers(network, planned) if planned else {"carries": {}, "why": ""}
    out["carries"], out["carries_why"] = dict(carried["carries"]), carried["why"]
    out["named"] = [d for d in dict.fromkeys(named or []) if d in planned]
    for d in out["named"]:
        out["carries"].setdefault(d, [])
    # A program of accounts and privilege lines alone cannot cut a path (`cannot_cut`, an
    # allowlist of exact shapes): such a carrier joins the normal waves, and the plan says so.
    programs = {d["device"]: d["program"] for d in out["devices"]}
    out["account_only"] = sorted(d for d in out["carries"] if cannot_cut(programs.get(d)))
    kept = {d: v for d, v in out["carries"].items() if d not in out["account_only"]}
    if planned and out["carries_why"] and not out["named"] and any(
            not cannot_cut(programs[d]) for d in planned):
        out["blocked"] = blocked_words(out["carries_why"])
    _ranked, cycle = carrier_order(kept)
    if cycle:
        out["error"] = cycle
        return out
    why = canary_refusal(canary, planned, kept, out["unchanged"],
                         [r["device"] for r in out["refused"]])
    if why:
        out["error"] = why
        return out
    out["batches"], out["confirm_at"] = (order(planned, canary, out["size"], kept)
                                         if planned else ([], []))
    out["canary"] = out["batches"][0][0] if out["batches"] else ""
    rc, head, _err = git(listref.resolve(network).repo_dir, "rev-parse", "HEAD")
    out["base"] = head.strip() if rc == 0 else ""
    out["hash"] = hashlib.sha256(json.dumps({
        "network": network, "base": out["base"], "batches": out["batches"],
        "confirm_at": out["confirm_at"], "named": out["named"], "blocked": out["blocked"],
        "account_only": out["account_only"], "options": out["options"],
        "devices": sorted((d["device"], d["command_hash"]) for d in out["devices"]),
        "probes": sorted((d["device"], d["probe"]["hash"]) for d in out["devices"]),
        "unchanged": sorted(out["unchanged"]),
        "refused": sorted(r["device"] for r in out["refused"])},
        sort_keys=True).encode()).hexdigest()
    out["ok"] = True
    return out


def plan_start(network: str, devices: list, canary: str, size: int, actor: str,
               named=(), options=None) -> str:
    """`rollout_plan` as a job (every device's program is read: never a request's work); its
    payload masked; it announces `fleet_change` (fleet_change's plan announcer) when it ends."""
    from modules.nsot import capture_job, fleet_change
    from modules.outbound import mask_payload

    def work(_job):
        return mask_payload(rollout_plan(network, devices, canary, size, named, options))
    return capture_job.start(network, "Plan the read-only account's rollout", actor, work,
                             kind="read-only account rollout preview",
                             announce_keys=fleet_change.ANNOUNCE_KEYS, page=page_of(network),
                             announcer=fleet_change.ANNOUNCER)


#: Each running rollout's place, by job: the wave it is on and its devices' outcomes so far,
#: drawn in place by its card while it runs (`progress`). In memory, as its job is.
_PROGRESS: dict = {}


def progress(job: str) -> dict:
    """``{"wave", "state", "done": {device: outcome}}`` for a running rollout, or ``{}``."""
    return dict(_PROGRESS.get(job) or {})


def page_of(network: str) -> str:
    """The page a rollout's or its preview's job reopens from In progress: Credentials'
    Profiles, its card opened on the job (``ra_job``; the page draws it in place)."""
    from urllib.parse import quote
    return f"/v2/credentials/profiles?list={quote(network)}&ra_job={{job}}"


def _probe_plan(network: str, device: str) -> dict:
    """The probe's plan for *device* (`read_account_probe.plan`): touches no device."""
    from modules import read_account_probe
    return read_account_probe.plan(network, device, {})


#: The probe verdicts a device's verify passes on: PASS, and INCOMPLETE (every read the probe
#: could ask answered and every refused command was refused; a read Mercury holds no argument
#: for is not measured, which the plan names per device). FAIL and UNREADABLE roll it back.
PROBE_PASSES = ("PASS", "INCOMPLETE")


def probe_after_verify(network: str, plan: dict, actor: str):
    """THE apply's check after verify for the rollout (`routes.deploy.apply_batch`'s
    ``after_verify``): each device, still held and its save to startup held, probed signed in
    AS the read-only account (`read_account_probe.run`, *held*: inside the apply's hold), its
    record written to History. The probe's program is planned again and must be the one the
    plan confirmed (both hashes named); a FAIL, an UNREADABLE (the account cannot sign in) or a
    probe that cannot be made rolls the device back by the pipeline's own rollback and stops
    the run, which tells the team (`fleet_change.run_waves`). The probe's verdict rides on the
    device's result as ``probe``."""
    from modules import read_account_probe as P
    from modules.nsot import reads
    from modules.redact import known_secret_values

    confirmed = {d["device"]: (d.get("probe") or {}).get("hash", "")
                 for d in plan.get("devices") or []}

    def check(host, result, _ctx):
        p = _probe_plan(network, host)
        if p.get("refused"):
            return {"rollback": "the probe as the read-only account could not be made: "
                                + p["refused"].replace("REFUSED: ", "", 1)}
        if p["hash"] != confirmed.get(host):
            return {"rollback": (f"the probe's program moved since the plan you confirmed "
                                 f"({(confirmed.get(host) or 'none')[:12]} -> {p['hash'][:12]})"
                                 ": not sent")}
        dev = P._inventory(network)[host]
        rec = P.run(p, dev, actor, known_secret_values(), reads.cap_bytes(network), held=True)
        path = P.write_record(rec)
        v = rec.get("verdict") or {}
        result["probe"] = {"result": v.get("result", ""), "why": v.get("why", ""),
                           "record": os.path.basename(path)}
        if v.get("result") in PROBE_PASSES:
            return {}
        return {"rollback": (f"the probe signed in as {p['account']['username']} gave "
                             f"{v.get('result') or 'no verdict'}: {v.get('why', '')}")}
    return check


def _run(network: str, plan: dict, start_at: int, before: list, *, actor: str,
         actor_kind: str, job: str = "") -> dict:
    """One part of the run, its payload, through THE engine (`fleet_change.run_waves`): every
    wave from *start_at*, the canary first and the carriers last in their order, with no press
    between them; the settle waited between waves; a pause after the canary when the plan's
    options say so; the first failure rolled back, the rest named not started, the team told."""
    from modules.nsot import fleet_change
    from modules.outbound import mask_payload

    _PROGRESS[job] = {"wave": start_at, "state": "running", "done": {}}

    def on_wave(n, state):
        _PROGRESS.setdefault(job, {"done": {}}).update(wave=n, state=state)

    def on_device(event, name, result):
        if event != "start":
            _PROGRESS.setdefault(job, {"done": {}})["done"][name] = (result or {}).get(
                "outcome", "")

    got = fleet_change.run_waves(
        network, plan["batches"], fleet_change.plan_waves(
            network, plan, actor=actor, actor_kind=actor_kind, on_device=on_device,
            after_verify=probe_after_verify(network, plan, actor)),
        options=plan.get("options") or {}, start_at=start_at, before=before,
        label=f"The read-only account's rollout to {network}", on_wave=on_wave,
        link=page_of(network).format(job=job) if job else "", key=plan["hash"])
    _PROGRESS.pop(job, None)
    return mask_payload({"state": got["state"], "network": network, "plan": plan,
                         "next": got["next"], "waits": "canary" if got["state"] == "paused"
                         else "", "results": got["results"], "stopped": got["stopped"],
                         "not_started": got["not_started"], "told": got["told"],
                         "actor": actor})


def rollout_start(network: str, devices: list, canary: str, size: int, confirmed: str, *,
                  actor: str, actor_kind: str, named=(), options=None) -> str:
    """The ONE confirm, as a job: the plan made again with its options and refused unless its
    hash is *confirmed* (naming both; nothing sent: a changed option is a changed hash), and
    refused while its management path cannot be measured and no device is named for it
    (`blocked_words`); then the engine runs every wave by itself (`_run`)."""
    from modules.nsot import capture_job, fleet_change
    from modules.outbound import mask_payload

    def work(job):
        plan = rollout_plan(network, devices, canary, size, named, options=options)
        if not plan["ok"]:
            return mask_payload({"state": "refused", "network": network,
                                 "error": f"the plan cannot be made now: {plan['error']}"})
        if plan["blocked"]:
            return mask_payload({"state": "refused", "network": network,
                                 "error": plan["blocked"]})
        if plan["hash"] != (confirmed or "").strip():
            return mask_payload({"state": "refused", "network": network, "error": (
                f"the rollout moved since the preview you confirmed ({(confirmed or 'none')[:12]}"
                f" -> {plan['hash'][:12]}): a program, the order or the repository changed. "
                "Nothing was sent; preview it again")})
        if not plan["batches"]:
            return mask_payload({"state": "done", "network": network, "plan": plan, "next": 0,
                                 "waits": "", "results": [], "stopped": "", "actor": actor})
        return _run(network, plan, 0, [], actor=actor, actor_kind=actor_kind, job=job)
    return capture_job.start(network, "Roll out the read-only account", actor, work,
                             kind="read-only account rollout",
                             announce_keys=fleet_change.RUN_KEYS,
                             announcer=fleet_change.RUN_ANNOUNCER, page=page_of(network))


def go_on_refusal(run: dict, device: str = "") -> str:
    """Why a Continue for *run* is refused, or ``""``: it must be paused after its canary (the
    plan's option; the engine never waits anywhere else)."""
    if (run or {}).get("state") != "paused":
        return ("that rollout is not paused (it finished, stopped, or this server has no record "
                "of it); nothing was sent")
    return ""


def rollout_go_on(run: dict, *, actor: str, actor_kind: str) -> str:
    """Continue the rollout: the person's press after a pause, the rest of the run from the
    paused run's own record, as a job; each device's program is checked against the confirmed
    one before it is sent (`fleet_change.run_batches`)."""
    from modules.nsot import capture_job, fleet_change

    def work(job):
        return _run(run["network"], run["plan"], run["next"], run.get("results") or [],
                    actor=actor, actor_kind=actor_kind, job=job)
    return capture_job.start(run["network"], "Roll out the read-only account", actor, work,
                             kind="read-only account rollout",
                             announce_keys=fleet_change.RUN_KEYS,
                             announcer=fleet_change.RUN_ANNOUNCER,
                             page=page_of(run["network"]))


#: The rollout's steps, in order: the manual's How it works page names each.
STEPS = (
    ("preview", "Preview", "every chosen device's program from the deploy's own plan, masked, "
                           "and its probe's plan; the order, the options and one hash"),
    ("confirm", "Confirm", "the hash confirmed once by a verified person; the plan made again "
                           "and refused if it or an option moved"),
    ("canary", "Canary", "one device alone, held, sent, verified, probed signed in as the "
                         "account, then saved; a pause for your Continue only when the plan "
                         "chose one"),
    ("waves", "Waves", "the rest in waves of the chosen size, by themselves, the settle waited "
                       "between them, each device's program checked again before it is sent"),
    ("management", "Management path", "each device carrying Mercury's management path last, "
                                      "alone, after every device reached through it"),
    ("stop", "Stop", "the first device that does not deploy, verify and pass its probe is "
                     "rolled back, stops the rest, and the team is told"),
    ("record", "Record", "each device's receipt, and its golden committed after its save"),
)
