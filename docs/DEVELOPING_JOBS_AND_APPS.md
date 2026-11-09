# Developing jobs and controller apps for Mercury

How a **job** (a saved, rerunnable script that reaches the network only through Mercury) and a
**controller app** (a Ryu app that Mercury packages, checks and deploys) are written for
Mercury. What is here is the published contract: the shapes are fixed now, so the pure logic
can be written and unit-tested before the framework that runs it lands.

The design behind it is the SDN platform design, revision 4: section 11 (jobs, I-1),
section 12 (controller apps, I-2) and section 14 (the lab as the acceptance test). Revision 6,
section 11a, adds the spec card, the job gate and `mercury job new|check`.

## Building a job or app: two ways

**Describe it.** Run `mercury job new`, say in plain words what it should do, and give two or
three examples of the right result. Confirm the spec card. Mercury, or your own AI assistant,
writes the code and tests, and repairs them until `mercury job check` passes.

**Write it yourself.** Run `mercury job new --blank` and write the logic and tests.
`mercury job check` tells you exactly what's missing.

Either way, the result is a Draft. In Mercury, a reviewer other than its author reads the spec
card, the code and the check's results, and publishes it; Mercury runs only what was published.

Until Mercury's own assistant drafts the card (part (b) of section 11a, with J), "describe it"
means your own assistant: give it the folder's `AUTHORING.md` (below), and it drafts the card
with you, asking rather than guessing, then writes the code and tests against
`mercury job check`. Everything below holds for apps too, with `mercury app new|check`.

## What you write

Pure logic, against the published contracts. You don't write SSH, REST plumbing, credentials,
or anything that touches a device directly.

- **A job** is a Python class extending `Job` (`modules/jobs/base.py`; import it as
  `from modules.jobs import Job`). It declares `meta`, its typed `Inputs` and
  `run(ctx, inputs)`. It reaches the world only through `ctx`: `ctx.nsot`, `ctx.netbox`,
  `ctx.controller`, `ctx.paths`, `ctx.changes`, `ctx.output`. A write is a call on
  `ctx.changes` that builds a plan; you never send anything yourself.
- **A controller app** is a Ryu app folder with a `manifest.yml`. The manifest gives its name,
  version, controllers, OpenFlow versions, config schema, and REST endpoints, including
  `/health`.
  - It reads every network-specific value from its config, never from constants.
  - On switch connect it reconciles: it adds or removes only the difference, and never wipes
    flows.
  - It runs in the controller, on the Python its network's controller runs apps on, as
    measured for that network, and is held to its own allowlist, not a job's ("An app's
    allowlist" and "The controller's Python", below).
- **Tests** sit at the folder's root, beside the code, or in its `tests/` subfolder, and
  nowhere else, for jobs and apps alike.

## Where things run

- **A controller app:** anything that must react per packet or in milliseconds (forwarding,
  DNS inspection, reroute). It must keep working with Mercury down.
- **A Mercury job:** anything in seconds or on request, through the controller's REST API.

## A job

```python
from modules.jobs import DeviceRef, HostRef, Job, JobInputs, JobMeta, Scope


class TracePath(Job):
    meta = JobMeta(name="trace-path", version="1.0.0",
                   summary="The path a packet takes between two endpoints.",
                   permission="read",                  # "read" or "write"
                   scope=Scope(object_types=["dcim.device", "dcim.interface"],
                               roles=["openflow-switch", "host"]),
                   max_changes=0, autonomous=False)

    class Inputs(JobInputs):
        src: HostRef                                   # picked from NetBox
        dst: HostRef | DeviceRef

    def run(self, ctx, inputs):
        switches = ctx.controller.switches()           # the driver's answer: {"ok", ...}
        ctx.output.table("switches", ["dpid"], [[s["dpid_hex"]] for s in switches["switches"]])
```

### The declaration (`JobMeta`)

Everything is checked when the class is defined. A refusal names the field, the value and the
rule.

