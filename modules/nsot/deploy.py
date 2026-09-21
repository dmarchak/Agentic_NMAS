"""nsot/deploy.py

The Phase 3c deploy contract.

Everything Phase 3b promised, enforced here at the boundary where a socket is
about to open:

* **Re-render from the template with real secrets in memory.** ``intended/`` is
  written masked and is therefore never a deploy source; this module never
  opens it.
* **``assert_no_mask()`` before the socket**, not after. A masked push that
  fails halfway is worse than one that never starts.
* **Refuse any artifact whose ``deployable`` is False.** That property is
  computed on a frozen dataclass, so there is nothing to override here either.

Deploys are **merge-only**. Lines present in the intended config and absent from
the device are pushed. Lines present on the device and absent from the intended
config are reported as **removal warnings** and never negated — no ``no``
command is generated anywhere in this module. ``configure replace`` is a
documented future option, not built.
"""

import logging

from modules.nsot.render_artifact import assert_no_mask

log = logging.getLogger(__name__)


class DeployRefused(RuntimeError):
    """Raised when the 3b contract refuses an artifact before any connection."""


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------

def render_for_deploy(host_vars: dict, platform: str, template_root: str = None,
                      template_name: str = "base.j2") -> str:
    """Render with **real** secrets, resolved in memory.

    Deliberately not reading ``intended/``: that file is written masked for
    display, so using it as a deploy source would push ``••••••••`` to a device.
    """
    from modules.nsot import roundtrip

    def _resolve(name: str) -> str:
        from modules.credentials import get_template_secret
        stored = get_template_secret(name)
        if stored:
            return stored
        # Fall back to the value the extractor captured — for a hashed secret
        # that IS the value, and it can never be re-derived.
        return (host_vars.get("secrets") or {}).get(name, "")

    kwargs = {"secret_lookup": _resolve, "template_name": template_name}
    if template_root:
        kwargs["template_root"] = template_root
    return roundtrip.render(host_vars, platform, **kwargs)


def assert_deployable(artifact) -> None:
    """Refuse a non-deployable artifact. Called before anything connects."""
    if not artifact.deployable:
        raise DeployRefused(
            f"{artifact.device} is not deployable: "
            + "; ".join(artifact.blocking_reasons))


def prepare_device(artifact, template_root: str = None) -> dict:
    """Produce the deploy-ready config for one device.

    Order matters and is asserted by tests: refuse → render with real secrets →
    mask check → only then may a caller open a socket.
    """
    assert_deployable(artifact)

    template_name = (artifact.template or "base.j2").split("/")[-1]
    # The artifact's own tree wins. Validation and deployment must read the
    # same templates, or the gate measures something other than what ships.
    root = template_root or getattr(artifact, "template_root", "") or None
    config = render_for_deploy(artifact.host_vars, artifact.platform,
                               template_root=root,
                               template_name=template_name)

    # The backstop. If a secret failed to resolve, the renderer emits a
    # placeholder and this catches it before it reaches a device.
    assert_no_mask(config, context="deploy")

    return {"device": artifact.device, "platform": artifact.platform,
            "config": config, "template": artifact.template}


# ---------------------------------------------------------------------------
# Merge-only diff
# ---------------------------------------------------------------------------

