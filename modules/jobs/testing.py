"""The context a unit test runs a job in (phase P1): `FakeContext`, a `Context` whose handles
answer from fixtures the test hands it, with no Mercury running and nothing sent anywhere.

- **`controller`**: any controller driver; its READS only are offered to the job, as the real
  handle offers them (`ControllerReads`), so a job cannot reach a driver's write calls. A test
  gives it the recorded Ryu: `tests/fixtures/sdn/ryu_recorded.RecordedRyu().driver()`, Mercury's
  real Ryu driver reading Ryu's recorded answers.
- **`netbox`**: `FakeNetBox({object_type: [object, ...]})`; a read of an object type outside the
  job's scope raises `ScopeError`, naming the call and the scope, as P4's broker will.
- **`nsot`**: `FakeNsot(export)`, the export as a mapping.
- **`devices`**: `FakeDevices({(device_id, command): text})`; a command off Show commands'
  allowlist is refused with the allowlist's own words, and a read not given raises, naming it.
- **`output`**: always a `RecordedOutput`, keeping the tables, log lines and files.

Any handle not given stays its signature, whose calls raise `NotBuilt`. `plan_run` builds the
context, validates the inputs through the job's `Inputs` and runs the job in plan mode.

**The fixtures a job's test asks for by name** (rev. 6, section 11a, item 2): a test parameter
named `ctx`, `ryu` or `netbox` is given what `FIXTURES` maps it to, by `fixture(name, job)`,
the one resolver Mercury's runner (`modules/jobs/runner.py`) and the folder's fixed
`conftest.py` (under pytest) both call; a test may call the same helpers itself.
- `ctx(job)`: a `FakeContext` for the job's `meta`, its controller the recorded Ryu's driver;
- `ryu(job=None)`: the recorded Ryu (`tests/fixtures/sdn/ryu_recorded.RecordedRyu`);
- `netbox(job=None, objects=None)`: a `FakeNetBox` over *objects*, read within the job's scope.
  The masked NetBox export it will default to (`tests/fixtures/lab9_netbox/`, P1b) is not in
  the repository yet, so without *objects* it raises, naming that path: an empty NetBox would
  pass a test that reads nothing.
"""

import copy
import os

from modules.jobs.base import ContractError, DeviceRef, Job, JobInputs, JobMeta, quoted
from modules.jobs.sdk import ControllerHandle, Context

__all__ = ["ControllerReads", "FakeContext", "FakeDevices", "FakeNetBox", "FakeNsot",
           "FIXTURES", "RecordedOutput", "ctx", "fixture", "fixture_for", "job_class_in",
           "netbox", "plan_run", "ryu"]

#: The masked NetBox export `netbox()` will read (P1b), relative to the repository.
NETBOX_EXPORT = os.path.join("tests", "fixtures", "lab9_netbox")

#: The reads the controller handle offers: the signature's own public methods.
CONTROLLER_READS = tuple(sorted(name for name in vars(ControllerHandle)
                                if not name.startswith("_") and name.islower()))


class ControllerReads:
    """A controller driver's reads, and nothing else of it."""

    def __init__(self, driver):
        self._driver = driver

    def __getattr__(self, name):
        if name in CONTROLLER_READS:
            return getattr(self._driver, name)
        raise AttributeError(f"ctx.controller offers reads only ({', '.join(CONTROLLER_READS)}), "
                             f"not {name!r}: a controller write is ctx.changes.flow")


class FakeNetBox:
    """NetBox's objects by type, read within the job's scope."""

    def __init__(self, objects: dict, meta: JobMeta = None):
        self._objects = copy.deepcopy(objects or {})
        self._meta = meta

    def _check(self, call: str, object_type: str):
        if self._meta is not None:
            self._meta.scope.check(call, object_type)

    def get(self, object_type: str, **filters) -> list:
        self._check(f"netbox.get({object_type!r})", object_type)
        return [copy.deepcopy(o) for o in self._objects.get(object_type, [])
                if all(o.get(k) == v for k, v in filters.items())]

    def one(self, object_type: str, object_id: int) -> dict:
        self._check(f"netbox.one({object_type!r}, {object_id!r})", object_type)
        for o in self._objects.get(object_type, []):
            if o.get("id") == object_id:
                return copy.deepcopy(o)
        raise LookupError(f"the fixture holds no {object_type} with id {object_id!r}")


class FakeNsot:
    def __init__(self, export: dict):
        self._export = copy.deepcopy(export)

    def export(self) -> dict:
        return copy.deepcopy(self._export)


class FakeDevices:
    """Allowlisted reads answered from `{(device_id, command): text}`."""

    def __init__(self, answers: dict):
        self._answers = dict(answers or {})

    def show(self, device: DeviceRef, command: str) -> dict:
        from modules.readonly_commands import refusal

        if not isinstance(device, DeviceRef):
            return {"ok": False, "error": f"device is a DeviceRef, not {quoted(device)}",
                    "text": ""}
        refused = refusal(command)
        if refused:
            return {"ok": False, "error": refused, "text": ""}
        key = (device.id, command)
        if key not in self._answers:
            raise LookupError(f"the fixture holds no answer to {command!r} from device "
                              f"{device.id} ({device.name})")
        return {"ok": True, "error": "", "text": self._answers[key]}