| Field | Rule |
|---|---|
| `name` | lower case with hyphens, `^[a-z][a-z0-9-]{0,40}$` (`trace-path`) |
| `version` | three numbers, `^[0-9]+\.[0-9]+\.[0-9]+$` |
| `summary` | one sentence, at most 200 characters |
| `permission` | `"read"` or `"write"` |
| `scope` | the NetBox object types (`dcim.device`) and device roles (slugs) the job reaches |
| `max_changes` | 0 for a read job; at least 1 for a write job |
| `autonomous` | `True` or `False` (strictly a boolean) |

About the scope:
- **There is no wildcard: an empty list reaches nothing.**
- At run time, a call outside the scope raises, naming the call and the scope
  (`Scope.check`).
- Widening a scope is a new version, back to Draft, needing review.
- A job calling a job gets the intersection of their permissions and scopes, never the union
  (`composed_reach`).

### The inputs

`Inputs` subclasses `JobInputs`. Inputs are frozen, and an unknown input is refused by name.
A device or host is a `DeviceRef` or a `HostRef`: its NetBox ID (the identity) and its name (a
label), told apart by `kind`.

### The context (`modules/jobs/sdk.py`)

| Handle | Reaches | Built in |
|---|---|---|
| `ctx.netbox` | `get(object_type, **filters)`, `one(object_type, id)`: NetBox, filtered to the scope | P4 |
| `ctx.nsot` | `export()`: the network's committed NSOT export | P2, served in P4 |
| `ctx.devices` | `show(device, command)`: allowlisted reads only, as Show commands are | P4 |
| `ctx.controller` | `switches`, `switch_desc`, `links`, `hosts`, `topology`, `flows`, `port_stats`, `meters`: the controller driver's reads, each answering `{"ok", "error", ...}` | P4 |
| `ctx.paths` | `trace(src, dst)`; `verify()`, H's path verification | P4; P6 |
| `ctx.changes` | `flow`, `feature`, `app_policy`: the change plan | recording now |
| `ctx.ai` | the AI gateway | P8 |
| `ctx.output` | `table`, `log`, `file` | P4 |
| `ctx.job_files` | the job's own files, read-only | P4 |

On a real Mercury, a handle that is not built yet raises `NotBuilt`, naming the call and the
phase that builds it. In a unit test, every handle answers from fixtures (below).

### Writes build a plan

Each `ctx.changes` call records one intended change and returns a copy of it. Nothing is
sent. The calls:
- **`ctx.changes.flow(dpid, do, flow=..., meter=...)`:** a flow or meter change in
  `flow_ops`' terms. `do` is one of `add_flow`, `edit_flow`, `remove_flow`, `add_meter` and
  `remove_meter`. The dpid can be an integer, `0x` hex, sixteen hex digits, or eight
  colon-separated bytes.
- **`ctx.changes.feature(device, feature, values)`:** a device feature's intended values, such
  as `openflow`.
- **`ctx.changes.app_policy(app, endpoint, body)`:** a controller app's policy, pushed to its
  REST endpoint.

