"""The job SDK: the context a job's `run(ctx, inputs)` is given, and the only path to anything
(the SDN design (rev. 4), section 11's table). Phase P1 publishes it as SIGNATURES: each handle
below names what it will reach, and every call on a real handle raises `NotBuilt`, naming the
phase that builds it. A unit test runs a job in `modules/jobs/testing.FakeContext` instead, whose
handles answer from fixtures.

The one handle built now is **`ctx.changes`, the change plan**: plan mode (the dry run) is the
contract a job is tested against, so its calls RECORD the intended writes and do nothing else
(no I/O). P4 sends a recorded plan through the guarded write path (B, the approvals, the
feature engine, `flow_ops`, H's policy push, the post-checks); `commit` raises `NotBuilt` until
then. The plan refuses, naming the job, its permission and its limit:
- any change from a read job (`permission` "read");
- a change past the job's `max_changes`;
- a value that is not plain data (JSON's types), which no hash could bind.

| Handle | Reaches | Built in |
|---|---|---|
| `ctx.netbox` | reads through Mercury's NetBox chokepoint, filtered to the scope | P4 (the broker) |
| `ctx.nsot` | the network's committed NSOT export (design section 5, C) | P2 (the export), served in P4 |
| `ctx.devices` | allowlisted reads only, as Show commands are | P4 |
| `ctx.controller` | the network's controller driver's reads (`modules/sdn/drivers/`) | P4 |
| `ctx.paths` | `trace` (`modules/sdn/trace.py`) and H's path verification | P4; verification P6 |
| `ctx.changes` | the change plan: `flow`, `feature`, `app_policy` | recording now; commit P4 |
| `ctx.ai` | the AI gateway (J), the job's id as its background trigger | P8 |
| `ctx.output` | `table`, `log`, `file` | P4 (the runner) |
| `ctx.job_files` | the job's own files, read-only (section 11's runner) | P4 |

What a job never gets: raw SSH, sockets, tokens, or a filesystem beyond its scratch folder.
"""

import copy
import hashlib
import json

from modules.jobs.base import APP_NAME, ContractError, DeviceRef, JobMeta, quoted

TESTING_HINT = "in a unit test, run the job in modules.jobs.testing.FakeContext"
#: A device feature's name (A: `openflow`).
FEATURE_NAME = APP_NAME
MODES = ("plan", "commit")


class NotBuilt(NotImplementedError):
    """A handle's call that a later phase builds, naming the call and the phase."""

    def __init__(self, call: str, phase: str, what: str):
        self.call, self.phase = call, phase
        super().__init__(f"ctx.{call} is not built yet: {phase} builds it ({what}); "
                         f"{TESTING_HINT}")


class ChangeRefused(ContractError):
    """A change the plan will not record, naming the job, the change and the rule."""


# ── the handles, as signatures ───────────────────────────────────────────────────────────────

class NetBoxHandle:
    """Reads through Mercury's NetBox chokepoint (`modules/netbox_client.py`), filtered to the
    job's scope: an object type or role outside it raises `ScopeError`, naming the call and the
    scope (`Scope.check`)."""

    PHASE, WHAT = "P4", "the broker, through Mercury's NetBox chokepoint, filtered to the scope"

    def get(self, object_type: str, **filters) -> list:
        """The objects of *object_type* (`dcim.interface`) matching *filters*, as NetBox's API
        answers them (each a mapping)."""
        raise NotBuilt("netbox.get", self.PHASE, self.WHAT)

    def one(self, object_type: str, object_id: int) -> dict:
        """One object of *object_type* by its NetBox ID."""
        raise NotBuilt("netbox.one", self.PHASE, self.WHAT)


class NsotHandle:
    """The network's committed NSOT export (design section 5, C)."""

    def export(self) -> dict:
        """The committed export, whole, as a mapping."""
        raise NotBuilt("nsot.export", "P2 (the export) and P4 (serving it to a job)",
                       "the network's committed NSOT export")


class DevicesHandle:
    """Allowlisted reads only, as Show commands are (`modules/readonly_commands.py`); a device
    write is a `ctx.changes` call, never this handle's."""

    def show(self, device: DeviceRef, command: str) -> dict:
        """`{"ok", "error", "text"}`: *command*'s masked answer from *device*. A command off the
        allowlist is refused, naming the allowlist's refusal."""
        raise NotBuilt("devices.show", "P4", "allowlisted reads through the reads engine")


