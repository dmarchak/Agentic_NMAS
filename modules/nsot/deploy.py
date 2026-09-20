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

    # Before anything connects. A command list that cannot be sent is a defect
    # in the intent, not a transport problem, and it should never become
    # something an operator confirms.
    assert_sendable(commands)

    if remaining:
        log.warning("deploy: %d diff line(s) had no place in the intended "
                    "config and were not sent: %s", len(remaining),
                    ", ".join(repr(l) for l in list(remaining)[:5]))
    return commands


def command_fingerprint(commands: list) -> str:
    """Stable hash of an exact command list, for the confirm-then-send check."""
    import hashlib

    payload = "\n".join(commands)
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