def merge_diff(intended_config: str, running_config: str) -> dict:
    """Lines to add, and lines present only on the device.

    Returns ``{"to_add", "removal_warnings", "unchanged_count"}``. Nothing in
    here generates a ``no`` command: removals are reported for a human to act
    on, never performed.
    """
    from modules.nsot import ifnames, normalize

    #: Neither a command nor a removal. A blank line pushed as configuration is
    #: a no-op at best, and it made ``to_add`` non-empty for a device with
    #: nothing to deploy — so "is there anything to do here" answered yes for
    #: every device. ``!`` and ``end`` were already excluded from removals but
    #: not from additions; both sides are filtered now, symmetrically.
    _NOT_A_COMMAND = ("", "!", "end")

    def _norm(text):
        lines = [ifnames.canonicalise_line(l.rstrip())
                 for l in normalize.strip_for_roundtrip(text)]
        return [l for l in lines if l.strip() not in _NOT_A_COMMAND]

    intended = _norm(intended_config)
    running = _norm(running_config)
    running_set = set(running)
    intended_set = set(intended)

    to_add = [l for l in intended if l not in running_set]
    # Section headers whose children are all present are not "additions".
    removal_warnings = [l for l in running if l not in intended_set]

    return {
        "to_add": to_add,
        "removal_warnings": removal_warnings,
        "unchanged_count": len(intended) - len(to_add),
    }


#: Mode control, not configuration. ``exit`` unwinds a sub-mode and cannot add
#: or remove a line, so it carries no provenance requirement. ``end`` is
#: deliberately **not** here and is never emitted: it drops out of config mode
#: entirely, and a command list that ends config mode part-way through is a
#: different program than the one the operator confirmed.
CONTROL_WORDS = ("exit",)