class ControllerHandle:
    """The network's controller driver's reads. Each answers exactly what the driver answers
    (`modules/sdn/drivers/base.py`, `ControllerDriver`): `{"ok": bool, "error": str, ...}`,
    never raising. A controller write is a `ctx.changes.flow` call, never this handle's."""

    PHASE, WHAT = "P4", "the broker, over the network's controller driver"

    def switches(self) -> dict:
        """`{"switches": [{"dpid", "dpid_hex"}]}`: the switches connected."""
        raise NotBuilt("controller.switches", self.PHASE, self.WHAT)

    def switch_desc(self, dpid) -> dict:
        """`{"dpid", "desc"}`: what a switch says it is."""
        raise NotBuilt("controller.switch_desc", self.PHASE, self.WHAT)

    def links(self) -> dict:
        """`{"links": [{"src": port, "dst": port}]}`, each direction as the controller says."""
        raise NotBuilt("controller.links", self.PHASE, self.WHAT)

    def hosts(self) -> dict:
        """`{"hosts": [...], "hosts_note"}`: the hosts the controller learned."""
        raise NotBuilt("controller.hosts", self.PHASE, self.WHAT)

    def topology(self) -> dict:
        """`{"switches", "links", "hosts"}` in one read."""
        raise NotBuilt("controller.topology", self.PHASE, self.WHAT)

    def flows(self, dpid) -> dict:
        """`{"flows": [...]}`: a switch's flow table."""
        raise NotBuilt("controller.flows", self.PHASE, self.WHAT)

    def port_stats(self, dpid) -> dict:
        """`{"ports": [...]}`: a switch's port counters."""
        raise NotBuilt("controller.port_stats", self.PHASE, self.WHAT)

    def meters(self, dpid) -> dict:
        """`{"meters": [...]}`: a switch's meters."""
        raise NotBuilt("controller.meters", self.PHASE, self.WHAT)


class PathsHandle:
    """The forwarding path from the flow tables, and H's path verification."""

    def trace(self, src, dst, protocol: str = "icmp", **ports) -> dict:
        """The path a packet from *src* to *dst* takes through the flow tables
        (`modules/sdn/trace.py`: `delivered`, `not_delivered` or `cannot_tell`, with each hop's
        switch and ports)."""
        raise NotBuilt("paths.trace", "P4", "trace over the stored flow tables")

    def verify(self) -> dict:
        """The protected classes' `must_reach` invariants checked on the current tables."""
        raise NotBuilt("paths.verify", "P6", "H's path verification")


class AiHandle:
    """The AI gateway (J), with the job's id as its trigger: a background call only where the
    network has the feature on."""

    def ask(self, prompt: str, **options) -> dict:
        raise NotBuilt("ai.ask", "P8", "the AI gateway, J")


class OutputHandle:
    """What a run shows and keeps: tables, log lines and files (kept 90 days, their hashes for
    the network's life)."""

    PHASE, WHAT = "P4", "the runner's output"

    def table(self, title: str, columns, rows) -> None:
        raise NotBuilt("output.table", self.PHASE, self.WHAT)

    def log(self, message: str) -> None:
        raise NotBuilt("output.log", self.PHASE, self.WHAT)

    def file(self, name: str, content) -> None:
        raise NotBuilt("output.file", self.PHASE, self.WHAT)


class JobFilesHandle:
    """The job's own folder, read-only, held in memory by the runner (no job file on disk)."""

    PHASE, WHAT = "P4", "the runner, holding the job's folder in memory"

    def names(self) -> list:
        raise NotBuilt("job_files.names", self.PHASE, self.WHAT)

    def read(self, name: str) -> bytes:
        raise NotBuilt("job_files.read", self.PHASE, self.WHAT)


# ── the change plan (recording; no I/O) ──────────────────────────────────────────────────────