The plan refuses three things, each naming the job and the rule:
- any change from a read job;
- a change past `max_changes`;
- a value that is not plain data (JSON's types).

`ctx.changes.sha256()` is the plan's hash. An approval binds to it, together with the state it
was computed against. Committing a plan (B, the approvals, the guarded write path and the
post-checks) is P4's: until then a test asserts on `ctx.changes.changes`.

## Testing a job

Unit tests are pytest, with no network. Run the job in `modules/jobs/testing.py`'s
`FakeContext`, or let `plan_run` build one, validate the inputs and run the job in plan mode:

```python
from modules.jobs.testing import plan_run
from tests.fixtures.sdn.ryu_recorded import RecordedRyu


def test_trace_path_lists_every_switch():
    ryu = RecordedRyu()
    ctx = plan_run(TracePath, {"src": {"id": 7, "name": "host-a", "kind": "host"},
                               "dst": {"id": 9, "name": "edge1", "kind": "device"}},
                   controller=ryu.driver())
    assert len(ctx.output.tables[0]["rows"]) == len(ryu.dpids())
    assert ctx.changes.changes == []
```

What each fixture keyword gives:
- **`controller=`:** a controller driver. Only its reads are offered, so `ctx.controller` has
  no write. `RecordedRyu().driver()` (`tests/fixtures/sdn/ryu_recorded.py`) is Mercury's real
  Ryu driver reading Ryu's recorded answers, so a job sees exactly the shapes it will see on a
  real network.
  - The recording answers `/stats/switches`, `/v1.0/topology/links`, and `desc` and `portdesc`
    per switch.
  - A path it did not record raises `UnrecordedPath`, naming the path. Through the driver,
    that comes back as the driver's `{"ok": False, "error": ...}`.
- **`netbox={object_type: [objects]}`:** an object type outside the job's scope raises
  `ScopeError`, as the runner will.
- **`nsot={...}`:** the export, as a mapping.
- **`devices={(device_id, command): text}`:** a command off Show commands' allowlist is
  refused, in the allowlist's own words.
- **`ctx.output`:** always recorded: `tables`, `lines` and `files`.

A test can also ask for a fixture by naming a parameter: `ryu` (the recorded Ryu), `ctx` (a
plan-mode `FakeContext` for the folder's job, its controller the recorded Ryu's) or `netbox`.
Mercury's runner gives them, and so does the folder's `conftest.py` under pytest, through the
same resolver (`modules.jobs.testing.fixture_for`).

## The spec card, the folder and `mercury job check`

**`mercury job new <folder> --from spec.yml`** writes a new folder from a confirmed spec card,
and **`mercury job new <folder> --blank`** from an empty one (the folder's name is the job's).
It refuses a folder that exists and is not empty, naming it, and a card that still holds an
`ask:` question or a refused field, naming each. The folder holds:
- `spec.yml`, the spec card (`modules/jobs/spec.py`): the contract (name, summary, read or
  write, scope, typed inputs and outputs) and two or more acceptance examples in plain
  Given/When/Then, each naming its fixture data. A blank card's every open field is an `ask:`
  question;
- `job.py`, a stub declaring the card's contract, whose `run` raises until written;
- `test_job.py`, one test per example, each marked `@covers("<example>")` and failing until it
  is written;
- `conftest.py`, fixed, so the folder runs unchanged under pytest;
- `AUTHORING.md`, the guide to paste into an AI assistant: the contract, the SDK's handles,
  the fixtures, every check with the action it prints, two worked examples and one worked
  failure.

A job or app is never written into a network's configuration repository, which holds its
goldens and intent: Mercury registers it as a Draft from the network's own code repository,
pinned by commit (the SDN design revision 7, code apart from state).

**`mercury job check <folder>`** runs the job gate (`modules/jobs/gate.py`), the same function
Publish runs, so the two give the same verdict, check by check. It prints each check, passed or
FAILED, with what failed and the action that clears it; `--json` prints the verdict whole. It
exits 0 only when every check passes:
1. `spec`: the card is valid and holds no open question;
2. `static`: the code and tests import only their own modules, `modules.jobs`,
   `modules.jobs.testing` and the standard library's safe set, and use no file, socket,
   process, `eval` or `exec`;
3. `tests`: the tests pass under Mercury's own runner, with no network; a failed assertion shows
   both sides;
4. `examples`: every example is covered by a test, and every `@covers` names an example;
5. `asserts`: every test asserts something;
6. `mutation`: the job's own code is changed one place at a time, and every mutant runs;
7. `survivors`: every change the tests didn't notice is killed by a test, or marked equivalent
   by the reviewer, a person, with a reason (never by an AI). A survivor reads "your tests
   didn't notice when line 14's `>` became `>=`", with the line quoted.

**`mercury app new|check`** are the same for a controller app, with `manifest.yml` beside the
card, and with three differences in its verdict (`modules/apps/gate.py`):
- it adds `manifest` (the manifest is valid, names the card's app, lists its tests where tests
  sit, and lists each network destination it declares, for the reviewer) and `reconcile` (the
  reconcile test);
- its `static` check is the app allowlist's (below), not the job's;
- **it runs no app code.** An app's tests run in the container harness, never in the job
  sandbox, so its `tests`, `mutation`, `survivors` and `reconcile` checks say "not run" until
  the harness runs them, and an app's verdict cannot pass before then. Its `spec`, `manifest`,
  `static`, `examples` and `asserts` checks read the source.

## A controller app

`manifest.yml`, validated by `modules/apps/manifest.py` (`load_manifest(folder)`). Each
malformed field is refused by name. The contract fixture is the `dns_blacklist` app's,
`tests/fixtures/apps/dns-blacklist/manifest.yml`, with an example config beside it
(`tests/fixtures/apps/dns-blacklist/config.example.yml`).

| Field | Rule |
|---|---|
| `name` | `^[a-z][a-z0-9_]{0,40}$`: underscores, not hyphens (a Python module path on the controller) |
| `version` | `^[0-9]+\.[0-9]+\.[0-9]+$` |
| `summary` | optional, one sentence |
| `controllers` | each controller with its versions, such as `ryu: ">=4.34"` |
| `openflow_versions` | quoted, such as `["1.3"]` (YAML reads an unquoted 1.3 as a number) |
| `requires` | optional: other apps loaded first, by name |
| `config_schema` | a JSON Schema (draft 2020-12) whose top level is an object |
| `rest` | `prefix` and `endpoints`, each a `path` and its `methods`; `/health` answering GET is required; `/validate`, if offered, answers POST. Mercury's post-check reads `GET <prefix>/health` on the controller's REST port, and the app answers a 200 with a JSON object whose `ok` is `true` or `false`, listing in `problems` why when it is false; any other answer is read as unreadable, never as healthy |
| `owns_flows` | optional: `cookie_prefix` and `cookie_mask` (64-bit hex), and the protected `classes` it owns |
| `egress` | optional: every network destination the app reaches, each a unique `name`, the `from_config` key whose value is its address (dotted, such as `verdict_service.url`: a string key `config_schema` declares through `properties`) and its `purpose`; none means the app reaches no destination of its own |
| `compiled` | optional: what Mercury compiles into the app's start-time config, each a unique top-level `key` the `config_schema` declares and its `per_switch` table roles (`forward_table`, `punt_table`, `meter_table`), placed from each expected switch's platform profile and keyed by its DPID in decimal (`modules/apps/app_config.py`) |
| `tests` | optional: its unit tests, as paths relative to the app's folder: a `test_*.py` file at its root or in `tests/` |

The manifest file itself:
- a key given twice is refused;
- a manifest that is a link is refused;
- a manifest is at most 64 KiB.

`validate_config(manifest, config)` lists each way a config fails the schema, by its path.

**The `dns_blacklist` config** (section 14), as its schema declares it:
- **`verdict_service`:** `url`, `timeout_seconds` and `on_unavailable` (`allow` or `block`:
  what a query gets while the verdict service does not answer).
  - **`on_unavailable` defaults to `allow`** (the operator, 2026-11-06). DNS is a protected
    class with a `must_reach` invariant, so failing closed would break DNS for every host
    whenever the verdict service is down.
  - **While it is down, the app:**
    - honours a verdict still in its cache, for that verdict's TTL;
    - allows a domain it has no verdict for, and logs it;
    - reports the service as down on its `/health`.

    Mercury raises that as a Needs attention row naming the service, and the row clears when
    the service answers again.
  - **`block` stays selectable per network** in the app's config. Its explain-back says what
    it costs: every lookup without a cached verdict fails while the service is down.
  - `modules/apps/manifest.py`'s `effective_config()` fills a schema's defaults, as Mercury
    compiles the config, so a config that leaves `on_unavailable` out gets `allow`.
  - The URL takes a name, an IPv4 address, or an IPv6 address in brackets
    (`http://[2001:db8::53]:8053/verdict`).
- **`cache`:** `max_entries` and `ttl_seconds`.
- **`overrides`:** `allow` and `block`, lists of domains (`*.` for every name under one).

On a real network, Mercury compiles the config. The app never holds an address of its own.

**The compile step and the start-time config** (C2760, C2729; decision K9). The controller app
deploy's plan compiles each chosen app's config before it is previewed
(`compile_set` in `modules/apps/app_config.py`): the network's own config, if any, then each key the
manifest declares under `compiled`, then the schema's defaults, validated against
`config_schema`. A table role is the first table, by id, of the switch's platform profile that
takes the flows the role carries (`modules/sdn/placement.py`): `forward_table` a host's IPv4 and
IPv6 forwarding flows, `punt_table` the table miss, ARP and LLDP to the controller,
`meter_table` a flow through a meter. On the ProCurve's measured pipeline (C2601) that is 100,
200 and 100; a profile that records no tables (the Aristas, Open vSwitch) gives table 0 for
every role, and the preview says so. A network config that sets a compiled key is refused.
The config is staged as `/opt/ryu-apps/<app>/<version>.config.json`, its sha256 in the request
and the plan's hash, drawn masked in the preview beside what each switch's tables came from,
and checked by the apply script before the restart. The app reads it once, at load, with
`mercury_app.start_config(NAME, VERSION)`, which answers `{"ok", "error", "config", "path",
"sha256"}` and raises nothing: an absent, unreadable or malformed file is `ok` false with
`error` saying which, and the app's `/health` names it while no config is in force, never ok.

### An app's allowlist

`modules/apps/allowlist.py` holds it, in one table (`IMPORTS`), separate from a job's:
- **Imports:** the app's own modules, `ryu` and its submodules (but the few that open their
  own connections or load code by name: `ryu.lib.rpc`, `ryu.lib.ovs`, `ryu.lib.snortlib`,
  `ryu.services`, `ryu.contrib`, `ryu.cmd`, `ryu.utils`, and `ryu.lib.hub`'s `connect`,
  `listen` and servers), the app SDK `mercury_app`, and the standard library's data modules:
  `base64`, `collections`, `copy`, `dataclasses`, `datetime`, `enum`, `fnmatch`,
  `functools`, `hashlib`, `ipaddress`, `itertools`, `json`, `logging` (not its file or socket
  handlers), `math`, `re`, `string`, `struct`, `time`, `typing`, `uuid` (not `uuid1` or
  `getnode`). An app's tests may also use `pytest.raises` and, from the app SDK's
  `mercury_app.testing`, `covers`, `refused`, `netbox`, `RecordedRyu`, `HARNESS` and
  `UnrecordedPath`; never `modules.jobs`, which needs pydantic and Mercury's Python (C2644).