class RecordedOutput:
    """The run's output, kept for the test to read."""

    def __init__(self):
        self.tables, self.lines, self.files = [], [], {}

    def table(self, title: str, columns, rows) -> None:
        columns = list(columns)
        rows = [list(r) for r in rows]
        wrong = [i for i, r in enumerate(rows) if len(r) != len(columns)]
        if wrong:
            raise ContractError(f"output.table {title!r}",
                                [f"row {wrong[0]} has {len(rows[wrong[0]])} cells, not the "
                                 f"{len(columns)} columns"])
        self.tables.append({"title": title, "columns": columns, "rows": rows})

    def log(self, message: str) -> None:
        self.lines.append(str(message))

    def file(self, name: str, content) -> None:
        if not isinstance(content, (str, bytes)):
            raise ContractError(f"output.file {name!r}",
                                [f"content is text or bytes, not {type(content).__name__}"])
        self.files[name] = content


class FakeContext(Context):
    """A plan-mode `Context` over fixtures (see the module's docstring)."""

    def __init__(self, meta: JobMeta, *, controller=None, netbox=None, nsot=None,
                 devices=None, paths=None, job_files=None):
        super().__init__(
            meta, mode="plan",
            controller=ControllerReads(controller) if controller is not None else None,
            netbox=FakeNetBox(netbox, meta) if isinstance(netbox, dict) else netbox,
            nsot=FakeNsot(nsot) if isinstance(nsot, dict) else nsot,
            devices=FakeDevices(devices) if isinstance(devices, dict) else devices,
            paths=paths, output=RecordedOutput(), job_files=job_files)


def plan_run(job_class, inputs, **fixtures) -> FakeContext:
    """Run *job_class* in plan mode over *fixtures* (`FakeContext`'s keywords) and answer the
    context: `ctx.changes` the plan, `ctx.output` what it showed. *inputs* is a mapping (it is
    validated through the job's `Inputs`) or an `Inputs` already built."""
    if not (isinstance(job_class, type) and issubclass(job_class, Job)):
        raise ContractError("plan_run", [f"job_class is a Job subclass, not {quoted(job_class)}"])
    if isinstance(inputs, JobInputs):
        if not isinstance(inputs, job_class.Inputs):
            raise ContractError("plan_run", [f"inputs are {type(inputs).__name__}, not "
                                             f"{job_class.__name__}.Inputs"])
        given = inputs
    else:
        given = job_class.Inputs.parse(inputs, f"{job_class.__name__}.Inputs")
    ctx = FakeContext(job_class.meta, **fixtures)
    job_class().run(ctx, given)
    return ctx


# ── the fixtures a test asks for by name ─────────────────────────────────────────────────────

def _meta(job, helper: str) -> JobMeta:
    if isinstance(job, JobMeta):
        return job
    if isinstance(job, type) and issubclass(job, Job):
        return job.meta
    raise ContractError(f"the fixture {helper}", [f"job is the folder's Job class or its "
                                                  f"JobMeta, not {quoted(job)}"])


def job_class_in(modules) -> type:
    """The one `Job` subclass defined in *modules* (the job folder's own modules, as the
    runner or pytest imported them); refused, naming what was found, when there is not
    exactly one."""
    names = {getattr(m, "__name__", None) for m in modules}
    found = []
    for m in modules:
        for value in vars(m).values():
            if isinstance(value, type) and issubclass(value, Job) and value is not Job \
                    and value.__module__ in names and value not in found:
                found.append(value)
    if len(found) != 1:
        raise ContractError("the folder's job", [
            f"the fixtures need exactly one Job class in the folder's modules "
            f"({', '.join(sorted(n for n in names if n))}); found {len(found)}"
            + (f": {', '.join(c.__name__ for c in found)}" if found else "")])
    return found[0]


def ryu(job=None):
    """The recorded Ryu (`tests/fixtures/sdn/ryu_recorded.py`); *job* is not needed."""
    from tests.fixtures.sdn.ryu_recorded import RecordedRyu

    return RecordedRyu()


def ctx(job, **fixtures) -> FakeContext:
    """A plan-mode `FakeContext` for *job* (its class or its `JobMeta`), its controller the
    recorded Ryu's driver unless *fixtures* gives another (`FakeContext`'s keywords)."""
    meta = _meta(job, "ctx")
    fixtures.setdefault("controller", ryu().driver())
    return FakeContext(meta, **fixtures)


def netbox(job=None, objects=None) -> FakeNetBox:
    """A `FakeNetBox` over *objects* (`{object_type: [object, ...]}`), within *job*'s scope
    when *job* is given (see the module's docstring for the export it will default to)."""
    if objects is None:
        raise LookupError(f"the masked NetBox export ({NETBOX_EXPORT}/, P1b) is not in this "
                          "repository yet: give the objects, netbox(job, objects={...})")
    return FakeNetBox(objects, _meta(job, "netbox") if job is not None else None)


#: A test parameter's name -> the helper giving it, each called with the folder's job class.
FIXTURES = {"ctx": ctx, "ryu": ryu, "netbox": netbox}


def fixture(name: str, job):
    """What the test parameter *name* is given, for the folder's *job* class: the one resolver
    the runner and the folder's conftest.py both call. An unknown name is refused, naming the
    fixtures there are."""
    if name not in FIXTURES:
        raise LookupError(f"no fixture named {name!r}: a job's test may ask for "
                          f"{', '.join(sorted(FIXTURES))}")
    return FIXTURES[name](job)


def fixture_for(name: str, modules):
    """`fixture(name, job)` for the job class in *modules* (the folder's own modules, as the
    runner or pytest imported them). A fixture that needs no job (`ryu`) is given without
    one; one that needs it, where the folder has not exactly one, raises `job_class_in`'s
    refusal, naming what was found."""
    try:
        job, missing = job_class_in(modules), None
    except ContractError as exc:
        job, missing = None, exc
    try:
        return fixture(name, job)
    except ContractError:
        if missing is not None:
            raise missing from None
        raise