def _plain(value, where: str):
    """A deep copy of *value* if it is plain data (JSON's types, string keys); otherwise a
    ValueError naming where the first other value sits."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{where} is {value!r}, which JSON cannot carry")
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(v, f"{where}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(f"{where} has the key {quoted(k)}, not a string")
            out[k] = _plain(v, f"{where}.{k}")
        return out
    raise ValueError(f"{where} is a {type(value).__name__} ({quoted(value)}), not plain data")


class ChangePlan:
    """The change plan a job's writes build (section 11, "Plan and commit"). Each call records
    one change and returns a copy of it; nothing is sent. `changes` lists them in order,
    `sha256()` is the plan's hash (what an approval binds to, with the state it was computed
    against: P4)."""

    def __init__(self, meta: JobMeta):
        if not isinstance(meta, JobMeta):
            raise ContractError("a change plan", [f"meta is a JobMeta, not "
                                                  f"{type(meta).__name__}"])
        self.meta = meta
        self._changes = []

    @property
    def changes(self) -> list:
        return copy.deepcopy(self._changes)

    def __len__(self) -> int:
        return len(self._changes)

    def _refuse(self, call: str, problem: str):
        raise ChangeRefused(f"ctx.changes.{call} from {self.meta.name} {self.meta.version}",
                            [problem])

    def _record(self, call: str, change: dict) -> dict:
        if self.meta.permission != "write":
            self._refuse(call, f"the job's permission is {self.meta.permission!r}, so it makes "
                               "no change (a write job declares permission 'write')")
        if len(self._changes) + 1 > self.meta.max_changes:
            self._refuse(call, f"change {len(self._changes) + 1} is past the job's max_changes "
                               f"of {self.meta.max_changes}")
        try:
            change = _plain(change, call)
        except ValueError as exc:
            self._refuse(call, str(exc))
        self._changes.append(change)
        return copy.deepcopy(change)

    def flow(self, dpid, do: str = "add_flow", *, flow: dict = None, meter: dict = None,
             connection: str = "") -> dict:
        """One flow or meter change on a switch, in `flow_ops`' terms (`do` one of
        `modules/sdn/flow_ops.DO`; *flow* for a flow's change, *meter* for a meter's), sent at
        commit through `flow_ops`' one write path, which checks the flow whole."""
        from modules.sdn.drivers.base import SpecError, parse_dpid
        from modules.sdn.flow_ops import DO

        try:
            number = parse_dpid(dpid)
        except SpecError as exc:
            self._refuse("flow", str(exc))
        if do not in DO:
            self._refuse("flow", f"do {quoted(do)} is not one of {', '.join(DO)}")
        needs = "meter" if do.endswith("_meter") else "flow"
        given = meter if needs == "meter" else flow
        other = flow if needs == "meter" else meter
        if not isinstance(given, dict) or not given:
            self._refuse("flow", f"{do} names its {needs} as a non-empty mapping, not "
                                 f"{quoted(given)}")
        if other is not None:
            wrong = "flow" if needs == "meter" else "meter"
            self._refuse("flow", f"{do} takes a {needs}, not a {wrong}")
        if not isinstance(connection, str):
            self._refuse("flow", f"connection is a name, not {quoted(connection)}")
        return self._record("flow", {"kind": "flow", "connection": connection, "dpid": number,
                                     "change": {"do": do, needs: given}})

    def feature(self, device: DeviceRef, feature: str, values: dict) -> dict:
        """A device feature's intended values (A: `openflow`), rendered and pushed at commit
        through the feature engine (P4)."""
        if not isinstance(device, DeviceRef):
            self._refuse("feature", f"device is a DeviceRef, not {quoted(device)}")
        if not isinstance(feature, str) or not FEATURE_NAME.fullmatch(feature):
            self._refuse("feature", f"feature {quoted(feature)} does not match "
                                    f"{FEATURE_NAME.pattern}")
        if not isinstance(values, dict):
            self._refuse("feature", f"values is a mapping, not {quoted(values)}")
        return self._record("feature", {"kind": "feature",
                                        "device": {"id": device.id, "name": device.name},
                                        "feature": feature, "values": values})

    def app_policy(self, app: str, endpoint: str, body: dict) -> dict:
        """A controller app's policy (I-2's policy as data), validated by the app's manifest's
        schema and pushed at commit through H's policy push (P6, P4)."""
        if not isinstance(app, str) or not APP_NAME.fullmatch(app):
            self._refuse("app_policy", f"app {quoted(app)} does not match {APP_NAME.pattern}")
        if not isinstance(endpoint, str) or not endpoint.startswith("/"):
            self._refuse("app_policy", f"endpoint {quoted(endpoint)} is a path starting '/'")
        if not isinstance(body, dict):
            self._refuse("app_policy", f"body is a mapping, not {quoted(body)}")
        return self._record("app_policy", {"kind": "app_policy", "app": app,
                                           "endpoint": endpoint, "body": body})

    def as_dict(self) -> dict:
        return {"job": self.meta.name, "version": self.meta.version,
                "changes": self.changes}

    def sha256(self) -> str:
        """The plan's hash: SHA-256 over its canonical JSON (keys sorted, no spaces)."""
        text = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def commit(self):
        raise NotBuilt("changes.commit", "P4", "the guarded write path: B, the approvals, "
                                               "the feature engine, flow_ops, H's policy push")


# ── the context ──────────────────────────────────────────────────────────────────────────────

class Context:
    """What `run(ctx, inputs)` is given. Each handle defaults to its signature, whose calls
    raise `NotBuilt`; `changes` is a `ChangePlan` for the job's `meta`. Only plan mode exists
    in P1: a commit-mode context raises `NotBuilt` (P4)."""

    def __init__(self, meta: JobMeta, *, mode: str = "plan", netbox=None, nsot=None,
                 devices=None, controller=None, paths=None, ai=None, output=None,
                 job_files=None):
        if mode not in MODES:
            raise ContractError("a context", [f"mode {quoted(mode)} is not one of "
                                              f"{', '.join(MODES)}"])
        if mode == "commit":
            raise NotBuilt("commit", "P4", "the runner's commit mode")
        self.meta = meta
        self.mode = mode
        self.changes = ChangePlan(meta)
        self.netbox = netbox if netbox is not None else NetBoxHandle()
        self.nsot = nsot if nsot is not None else NsotHandle()
        self.devices = devices if devices is not None else DevicesHandle()
        self.controller = controller if controller is not None else ControllerHandle()
        self.paths = paths if paths is not None else PathsHandle()
        self.ai = ai if ai is not None else AiHandle()
        self.output = output if output is not None else OutputHandle()
        self.job_files = job_files if job_files is not None else JobFilesHandle()