- **An app's tests run on the controller's Python, in the container harness:**
  `modules/apps/sdk/mercury_app/testing.py` and the app's fixed `conftest.py`
  (`modules/jobs/templates/app_conftest.py.template`; a job's is `conftest.py.template`) are
  written for 3.5, on the standard library alone. A test parameter named `ryu` is given the
  recorded Ryu, and `netbox` a NetBox over the objects a test gives
  (`netbox(objects={...})`); `ctx` is a job's, and an app's is refused, naming why.
  `tests/test_app_sdk_testing.py` holds its answers to `modules.jobs.testing`'s on the same
  inputs, and `mercury_app.testing.RecordedRyu` is the one parser of the recordings
  (`tests/fixtures/sdn/ryu_recorded.py` extends it with Mercury's Ryu driver).
- **Refused, by name:** every network, process, file or interpreter module (`socket`,
  `ssl`, `http`, `urllib`, `requests`, `subprocess`, `threading`, `os`, `sys`, `importlib`
  and the rest the table lists), any module not in the table, a private (`_`) name of an
  allowed one, and, as for a job, `open`, `exec`, `eval`, `getattr` and the other forbidden
  builtins.
- **The network only through `mercury_app.egress`, to a destination the manifest declares:**
  `egress("<name>", method, path, body, timeout)`, its destination a string literal naming an
  entry of the manifest's `egress`; the SDK reads the address from the network's config at
  that entry's `from_config` key. An undeclared name, a computed one, or `egress` passed,
  stored or wrapped is refused at check. The `manifest` check lists each declared destination,
  and the `static` check each call it read, so the reviewer sees every place the app reaches.
  `dns_blacklist` declares one, its verdict service (`verdict_service.url`).
- **The controller's Python, as measured:** every file is held to the version the network's
  controller runs apps on (below).

The app SDK's contract is `modules/apps/sdk/mercury_app/`: `start_config` is its working call
(a local file, the start-time config); `egress` is a stub until the working package lands
(C2645). Neither the controller's deploy nor the container harness puts the SDK on a
controller app's import path yet (C2852), so an app imports it guarded and its `/health` says
when it is absent (lab/lab9/apps/fabric_forwarding/fabric_forwarding.py). The allowlist is the check a person
can read; the controller's container and its network policy are the boundary.

### The controller's Python

An app is checked against the Python its network's controller runs apps on, as measured for
that network, never a fixed version (`modules/apps/python_versions.py`):
- **The record:** `modules/sdn/controller_runtime.py` keeps each network's own, in the
  network's folder (`controller_runtime.json`): the minor version, derived from what the
  controller app runtime's interpreter answered (`Python 3.5.2` is 3.5), the read that
  measured it (the Linux host capture list's `/opt/<folder>/bin/python --version`), the host,
  and when. It is a measurement, so it is neither a setting nor NetBox data, and it is kept
  outside the network's configuration repository, which the app gate never reads. There is
  no default.
- **Provisional, then measured:** a record may hold a provisional value (an earlier read's
  answer that is not the app runtime's own interpreter, with a note saying why), which the
  check targets and marks "(provisional)", naming its source. The interpreter read's
  measurement replaces it, and a provisional value never replaces a measurement. A value
  replaced by another minor version is a Needs attention row (`controller_python`,
  `changed`) naming both values and their sources; it clears when the network's apps are
  re-checked against the new version (`controller_runtime.record_recheck`) or a person
  acknowledges the change, and a later change raises it again.
- **The check:** `mercury app check <folder> --network <network>` (and
  `modules.apps.gate.check(folder, python=controller_runtime.target(network))`, the one
  function both call) parses each file with `ast.parse`'s `feature_version` at that version,
  then refuses what the parser lets through (f-strings and asynchronous generators on 3.5,
  among others) and every module, name or builtin newer than it, naming the file, the line,
  the version it needs and the controller's. A module the allowlist allows is refused on a
  controller older than it (`dataclasses` on 3.5).
- **Not known is a failure:** without `--network`, or for a network whose record holds none
  (or cannot be read), the `static` check says "can't tell: the controller's Python is not
  measured for <network>" and fails, never passes and never assumes a version.
- **On a 3.5 controller** (Ubuntu 16.04's `python3`): no f-strings (`str.format` or `%`), no
  variable annotations, no underscores in numbers, no asynchronous generators or `await` in a
  comprehension, no `:=`, no positional-only parameters, no `dataclasses`, `secrets` or
  `contextvars`, and every other row of the tables below.
- **What no static check sees:** a method of a value (`str.removeprefix`), an operator on a
  type (`dict | dict`), a keyword argument newer than its call (`zip(strict=...)`),
  behaviour (insertion-ordered dicts from 3.7) and grammar the parsed tree does not keep (a
  parenthesized `with`, `f"{x=}"`, `a[*b]`): only the app's tests run on the controller's
  version, in the container harness, find those.

The tables, generated from the check's own (tests/test_controller_python.py holds this file
and AUTHORING.md to them):

<!-- the controller's Python: generated by modules/jobs/scaffold.controller_python_markdown -->

| Grammar | Needs | On an older controller, instead |
|---|---|---|
| an f-string | 3.6 | use str.format or % |
| a variable annotation (`x: int = 1`) | 3.6 | leave it out, or write a `# type:` comment |
| an underscore in a numeric literal (`1_000`) | 3.6 | write the digits without it |
| an asynchronous generator (`yield` in an `async def`) | 3.6 | a Ryu app runs on ryu.lib.hub's green threads: spawn and sleep |
| `await` in a comprehension | 3.6 | await each in a loop |
| `async for` in a comprehension | 3.6 | write the loop out |
| an assignment expression (`:=`) | 3.8 | assign on its own line first |
| a positional-only parameter (`/`) | 3.8 | leave the `/` out |
| a decorator that is not a dotted name or a call of one (PEP 614) | 3.9 | bind it to a name first |
| a `match` statement | 3.10 | use if and elif |
| `except*` | 3.11 | use except |
| the `type` statement | 3.12 | assign the alias |
| a type parameter list (`def f[T]`) | 3.12 | leave it out |

What the standard library lacks before each version, from Python's documentation ("New in version"); a 3.5 controller lacks every row:

| Needs | Modules, names and builtins |
|---|---|
| 3.6 | `ModuleNotFoundError` (builtin), `collections.abc.AsyncGenerator`, `collections.abc.Collection`, `collections.abc.Reversible`, `enum.Flag`, `enum.IntFlag`, `enum.auto`, `hashlib.blake2b`, `hashlib.blake2s`, `hashlib.scrypt`, `hashlib.sha3_224`, `hashlib.sha3_256`, `hashlib.sha3_384`, `hashlib.sha3_512`, `hashlib.shake_128`, `hashlib.shake_256`, `math.tau`, `re.RegexFlag`, `secrets` (module), `typing.AsyncIterable` (3.5.2), `typing.AsyncIterator` (3.5.2), `typing.Awaitable` (3.5.2), `typing.ClassVar` (3.5.3), `typing.Collection`, `typing.ContextManager` (3.5.4, 3.6.0), `typing.Coroutine` (3.5.3), `typing.DefaultDict` (3.5.2), `typing.NewType` (3.5.2), `typing.TYPE_CHECKING` (3.5.2), `typing.Text` (3.5.2), `typing.Type` (3.5.2) |
| 3.7 | `contextvars` (module), `dataclasses` (module), `datetime.date.fromisoformat`, `datetime.datetime.fromisoformat`, `datetime.time.fromisoformat`, `math.remainder`, `re.Match`, `re.Pattern`, `time.clock_gettime_ns`, `time.clock_settime_ns`, `time.monotonic_ns`, `time.perf_counter_ns`, `time.process_time_ns`, `time.thread_time_ns`, `time.thread_time`, `time.time_ns`, `typing.AsyncContextManager` (3.5.4, 3.6.2), `typing.AsyncGenerator` (3.6.1), `typing.ChainMap` (3.5.4, 3.6.1), `typing.Counter` (3.5.4, 3.6.1), `typing.Deque` (3.5.4, 3.6.1), `typing.NoReturn` (3.5.4, 3.6.2) |
| 3.8 | `datetime.date.fromisocalendar`, `datetime.datetime.fromisocalendar`, `functools.cached_property`, `functools.singledispatchmethod`, `math.comb`, `math.dist`, `math.isqrt`, `math.perm`, `math.prod`, `typing.Final`, `typing.Literal`, `typing.OrderedDict` (3.7.2), `typing.Protocol`, `typing.SupportsIndex`, `typing.TypedDict`, `typing.final`, `typing.get_args`, `typing.get_origin`, `typing.runtime_checkable` |
| 3.9 | `functools.cache`, `graphlib` (module), `math.lcm`, `math.nextafter`, `math.ulp`, `typing.Annotated`, `zoneinfo` (module) |
| 3.10 | `EncodingWarning` (builtin), `aiter` (builtin), `anext` (builtin), `base64.b32hexdecode`, `base64.b32hexencode`, `itertools.pairwise`, `typing.Concatenate`, `typing.ParamSpec`, `typing.TypeAlias`, `typing.TypeGuard`, `typing.is_typeddict` |
| 3.11 | `BaseExceptionGroup` (builtin), `ExceptionGroup` (builtin), `datetime.UTC`, `enum.EnumCheck`, `enum.EnumType`, `enum.FlagBoundary`, `enum.ReprEnum`, `enum.StrEnum`, `enum.global_enum`, `enum.member`, `enum.nonmember`, `enum.property`, `enum.verify`, `hashlib.file_digest`, `logging.getLevelNamesMapping`, `math.cbrt`, `math.exp2`, `re.NOFLAG`, `string.Template.get_identifiers`, `string.Template.is_valid`, `tomllib` (module), `typing.LiteralString`, `typing.Never`, `typing.NotRequired`, `typing.Required`, `typing.Self`, `typing.TypeVarTuple`, `typing.Unpack`, `typing.assert_never`, `typing.assert_type`, `typing.dataclass_transform`, `typing.reveal_type` |
| 3.12 | `collections.abc.Buffer`, `itertools.batched`, `logging.getHandlerByName`, `logging.getHandlerNames`, `math.sumprod`, `typing.TypeAliasType`, `typing.override` |
| 3.13 | `base64.z85decode`, `base64.z85encode`, `copy.replace`, `math.fma`, `re.PatternError`, `typing.ReadOnly`, `typing.TypeIs` |
| 3.14 | `uuid.uuid6`, `uuid.uuid7`, `uuid.uuid8` |

<!-- end of the controller's Python -->

## The lifecycle (jobs and apps alike)

`modules/jobs/lifecycle.py` holds the lifecycle. Jobs and apps share the same code.

1. **Draft:** a new version, pinned by its folder's content hash (`content_hash`).
   - A job runs for its author only, and in plan mode only.
   - An app deploys only in the container harness.
2. **Published:** reviewed by someone other than its author, with its harness tests passed.
   - Self-review counts only where the installation's policy is single-user, and is recorded
     as self-review.
   - **Any committed edit moves the hash and returns it to Draft.**
   - Only a Published app version deploys to a real controller, byte for byte the version
     reviewed.
3. **Retired:** kept for audit.

**The content hash is the folder as git holds it,** `content_hash(repo, path, rev="HEAD")`.
- **What it covers:** each tracked file's path, git mode and blob id at that revision.
- **What can't move it:** running your tests (their `__pycache__`), an untracked file, or an
  edit you haven't committed.
- **What does:** a committed edit, rename, addition or removal, or a change of the executable
  bit.
- **Refused by name:** a symbolic link or a submodule in the folder.

**What runs is what was pinned** (the operator, 2026-11-06; built in P4 for jobs and P6 for
apps). The hash pins your folder as git holds it, so what runs must be that same content:
- **A Published job is loaded from the blobs of its pinned revision,** through the
  repository's git helper, never from the working tree.
  - Its run record's `content_sha256` is recomputed from what was sent to the sandbox.
  - A mismatch with the pin refuses the run, naming both hashes.
- **A Published app deploys the same way:** H stages and deploys the pinned revision's blobs,
  never the working tree.
- **A Draft may run its working tree, in plan mode only.** Its record is marked Draft, with
  the working tree's own hash, and "uncommitted" when that differs from HEAD's.
- **So an uncommitted edit to a Published job's or app's folder never runs or deploys.** To
  change what runs, commit it: the hash moves, and the version is a Draft again until it's
  reviewed.

## What you test against

The recorded fixtures in the repository:
- the masked Ryu answers, `tests/fixtures/lab9_captures/2026-11-06/ryu-rest.txt`, read by
  `tests/fixtures/sdn/ryu_recorded.py`;
- the masked device captures beside them (`tests/fixtures/lab9_captures/README.md` says how
  each was masked).

There are no lab addresses, DPIDs or names in code or tests beyond the fixtures, and no secrets
anywhere. Example values are documentation values: 192.0.2.0/24, 2001:db8::/32 and
`example.invalid`.