def _section_chains(config_text: str) -> list:
    """``[(line, [ancestors, outermost first]), …]`` for a config.

    IOS nests by indentation, so a line's ancestors are the nearest preceding
    lines at each smaller indent. A partial chain is worse than none: sending
    ``neighbor … activate`` after only ``router bgp 65001`` applies it to the
    wrong address family, silently and successfully.
    """
    from modules.nsot import ifnames, normalize

    out, stack = [], []
    for raw in normalize.strip_for_roundtrip(config_text):
        line = raw.rstrip()
        if not line.strip() or line.strip() in ("!", "end"):
            continue
        indent = len(line) - len(line.lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        canonical = ifnames.canonicalise_line(line)
        out.append((canonical, [entry[1] for entry in stack]))
        stack.append((indent, canonical))
    return out


def merge_commands(intended_config: str, running_config: str) -> list:
    """The exact command list to send: the merge diff, in sendable form.

    ``merge_diff()`` answers *what differs*. That is not a program: a line like
    ``` description NSoT-managed``` is an interface sub-command, and sending it
    on its own applies it in global configuration mode. This answers *what to
    send* — each added line preceded by its full ancestor chain, in order, with
    each contiguous group unwound afterwards.

    One ``exit`` per open level, deepest first. Requirement is "an ``exit`` at
    the end of each contiguous group"; for the one-level case that is exactly
    one, and for ``router bgp`` → ``address-family`` it has to be two or the
    next group starts inside the address family. A group whose chain is empty
    emits none — an ``exit`` from global configuration mode leaves config mode
    altogether.
    """
    diff = merge_diff(intended_config, running_config)
    wanted = list(diff["to_add"])
    if not wanted:
        return []

    remaining = dict.fromkeys(wanted)          # preserves order, de-duplicates
    commands, open_chain = [], []

    def _close():
        for _level in reversed(open_chain):
            commands.append("exit")
        open_chain.clear()

    for line, chain in _section_chains(intended_config):
        if line not in remaining:
            continue
        if chain != open_chain:
            _close()
            commands.extend(chain)
            open_chain = list(chain)
        commands.append(line)
        del remaining[line]

    _close()

    # The forward path's own notion of "the lines I am adding" must equal what
    # program_structure() calls a leaf. Asserting it here is what keeps the two
    # from drifting apart again: change either and this fails loudly, instead
    # of the rollback quietly disagreeing later.
    from modules.nsot import ifnames as _ifnames
    classified = {_ifnames.canonicalise_line(e["line"])
                  for e in program_leaves(commands)}
    expected = {_ifnames.canonicalise_line(l) for l in wanted
                if l not in remaining}
    if classified != expected:
        raise RuntimeError(
            "merge_commands and program_structure disagree about which lines "
            f"are configuration: {sorted(classified ^ expected)}")

    # Before anything connects. A command list that cannot be sent is a defect
    # in the intent, not a transport problem, and it should never become
    # something an operator confirms.
    assert_sendable(commands)

    if remaining:
        log.warning("deploy: %d diff line(s) had no place in the intended "
                    "config and were not sent: %s", len(remaining),
                    ", ".join(repr(l) for l in list(remaining)[:5]))
    return commands


#: Commands whose value is *everything* after the first token, so the first
#: token alone identifies the setting. Every other command encodes part of its
#: identity in later tokens — ``ip mtu`` and ``ip address`` are different
#: settings that share a first word, and matching them on ``ip`` put a
#: management address into a rollback for an MTU line.
#:
#: This is a structural distinction, not a positional one. A second-word rule
#: would separate those two by accident and pick wrong on the third shape it
#: met. When the precise key misses, there is no prior value and the answer is
#: to negate — searching harder is what produced both this bug and the header
#: bug.
FREE_FORM_COMMANDS = ("description", "banner", "remark", "name")


def _command_keys(line: str) -> tuple:
    """``(precise, broad)`` keys identifying *which setting* a line sets.

    Two keys, because one cannot cover both shapes:

    * ``switchport access vlan 10`` — the value is the last token, so the
      precise key ``switchport access vlan`` matches a line setting the same
      thing to a different value.
    * ``description some free text`` — the value is *everything* after the
      first word, so the precise key would be ``description some free`` and
      would never match ``description other text``. The broad key
      ``description`` does.

    The broad key is used only when a section contains exactly one line
    starting with that word; otherwise it is ambiguous (``ip address`` primary
    and secondary, several ``switchport`` lines) and the precise key decides.
    """
    words = line.strip().split()
    if not words:
        return "", ""
    if words[0] == "no":
        words = words[1:]
    if not words:
        return "", ""
    precise = words[0] if len(words) == 1 else " ".join(words[:-1])
    return precise, words[0]


def landed_leaves(pushed: list, landed) -> tuple:
    """Split a pushed program into ``(applied, rejected)`` leaves.

    *landed* is the set of lines the failure-state capture saw on the device
    that were not there before. ``None`` means the capture could not read the
    device, in which case everything pushed is treated as applied — the
    conservative answer when you do not know.
    """
    from modules.nsot import ifnames

    leaves = program_leaves(pushed)
    if landed is None:
        return leaves, []

    seen = {ifnames.canonicalise_line(l).strip() for l in landed}
    applied = [e for e in leaves
               if ifnames.canonicalise_line(e["line"]).strip() in seen]
    rejected = [e for e in leaves if e not in applied]
    return applied, rejected


def rollback_commands(pushed: list, pre_config: str, landed=None) -> list:
    """The inverse of exactly what was pushed, and nothing else.

    A config-mode replay of the pre-change snapshot cannot undo a change. It is
    a **merge**: it re-applies lines and removes none. IOS omits ``no shutdown``
    from an up interface's running config, so a snapshot taken before a
    ``shutdown`` contains no line to re-apply — replay leaves the interface
    down, calls ``save_config()``, and reports success. Rollback would have
    demonstrated itself working on the one change it cannot reverse, then
    persisted it.

    For each pushed line, inside its own header chain:

    * the pre-change config had a line setting the same thing → re-send that
      line, which restores the old value
    * it did not → negate the pushed line

    **This is the one place the tool generates a ``no`` command**, and it is
    bounded: every negation corresponds to a line this deploy added, verified by
    :func:`assert_rollback_provenance`. It is not "remove what the template does
    not mention" — that remains a warning, never an action.

    *landed* is what the failure-state capture actually saw reach the device.
    Undoing what was **pushed** rather than what **landed** is the same
    derive-from-the-wrong-source error as taking intent from current state, one
    level down: on a partial push the two differ by definition, and with
    ``error_pattern`` live a rollback line answering a rejected push line now
    raises — so a rejected command could take the repair down with it. Rejected
    lines are reported as *not undone — never applied*; provenance stays total
    because every emitted line traces to something that reached the device.

    ``None`` means the capture could not read the device. Everything pushed is
    then treated as applied, which is the conservative answer when you do not
    know what happened.
    """
    from modules.nsot import ifnames

    precise_index, broad_index = {}, {}
    for line, chain in _section_chains(pre_config):
        precise, broad = _command_keys(line)
        precise_index.setdefault((tuple(chain), precise), line)
        broad_index.setdefault((tuple(chain), broad), []).append(line)

    def _previous(chain, line):
        precise, broad = _command_keys(line)
        hit = precise_index.get((tuple(chain), precise))
        if hit is not None:
            return hit
        if broad not in FREE_FORM_COMMANDS:
            return None          # no prior value: the answer is to negate
        candidates = broad_index.get((tuple(chain), broad), [])
        return candidates[0] if len(candidates) == 1 else None

    # Recover each pushed line's chain from the pushed program itself: the
    # headers are in it, which is the point of merge_commands().
    # **Leaves only.** Ancestry is context, not a setting: undoing
    # `interface GigabitEthernet0/1` is meaningless, and treating it as a value
    # reduced it to the key `interface`, matched the first `interface` line in
    # the pre-change config, and sent `interface Loopback0` to a device. The
    # classification comes from program_structure(), the same one
    # merge_commands() asserts against, so the two cannot disagree again.
    commands, open_chain = [], []
    pending = []
    applied, _rejected = landed_leaves(pushed, landed)
    for entry in applied:
        line = entry["line"]
        chain = list(entry["chain"])
        indent = len(line) - len(line.lstrip())
        canonical = ifnames.canonicalise_line(line)
        previous = _previous(chain, canonical)
        if previous is not None and previous != canonical:
            pending.append((chain, previous))
        elif previous is None:
            pending.append((chain, f"{' ' * indent}no {line.strip()}"))
        # previous == canonical: the pushed line was already there, nothing to do

    def _close():
        for _level in reversed(open_chain):
            commands.append("exit")
        open_chain.clear()

    for line_chain, command in pending:
        if line_chain != open_chain:
            _close()
            commands.extend(line_chain)
            open_chain = list(line_chain)
        commands.append(command)
    _close()

    assert_sendable(commands)
    return commands


def program_structure(commands: list) -> list:
    """``[{line, chain, leaf}]`` for a command program.

    **The single classification of ancestry vs. leaf**, derived from the
    program's own indentation and consumed by every path that needs it.

    It exists because the forward and rollback paths each had their own notion
    and they disagreed. ``merge_commands()`` knew perfectly well that
    ``interface GigabitEthernet0/1`` was context — it emitted that line
    *because* a diff line sat under it — while ``rollback_commands()``
    re-derived the question from key shapes, reduced the header to the key
    ``interface``, matched it against ``interface Loopback0`` in the
    pre-change config, and "restored" it onto a device. A line is ancestry if
    something deeper follows it before its level closes; nothing about that
    needs a second opinion.
    """
    entries, stack = [], []
    for raw in commands:
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.strip() in CONTROL_WORDS:
            if stack:
                stack.pop()
            continue
        indent = len(line) - len(line.lstrip())
        while stack and (len(entries[stack[-1]]["line"])
                         - len(entries[stack[-1]]["line"].lstrip())) >= indent:
            stack.pop()
        entries.append({"line": line,
                        "chain": tuple(entries[i]["line"] for i in stack),
                        "leaf": True})
        for index in stack:
            entries[index]["leaf"] = False
        stack.append(len(entries) - 1)
    return entries


def program_leaves(commands: list) -> list:
    """The configuration-bearing lines of a program, with their chains."""
    return [e for e in program_structure(commands) if e["leaf"]]


def program_lines(commands: list) -> frozenset:
    """``{(header chain, line)}`` for every configuration line in a program.

    A program is a sequence with context — the same text means different things
    under different headers — so a line is identified by its chain, not on its
    own. Control words carry no configuration and are dropped.
    """
    from modules.nsot import ifnames

    chain, pairs = [], set()
    for raw in commands:
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.strip() in CONTROL_WORDS:
            if chain:
                chain.pop()
            continue
        indent = len(line) - len(line.lstrip())
        while chain and (len(chain[-1]) - len(chain[-1].lstrip())) >= indent:
            chain.pop()
        canonical = ifnames.canonicalise_line(line)
        pairs.add((tuple(ifnames.canonicalise_line(c) for c in chain), canonical))
        chain.append(line)
    return frozenset(pairs)


def program_contains(new_commands: list, failed_commands: list) -> bool:
    """True if *new_commands* still sends everything *failed_commands* did.

    **Containment, not equality.** Equality lifts the block whenever the
    program merely *grows*: an unrelated edit that adds its own sent line — a
    description on another interface — makes the program different, so an
    equality test says "new proposal" and the failed ``shutdown`` goes out
    again bundled with it.

    Order-insensitive, because the same set of lines under the same headers is
    the same change however ``merge_commands`` happens to sequence it.
    """
    if not failed_commands:
        return False
    return program_lines(failed_commands) <= program_lines(new_commands)


class RollbackNotInverse(RuntimeError):
    """A rollback negation does not correspond to anything this deploy pushed."""


def assert_rollback_provenance(rollback: list, pushed: list) -> None:
    """Every rollback line must trace to the pushed program. No exceptions.

    Exactly three things may appear in a rollback:

    * an **inverse** — ``no X`` where ``X`` is a pushed leaf
    * a **restored prior value** — a line setting the same thing as a pushed
      leaf, in the same section
    * **ancestry** of one of those — a header that also headed a pushed line

    Anything else was synthesised, and synthesised configuration reaching a
    device is the failure this phase exists to prevent.

    The previous version examined only lines starting with ``no ``. A
    synthesised *non-negating* line passed free, which is how ``interface
    Loopback0`` reached a device: it is the inverse of nothing, so the check
    never looked at it. A guard that inspects one category and waves the rest
    through is the same family as a guard positioned where it cannot fail — it
    reads as a check, and the thing that went wrong was never in its scope.
    """
    from modules.nsot import ifnames

    pushed_leaves, pushed_ancestry = {}, set()
    for entry in program_structure(pushed):
        chain = tuple(ifnames.canonicalise_line(c) for c in entry["chain"])
        canonical = ifnames.canonicalise_line(entry["line"])
        if entry["leaf"]:
            precise, broad = _command_keys(canonical)
            keys = {canonical.strip(), f"key:{precise}"}
            if broad in FREE_FORM_COMMANDS:
                keys.add(f"key:{broad}")
            pushed_leaves.setdefault(chain, set()).update(keys)
        else:
            pushed_ancestry.add((chain, canonical))

    orphans = []
    for entry in program_structure(rollback):
        chain = tuple(ifnames.canonicalise_line(c) for c in entry["chain"])
        canonical = ifnames.canonicalise_line(entry["line"])

        if not entry["leaf"]:
            if (chain, canonical) not in pushed_ancestry:
                orphans.append((entry["line"],
                                "is not a section this deploy entered"))
            continue

        known = pushed_leaves.get(chain, set())
        stripped = canonical.strip()
        precise, broad = _command_keys(canonical)
        broad_ok = broad in FREE_FORM_COMMANDS and f"key:{broad}" in known

        if stripped.startswith("no "):
            if stripped[3:].strip() in known:
                continue
            if f"key:{precise}" in known or broad_ok:
                continue
            orphans.append((entry["line"], "negates nothing this deploy pushed"))
            continue

        if f"key:{precise}" in known or broad_ok:
            continue
        orphans.append((entry["line"],
                        "restores a setting this deploy did not touch"))

    if orphans:
        raise RollbackNotInverse(
            "refusing to send %d rollback line(s) that do not trace to this "
            "deploy: %s" % (len(orphans),
                            "; ".join(f"{line!r} {why}"
                                      for line, why in orphans[:5])))


class NotAuthorised(RuntimeError):
    """A dangerous command was not authorised, or an authorisation matched nothing."""


def dangerous_in(commands: list) -> list:
    """Commands the CI gate treats as dangerous, as exact allow-list strings."""
    from modules.pipeline import dangerous_commands
    return dangerous_commands(commands)


def assert_authorised(commands: list, authorised) -> None:
    """Every dangerous line must be authorised, and every authorisation used.

    Both halves matter. The first is the gate. The second stops an
    authorisation list becoming a standing blanket: a string that matches
    nothing in the program is either a typo — so the line it was meant to cover
    is *not* authorised — or a leftover from an earlier plan, and neither
    should pass quietly.
    """
    allowed = {a.strip() for a in (authorised or [])}
    flagged = set(dangerous_in(commands))

    unauthorised = sorted(flagged - allowed)
    if unauthorised:
        raise NotAuthorised(
            "%d dangerous command(s) are not authorised: %s. Authorise the "
            "exact string(s) at plan time." % (len(unauthorised),
                                               ", ".join(repr(u) for u in unauthorised)))

    unused = sorted(allowed - flagged)
    if unused:
        raise NotAuthorised(
            "%d authorisation(s) match no dangerous command in this program: "
            "%s. An authorisation that matches nothing is a typo or a leftover."
            % (len(unused), ", ".join(repr(u) for u in unused)))


def command_fingerprint(commands: list, authorised=None) -> str:
    """Stable hash of what was confirmed: the exact program **and** what was
    authorised within it.

    The authorisation is part of the confirmation, not an argument added later.
    "These lines, with these authorised" is one decision, and changing either
    half after it was displayed makes the confirmation no longer describe what
    would happen.
    """
    import hashlib
    import json as _json

    payload = _json.dumps(
        {"commands": list(commands),
         "authorised": sorted(a.strip() for a in (authorised or []))},
        sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class CommandsChanged(RuntimeError):
    """The recomputed command list differs from the one that was confirmed."""


class UnsendableCommand(RuntimeError):
    """A command contains a character an IOS CLI cannot accept."""


def assert_sendable(commands: list) -> None:
    """Refuse a command list the device's line parser cannot read.

    The second boundary, and the one that matters: every check built before
    this validated a command list's *provenance* and *identity* — where it came
    from, that it matched what was confirmed, that nothing was synthesised.
    None of them asked whether the bytes could be sent.

    An em dash reached a device as ``description NSoT-managed b``: three UTF-8
    bytes, the first consumed, the rest of the line lost. The push then failed
    on an echo mismatch, so the error named a timeout rather than the
    character. Refusing before connecting turns that into a message that says
    what is wrong.
    """
    from modules.nsot import normalize

    for index, command in enumerate(commands, 1):
        found = normalize.find_non_printable(command)
        if found:
            raise UnsendableCommand(
                f"command {index} of {len(commands)} cannot be sent — "
                f"{normalize.describe_non_printable(found)}. The IOS CLI "
                f"accepts printable ASCII only. Command: {command!r}")


class NegationSynthesised(RuntimeError):
    """Raised if a command to push did not come from the intended config."""


def assert_merge_only(to_push: list, intended_config: str) -> None:
    """Every pushed command must appear verbatim in the intended config.

    Merge-only does not mean "no ``no`` commands": an operator's template may
    legitimately contain ``no ip http server``, which is real configuration.
    It means this tool never *synthesises* one to remove something the template
    does not mention.

    Checking provenance rather than grepping for ``no`` is what makes that
    distinction enforceable — a synthesised negation is by definition absent
    from the intended config, whatever it looks like.
    """
    from modules.nsot import ifnames, normalize

    allowed = {ifnames.canonicalise_line(l.rstrip())
               for l in normalize.strip_for_roundtrip(intended_config)}
    invented = [c for c in to_push
                if c.strip() not in CONTROL_WORDS
                and ifnames.canonicalise_line(c.rstrip()) not in allowed]
    if invented:
        raise NegationSynthesised(
            "refusing to push %d command(s) that are not in the intended "
            "config: %s" % (len(invented), ", ".join(repr(c) for c in invented[:5])))


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def transport_for(platform_slug: str) -> str:
    """Resolve the deploy transport for a platform. Never guesses.

    The previous behaviour gated NETCONF on one **global** setting and fell back
    to SSH only *after* a failed attempt. On a nine-device batch containing
    vIOS-L2 — which has no NETCONF at all — that is nine socket timeouts before
    anything happens, and a deploy that looks hung.

    The platform map decides, per device. The global setting survives only as a
    master off-switch: it can disable NETCONF everywhere, never enable it on a
    platform that does not support it.
    """
    from modules.settings_schema import get_setting

    entry = (get_setting("platform_map", {}) or {}).get(platform_slug, {})
    if not entry.get("supports_netconf", False):
        return "ssh"
    if entry.get("deploy_transport", "ssh") != "netconf":
        return "ssh"
    try:
        from modules.config import get_user_setting
        if not get_user_setting("netconf_enabled", False):
            return "ssh"
    except Exception:                          # noqa: BLE001
        return "ssh"
    return "netconf"


# ---------------------------------------------------------------------------
# Batch control
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Stop attempting after N verify failures.

    Distinct from drift. One drifted device means someone touched a box, and
    the batch carries on without it. Repeated *verify* failures mean something
    systemic — a bad template, a broken assumption — and continuing turns one
    mistake into nine.
    """

    def __init__(self, limit: int = None):
        if limit is None:
            from modules.settings_schema import get_setting
            limit = get_setting("deploy_verify_failure_limit", 2)
        self.limit = max(1, int(limit))
        self.verify_failures = 0
        self.tripped_after = None

    def record_verify_failure(self, device: str) -> bool:
        self.verify_failures += 1
        if self.verify_failures >= self.limit and self.tripped_after is None:
            self.tripped_after = device
            log.error("deploy: circuit breaker tripped after %d verify failure(s) "
                      "(last: %s) — remaining devices will not be attempted",
                      self.verify_failures, device)
        return self.is_tripped

    @property
    def is_tripped(self) -> bool:
        return self.tripped_after is not None

    def reason(self) -> str:
        return (f"not attempted — stopped after {self.verify_failures} verify "
                f"failure(s), last on {self.tripped_after}")


def max_workers() -> int:
    """Deploy concurrency. Sequential by default.

    vIOS-L2 has limited vty lines, and Oxidized, the drift checker, the ping
    worker and a nine-device batch can all want the same device at once.
    """
    from modules.settings_schema import get_setting
    try:
        return max(1, min(16, int(get_setting("deploy_max_workers", 1))))
    except (TypeError, ValueError):
        return 1


# ---------------------------------------------------------------------------
# Batch orchestration
# ---------------------------------------------------------------------------

#: Per-device outcomes. Every device in a batch ends as exactly one of these —
#: a device can never simply fail to appear in the report.
DEPLOYED = "deployed"
SKIPPED_DRIFTED = "skipped_drifted"
SKIPPED_NOT_SELECTED = "skipped_not_selected"
REFUSED = "refused"
FAILED = "failed"
UNATTEMPTED = "unattempted"


def plan_batch(artifacts: list, confirmed: dict, fresh_captures: dict) -> dict:
    """Decide what each device gets before anything connects.

    *confirmed* maps device → the capture hash the operator confirmed against.
    *fresh_captures* maps device → the config read at deploy time.

    A device whose fresh capture no longer matches what was confirmed is
    **skipped, not aborted**: aborting is not atomic either. Stopping at device
    four leaves three deployed and six untouched, which is exactly as mixed a
    state as skipping one — abort prevents further change, it restores nothing.
    """
    import hashlib

    plan = {"to_deploy": [], "skipped": []}
    for artifact in artifacts:
        device = artifact.device

        if device not in confirmed:
            plan["skipped"].append({"device": device, "outcome": SKIPPED_NOT_SELECTED,
                                    "reason": "not selected for this deploy"})
            continue

        if not artifact.deployable:
            plan["skipped"].append({
                "device": device, "outcome": REFUSED,
                "reason": "; ".join(artifact.blocking_reasons)})
            continue

        fresh = fresh_captures.get(device)
        if fresh is None:
            plan["skipped"].append({"device": device, "outcome": FAILED,
                                    "reason": "no fresh capture at deploy time"})
            continue

        fresh_hash = hashlib.sha256(fresh.encode("utf-8")).hexdigest()[:16]
        if fresh_hash != confirmed[device]:
            plan["skipped"].append({
                "device": device, "outcome": SKIPPED_DRIFTED,
                "reason": ("the device configuration changed since you confirmed "
                           "the diff — re-preview to see what it looks like now"),
                "fresh_capture": fresh})
            continue

        plan["to_deploy"].append({"artifact": artifact, "fresh": fresh})

    return plan


def run_batch(plan: dict, deploy_one, breaker: CircuitBreaker = None) -> dict:
    """Deploy each planned device, honouring the circuit breaker.

    *deploy_one(entry)* performs one device and returns
    ``{"outcome", "verified", ...}``. It is injected so this function has no
    device dependency and can be tested without a network.

    Concurrency is capped — sequential by default — because vIOS-L2 has limited
    vty lines and Oxidized, the drift checker, the ping worker and a nine-device
    batch can all want the same device at once.
    """
    breaker = breaker or CircuitBreaker()
    results = list(plan.get("skipped", []))
    queue = list(plan.get("to_deploy", []))
    workers = max_workers()

    def _record(entry, outcome):
        results.append(outcome)
        if outcome.get("outcome") == FAILED and outcome.get("stage") == "verify":
            breaker.record_verify_failure(outcome["device"])

    if workers <= 1:
        for entry in queue:
            device = entry["artifact"].device
            if breaker.is_tripped:
                results.append({"device": device, "outcome": UNATTEMPTED,
                                "reason": breaker.reason()})
                continue
            _record(entry, deploy_one(entry))
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for entry in queue:
                if breaker.is_tripped:
                    results.append({"device": entry["artifact"].device,
                                    "outcome": UNATTEMPTED,
                                    "reason": breaker.reason()})
                    continue
                futures[pool.submit(deploy_one, entry)] = entry
            for future in as_completed(futures):
                _record(futures[future], future.result())

    accounted = {r["device"] for r in results}
    expected = ({e["artifact"].device for e in plan.get("to_deploy", [])}
                | {s["device"] for s in plan.get("skipped", [])})
    missing = expected - accounted
    if missing:
        # Should be unreachable. If it ever happens, say so loudly rather than
        # let a device vanish from the report.
        log.error("deploy: %d device(s) missing from the batch report: %s",
                  len(missing), sorted(missing))
        results.extend({"device": d, "outcome": UNATTEMPTED,
                        "reason": "not accounted for — this is a bug"}
                       for d in sorted(missing))

    by_outcome = {}
    for result in results:
        by_outcome.setdefault(result["outcome"], []).append(result["device"])

    return {
        "results": sorted(results, key=lambda r: r["device"]),
        "by_outcome": by_outcome,
        "deployed": by_outcome.get(DEPLOYED, []),
        "breaker_tripped": breaker.is_tripped,
        "breaker_reason": breaker.reason() if breaker.is_tripped else "",
        "total": len(results),
        "workers": workers,
    }
