# Writing a Mercury job or app: a guide for an AI assistant

`mercury job new` and `mercury app new` put this file in every new folder. It is written to be
pasted into an AI assistant (Claude Code, Copilot or another), so the assistant can write a job's
or app's code and tests and iterate against `mercury job check` (or `mercury app check`) until
it passes. The person you work for confirms the spec card and reviews the result; you write the
code and the tests.

## The loop

1. Read `spec.yml`, the spec card. It is the contract: what the job does, what it may reach,
   and two or more acceptance examples in plain Given/When/Then.
2. Write the code (`job.py`, or the app's module) and one or more tests per example.
3. Run `mercury job check <folder>` (`mercury app check <folder>` for an app). It prints each
   check, passed or FAILED, with what failed and the action that clears it. `--json` prints the
   same verdict as JSON.
4. Fix what it names and run it again, until every check passes.

**What you never do:**
- **Change the spec card's contract** (its permission, scope, inputs, outputs or examples)
  without the person. Where the card is unclear, ask the person; never guess. A field you
  cannot fill is written `{ask: "<the question>"}`, and the check refuses the card until the
  person answers it.
- **Weaken a test to make the check pass.** A failing test reports a real problem: fix the
  code, or show the person why the test's premise is wrong.
- **Mark a surviving mutant equivalent.** Only the reviewer, a person, may, with a reason; a
  mark made by an AI is refused. Kill a survivor with a test instead.

## The spec card (`spec.yml`)

| Field | What it holds |
|---|---|
| `kind` | `job` (the default) or `app` |
| `name` | a job's: lower case with hyphens (`switch-links`); an app's: lower case with underscores (`dns_overrides`) |
| `summary` | one sentence, at most 200 characters |
| `permission` | `read` or `write` (a write job plans changes) |
| `scope` | `object_types` (NetBox object types, such as `dcim.device`) and `roles` (device role slugs): what it may reach. There is no wildcard: an empty list reaches nothing |
| `inputs` | each a name and a type: `str`, `int`, `float`, `bool`, `HostRef`, `DeviceRef`, `dpid`, or `list[<one of them>]`; written `busy: int` or `busy: {type: int, description: ...}` |
| `outputs` | each a name and a type: `table`, `log`, `file`, `plan`, `str`, `int`, `float` or `bool` |
| `examples` | two or more, each a unique `name`, `given`, `when`, `then`, and the `fixture` its data comes from: `ryu_recorded` (the recorded controller) or `netbox_export` (the masked NetBox export) |

## The contract

A job is a class extending `Job`, in `job.py`:

```python
from modules.jobs import Job, JobInputs, JobMeta, Scope


class SwitchLinks(Job):
    meta = JobMeta(name="switch-links", version="1.0.0",
                   summary="Each switch with its link count, and which are busy.",
                   permission="read",
                   scope=Scope(object_types=["dcim.device"], roles=["openflow-switch"]))

    class Inputs(JobInputs):
        busy: int = 2

    def run(self, ctx, inputs):
        ...
```

- **`meta`** is checked when the class is defined; a refusal names the field, the value and
  the rule. A read job's `max_changes` is 0 (the default); a write job declares at least 1, the
  most changes one run may plan.
- **`Inputs`** subclasses `JobInputs`: typed fields, frozen, an unknown input refused by name. A
  device or host is a `DeviceRef` or a `HostRef` (its NetBox ID and its name).
- **`run(ctx, inputs)`** reaches the world only through `ctx`. A write is a call on
  `ctx.changes`, which records a plan; nothing is ever sent by the job itself.
- **Keep the logic in plain functions** (`link_counts(switches, links)`, `label(count, busy)`)
  that `run` calls: they are what the tests can pin exactly, and what the mutation step tests
  hardest.

An app's logic is the same: plain functions over plain data in the app's module (`<name>.py`),
beside `manifest.yml`, with tests in `test_app.py`. But an app is a Ryu controller app, not a
job, and it is held to its own allowlist (below, "An app's allowlist").

## The SDK's handles (`ctx`)

| Handle | What it offers |
|---|---|
| `ctx.controller` | the controller's reads: `switches()`, `switch_desc(dpid)`, `links()`, `hosts()`, `topology()`, `flows(dpid)`, `port_stats(dpid)`, `meters(dpid)`, each answering `{"ok": bool, "error": str, ...}` |
| `ctx.netbox` | `get(object_type, **filters)`, `one(object_type, id)`: NetBox, filtered to the scope; outside it raises `ScopeError` |
| `ctx.nsot` | `export()`: the network's committed export |
| `ctx.devices` | `show(device, command)`: allowlisted read commands only |
| `ctx.paths` | `trace(src, dst)`, `verify()` |
| `ctx.changes` | the change plan: `flow(dpid, do, flow=..., meter=...)`, `feature(device, feature, values)`, `app_policy(app, endpoint, body)`; a read job's change, a change past `max_changes`, or a value that is not plain data is refused |
| `ctx.output` | `table(title, columns, rows)`, `log(message)`, `file(name, content)` |
| `ctx.job_files` | the job's own files, read-only |

Always check a controller answer's `ok` before reading it.

## The fixtures

A test asks for a fixture by naming a parameter:
- **`ryu`**: the recorded controller (`RecordedRyu`). `ryu.driver()` is Mercury's real
  controller driver reading recorded answers; `ryu.dpids()` lists the recorded switches, and
  `ryu.get(path)` gives a recorded answer raw.
- **`ctx`**: a plan-mode `FakeContext` for the folder's job, its controller the recorded one.
- **`netbox`**: a `FakeNetBox` read within the job's scope. Until the masked NetBox export
  lands, call `netbox(job, objects={...})` with the objects the test needs.

Or build the run yourself, from `modules.jobs.testing`:
- **`plan_run(JobClass, {inputs}, controller=ryu.driver())`** validates the inputs, runs the job
  in plan mode and answers the context: `ctx.output.tables`, `ctx.output.lines`,
  `ctx.output.files`, and the plan in `ctx.changes.changes`.
- **`FakeContext(JobClass.meta, controller=..., netbox={...}, nsot={...}, devices={...})`** for
  a controller (or any handle) answering what the test gives it, such as one that does not
  answer.

## The tests

- **pytest's format:** plain `def test_...():` functions with `assert`, in `test_*.py` files
  at the folder's root, beside the code, or in its `tests/` subfolder; nowhere else (a
  `tests/` folder holds test files only, and a test file's name is used once). The same
  folder runs under `pytest` (the folder's `conftest.py` gives the fixtures) and under
  Mercury's runner, which `mercury job check` uses.
- **Each example is covered:** mark a test `@covers("<the example's name>")` (from
  `modules.jobs`), the name exactly as `spec.yml` writes it.
- **Expected refusals:** `with pytest.raises(SomeError, match="..."):` or
  `with refused("..."):` (from `modules.jobs`). `pytest.raises` is the only part of pytest a
  test may use: no `pytest.mark`, no `pytest.fixture`, no classes of tests.
- **What a job's code and tests may import:** the folder's own modules (`from job import
  ...`), `modules.jobs`, `modules.jobs.testing` (tests only), and the standard library's safe
  set (`collections`, `dataclasses`, `itertools`, `json`, `math`, `re` and the like). No
  files, no sockets, no subprocesses, no `eval`. An app's are its own allowlist's, below.
- **Assert the exact result** the example's `then` gives, worked out independently of the code
  (from the recording, or by hand), never the code's own output read back. A test that asserts
  whatever the code answers today passes when the code is wrong; the mutation step finds it.

## An app's allowlist

A job runs in Mercury's sandbox, reaching the world only through `ctx`. An app is a Ryu
controller app: it runs in the controller, on the Python its network's controller runs apps
on, so its code and tests are checked against that version, as measured (below, "The
controller's Python").

**What an app's code and tests may import:** its own modules (by name), `ryu`, the app SDK
`mercury_app`, and the standard library's data modules in this table; its tests may also use
`pytest.raises` and, from the app SDK's `mercury_app.testing`, `covers`, `refused`, `netbox`,
`RecordedRyu`, `HARNESS` and `UnrecordedPath` (never `modules.jobs`, which needs Mercury's
Python). No `open`, `exec`, `eval` or `getattr`, as for a job.

<!-- the app allowlist: generated by modules/jobs/scaffold.app_allowlist_markdown -->

| Module | Why it is allowed | Refused of it |
|---|---|---|
| `base64` | encodes and decodes bytes as text | its private (`_`) names |
| `collections` and its submodules | containers (deque, OrderedDict, Counter; collections.abc) | its private (`_`) names |
| `copy` | copies plain data | its private (`_`) names |
| `dataclasses` | records as classes | its private (`_`) names |
| `datetime` | dates, times and durations | its private (`_`) names |
| `enum` | named constants | its private (`_`) names |
| `fnmatch` | a name matched against a shell-style pattern | its private (`_`) names |
| `functools` | caching and partial functions over plain data | its private (`_`) names |
| `hashlib` | digests of bytes | its private (`_`) names |
| `ipaddress` | IPv4 and IPv6 addresses and networks as values; it opens no connection | its private (`_`) names |
| `itertools` | iteration over plain data | its private (`_`) names |
| `json` | JSON text to and from plain data (its load and dump take an open file, which an app has none of) | its private (`_`) names |
| `logging` | the app's log lines (RyuApp's self.logger is a logging.Logger) | `FileHandler`: it writes a file: log through the controller's logger; `basicConfig`: it can open a file and replaces the controller's handlers; `config`: logging.config opens files and listens on a socket; `handlers`: logging.handlers writes files and sends to sockets |
| `math` | arithmetic | its private (`_`) names |
| `mercury_app` | the app SDK: mercury_app.egress, the app's one way to the network, and mercury_app.start_config, the start-time config Mercury staged for it | its private (`_`) names |
| `re` | regular expressions | its private (`_`) names |
| `ryu` and its submodules | the controller framework the app runs in | its private (`_`) names |
| `ryu.lib.hub` | Ryu's green threads: spawn, sleep, Event, Queue | `StreamClient`: it opens a connection or a listening socket of its own; `StreamServer`: it opens a connection or a listening socket of its own; `WSGIServer`: it opens a connection or a listening socket of its own; `connect`: it opens a connection or a listening socket of its own; `listen`: it opens a connection or a listening socket of its own |
| `string` | string constants and templates | its private (`_`) names |
| `struct` | packs and unpacks a packet's fields | its private (`_`) names |
| `time` | the clock and sleeps: a TTL, a timeout | its private (`_`) names |
| `typing` | type annotations | its private (`_`) names |
| `uuid` | random identifiers (uuid4) | `getnode`: it reads the host's hardware address, which can start a process; `uuid1`: it reads the host's hardware address, which can start a process |

Refused by name (any module not in the table above is refused too):

- `_thread`, `concurrent`, `eventlet`, `greenlet`, `multiprocessing`, `pty`, `signal`, `subprocess`, `threading`: a process or thread module: an app runs in the controller's own loop (ryu.lib.hub's spawn and sleep)
- `aiohttp`, `asyncio`, `ftplib`, `http`, `httpx`, `imaplib`, `poplib`, `requests`, `select`, `selectors`, `smtplib`, `socket`, `socketserver`, `ssl`, `telnetlib`, `urllib`, `urllib3`, `xmlrpc`: a network module: an app reaches the network only by mercury_app.egress, to a destination its manifest declares
- `ast`, `builtins`, `code`, `codeop`, `ctypes`, `gc`, `importlib`, `inspect`, `marshal`, `pickle`, `runpy`, `types`: it reaches the interpreter's internals or loads code by name
- `glob`, `io`, `os`, `pathlib`, `shelve`, `shutil`, `sys`, `tempfile`: a file or operating-system module: an app is given its config by Mercury, and reads no file
- `logging.config`: it opens files and listens on a socket: a network module: an app reaches the network only by mercury_app.egress, to a destination its manifest declares
- `logging.handlers`: it writes files and sends to sockets: a network module: an app reaches the network only by mercury_app.egress, to a destination its manifest declares
- `ryu.cmd`: Ryu's command lines start managers and processes: a process or thread module: an app runs in the controller's own loop (ryu.lib.hub's spawn and sleep)
- `ryu.contrib`: libraries Ryu vendors, network clients among them: a network module: an app reaches the network only by mercury_app.egress, to a destination its manifest declares
- `ryu.lib.ovs`: it connects to an OVSDB server itself: a network module: an app reaches the network only by mercury_app.egress, to a destination its manifest declares
- `ryu.lib.rpc`: an RPC endpoint over its own socket: a network module: an app reaches the network only by mercury_app.egress, to a destination its manifest declares
- `ryu.lib.snortlib`: it listens on a socket of its own: a network module: an app reaches the network only by mercury_app.egress, to a destination its manifest declares
- `ryu.services`: protocol speakers (BGP, OVSDB, VRRP, Zebra) with sockets of their own: a network module: an app reaches the network only by mercury_app.egress, to a destination its manifest declares
- `ryu.utils`: it loads modules and files by name: it reaches the interpreter's internals or loads code by name

<!-- end of the app allowlist -->

**The network only through `mercury_app.egress`, to a destination the manifest declares.**
Each destination is an entry of `manifest.yml`'s `egress`: its `name`, the `from_config` key
whose value is its address (a string key the manifest's `config_schema` declares), and its
`purpose`. The app never holds an address: the network's config does, and the SDK reads it.
The call names its destination as a string literal:

```python
from mercury_app import egress


def ask_verdict(domain, timeout):
    """The verdict service's answer for *domain*, `{"ok": ..., "body": ...}`."""
    return egress("verdict_service", "POST", "/verdict", {"domain": domain}, timeout)
```

`mercury app check` refuses an egress call to a name the manifest does not declare, a
destination that is not a string literal, and `egress` passed, stored or wrapped; its
`manifest` check lists each declared destination and its `static` check each call it read,
for the reviewer.

**An app's tests run in the container harness, never in the job sandbox.** `mercury app check`
runs no app code: its `spec`, `manifest`, `static`, `examples` and `asserts` checks read the
source, and the checks that need the code run (`tests`, `mutation`, `survivors`, `reconcile`)
say "not run" until the harness runs them, so an app's verdict does not pass before then.
There, they run on the controller's Python: `mercury_app.testing` and the app's fixed
`conftest.py` are written for 3.5, and give a test parameter named `ryu` the recorded Ryu and
one named `netbox` a NetBox over the objects the test gives (`netbox(objects={...})`); an app
has no `ctx`, which is a job's.

## The controller's Python

An app is checked against the Python its network's controller runs apps on, **as measured for
that network**, never a fixed version: `mercury app check <folder> --network <network>`
reads the network's record (the minor version, such as 3.5, with the read that measured it,
the host and when) and holds every file to it. The `static` check's passed line names the
version and where it was measured. Without `--network`, or for a network whose record holds
none, `static` says "can't tell: the controller's Python is not measured for <network>" and
fails: it never passes and never assumes a version.

A record may hold a **provisional** value, an earlier read's answer that is not the app
runtime's own interpreter (a capture's `python3 --version`): the check targets it, its line
says "(provisional)" and names where the value came from. A measurement replaces it; one of
another minor version is a Needs attention row, naming both, until the network's apps are
re-checked against the new version or the change is acknowledged.

Each file is parsed as that version (`ast.parse` with its `feature_version`), and the check
refuses what the parser lets through: the grammar in the first table, and the standard
library's modules, names and builtins in the second, each newer than the controller's
version, naming the file, the line, the version it needs and the controller's. A module the
app allowlist allows is refused on a controller older than it (`dataclasses` on 3.5).

**On a 3.5 controller** (Ubuntu 16.04's `python3`) that rules out every row of both tables:
no f-strings (use `str.format` or `%`), no variable annotations (`x: int = 1`), no
underscores in numbers (`1_000`), no asynchronous generators or `await` in a comprehension,
no `:=`, no positional-only parameters, no `dataclasses`, `secrets` or `contextvars`, no
`enum.auto`, no `datetime.fromisoformat`, no `re.Match`, no `math.tau`, and none of the
`typing` names added since. Written for 3.5:

```python
LOG.info("switch %s port %s is down", dpid, port)  # not f"switch {dpid} port {port} is down"
label = "{}:{}".format(dpid, port)                  # not f"{dpid}:{port}"
```

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

**What no static check sees:** a method of a value (`str.removeprefix`, 3.9), an operator on a
type (`dict | dict`, 3.9), a keyword argument newer than its call (`zip(strict=...)`, 3.10),
behaviour (a `dict` keeps insertion order only from 3.7), and grammar the parsed tree does
not keep (a parenthesized `with`, `f"{x=}"`, `a[*b]`). Only a run of the app's tests on the
controller's version finds those: the container harness's.

## What `mercury job check` checks

The checks run in this order, and each prints, when it fails, what failed and the action below.

<!-- the gate's checks: generated by modules/jobs/scaffold.gate_checks_markdown -->

1. **`spec`.** spec.yml is a valid spec card: the contract, two or more acceptance examples, and no `ask:` question left open.

   > To clear it: Correct each field named in spec.yml, and answer each `ask:` question: the spec card is the decision a person confirms.

2. **`static`.** Every module and test of the folder passes the AST allowlist: imports only of the folder's own modules, modules.jobs, modules.jobs.testing, pytest's raises (in tests) and the standard library's safe set; no open, exec, eval, getattr or other forbidden builtin; no dunder or frame attribute; no bare except.

   > To clear it: Remove each use named: a job reaches the world only through ctx, and imports only its own modules, modules.jobs and the standard library's safe set.

   When a file itself is refused (a link, too large, not UTF-8, a name that shadows an import, Python in a subfolder other than tests/):

   > To clear it: Correct each file named.

3. **`tests`.** The tests pass under Mercury's runner, in one process, with no network; a failed assertion shows both sides.

   > To clear it: Fix the code or the test named: each failed assertion shows both sides.

4. **`examples`.** Every acceptance example is covered by at least one test marked `@covers("<example name>")`, and every `@covers` names an example.

   > To clear it: Mark a test @covers("<example>") for each example named, or correct the name that matches no example.

5. **`asserts`.** Every test asserts something: an assert, a pytest.raises or a refused() block, directly or through a helper.

   > To clear it: Give each test named an assert, a pytest.raises or a refused() block: a test that asserts nothing passes whatever the code does.

6. **`mutation`.** The job's own code is mutated (comparisons, boundaries, booleans, conditions, constants, arithmetic, returns, call statements, break and continue) and every mutant runs within its budget.

   > To clear it: Make the tests faster (the step's bound), or split the job or name its changed lines (the ceiling of 200 mutants): every mutant must run.

7. **`survivors`.** Every mutant the tests did not notice is killed by a new test, or marked equivalent by the reviewer, a person, with a reason.

   > To clear it: Add a test that fails for each change named, or have the reviewer (a person, never an AI) mark it equivalent with a reason.

A check that cannot run because an earlier one failed says "not run", and:

> To clear it: Clear the <earlier> check first.

An app's verdict (`mercury app check`) runs no app code: it has `manifest` first and `reconcile` last, and its `static` check is the app allowlist's, not the job's:

- **`manifest`.** manifest.yml is valid, names the app the spec card names, lists each test as a test_*.py file at the folder's root or in tests/, and declares every network destination the app reaches (egress), which the check lists.

  > To clear it: Correct each field named in manifest.yml.

- **`static`.** Every module and test of the app parses as the Python its network's controller runs apps on, as measured and recorded for the network (never assumed), uses no grammar, module or name that version lacks, and passes the app allowlist: imports only of the app's own modules, ryu, the app SDK (mercury_app) and the standard library's data modules (in tests, also pytest's raises and mercury_app.testing's covers, refused and fixtures); no network, process, file or interpreter module; the network reached only by mercury_app.egress, its destination a string literal the manifest declares; and the job allowlist's builtin, dunder and except rules.

  > To clear it: Remove each use named: an app imports ryu, mercury_app and the standard library's data modules, and reaches the network only by mercury_app.egress("<a destination manifest.yml declares>", ...).

  When the controller's Python is not known ("can't tell"):

  > To clear it: Name the app's network (`mercury app check <folder> --network <network>`). Its controller's Python is the network's record, measured by the controller host's interpreter read (`/opt/<folder>/bin/python --version`); a network whose record holds none cannot be checked until that read records it.

- **`reconcile`.** The reconcile test (T16) passes in the container harness: the app is connected, disconnected and reconnected with another owner's flows, and adds or removes only the difference.

- `tests`, `mutation`, `survivors` and `reconcile` need the app's code run, in the container harness, never in the job sandbox: until the harness lands each says "not run: app tests run in the container harness, which lands with P2a", so an app's verdict does not pass yet.

  > To clear it: Run `mercury app check` again once the container harness (P2a) is installed: an app's code runs there, never in the job sandbox, and until it runs, the app's verdict cannot pass.

- `spec`, `examples` and `asserts` are the job gate's, read from the source.

<!-- end of the gate's checks -->

## A worked read job: `switch-links`

From Mercury's own job fixtures (`tests/fixtures/jobs/switch-links/`), which pass every check.
The card:

<!-- quoted from tests/fixtures/jobs/switch-links/spec.yml -->
```yaml
kind: job
name: switch-links
summary: Each switch with its link count, and which are busy.
permission: read
scope:
  object_types: [dcim.device]
  roles: [openflow-switch]
inputs:
  busy: {type: int, description: more links than this is busy (2 if not given)}
outputs:
  links: table
examples:
  - name: every switch is listed with its links
    given: the recorded controller's switches and links
    when: the job runs
    then: each switch is a row with the number of links leaving it, in dpid order
    fixture: ryu_recorded
  - name: a switch past the threshold is busy
    given: a threshold of 2
    when: a switch has 3 links, another 2, another none
    then: the first is busy, the second ok, the third isolated
    fixture: ryu_recorded
```

The code: two plain functions, and `run` reading the controller through `ctx`:

<!-- quoted from tests/fixtures/jobs/switch-links/job.py -->
```python
def link_counts(switches, links):
    """`{dpid: links leaving it}`, every switch named, a link from elsewhere not counted."""
    counts = {s["dpid"]: 0 for s in switches}
    for link in links:
        dpid = link["src"]["dpid"]
        if dpid in counts:
            counts[dpid] += 1
    return counts


def label(count, busy):
    """A switch's state: busy past *busy* links, isolated with none, otherwise ok."""
    if count > busy:
        return "busy"
    if count == 0:
        return "isolated"
    return "ok"
```

<!-- quoted from tests/fixtures/jobs/switch-links/job.py -->
```python
    def run(self, ctx, inputs):
        switches = ctx.controller.switches()
        links = ctx.controller.links()
        if not switches["ok"] or not links["ok"]:
            ctx.output.log("the controller did not answer")
            return
        counts = link_counts(switches["switches"], links["links"])
        rows = [[dpid, n, label(n, inputs.busy)] for dpid, n in sorted(counts.items())]
        ctx.output.table("switch links", ["dpid", "links", "state"], rows)
```

The tests of its two examples. The first counts the links from the recording's raw answers, not
through the job's own code, so it checks the job rather than repeating it; the second pins each
side of each boundary (3 against 2 is busy, 2 against 2 is not, 0 is isolated):

<!-- quoted from tests/fixtures/jobs/switch-links/test_job.py -->
```python
from job import SwitchLinks, label, link_counts
from modules.jobs import covers, refused
from modules.jobs.testing import FakeContext, plan_run


def recorded_counts(ryu):
    """The links leaving each switch, counted here from the recording's raw answers."""
    counts = {int(d): 0 for d in ryu.dpids()}
    for link in ryu.get("/v1.0/topology/links"):
        counts[int(link["src"]["dpid"], 16)] += 1
    return counts


@covers("every switch is listed with its links")
def test_every_switch_is_listed_with_its_links(ryu):
    ctx = plan_run(SwitchLinks, {"busy": 2}, controller=ryu.driver())
    table = ctx.output.tables[0]
    assert table["title"] == "switch links"
    assert table["columns"] == ["dpid", "links", "state"]
    expected = recorded_counts(ryu)
    assert [row[0] for row in table["rows"]] == sorted(expected)
    assert [row[1] for row in table["rows"]] == [expected[d] for d in sorted(expected)]
    assert ctx.changes.changes == []


@covers("a switch past the threshold is busy")
def test_a_switch_past_the_threshold_is_busy():
    assert label(3, 2) == "busy"
    assert label(2, 2) == "ok"
    assert label(1, 2) == "ok"
    assert label(0, 2) == "isolated"
```

Its other tests cover what the examples leave out: the default threshold, a link from another
switch, a controller that does not answer, and an input that is not a number.

## A worked app: `dns_overrides`

An app's folder holds `spec.yml` (with `kind: app`), `manifest.yml`, its module and its tests
(`tests/fixtures/apps/dns_overrides/`). Its card:

<!-- quoted from tests/fixtures/apps/dns_overrides/spec.yml -->
```yaml
kind: app
name: dns_overrides
summary: Decides a DNS query by the app's overrides, before any verdict is asked.
permission: read
scope:
  object_types: [dcim.device]
  roles: [openflow-switch]
inputs:
  name: str
outputs:
  decision: str
examples:
  - name: a blocked name is blocked even when it is also allowed
    given: overrides blocking blocked.example.invalid and allowing it too
    when: a host asks for blocked.example.invalid
    then: the decision is block
    fixture: ryu_recorded
  - name: a zone covers every name under it but not itself
    given: overrides blocking *.blocked-zone.example.invalid
    when: a host asks for a.blocked-zone.example.invalid, then for blocked-zone.example.invalid
    then: the first is blocked, and the second is left to the verdict service (ask)
    fixture: ryu_recorded
```

Its manifest names the same app, its config's schema, its `/health` endpoint and its tests:

<!-- quoted from tests/fixtures/apps/dns_overrides/manifest.yml -->
```yaml
name: dns_overrides
version: 0.1.0
summary: Decides a DNS query by the app's overrides, before any verdict is asked.
controllers:
  ryu: ">=4.34"
openflow_versions: ["1.3"]
requires: []
config_schema:
  $schema: https://json-schema.org/draft/2020-12/schema
  type: object
  additionalProperties: false
  required: [overrides]
  properties:
    overrides:
      description: Domains decided here; block wins over allow.
      type: object
      additionalProperties: false
      properties:
        allow: {type: array, items: {type: string}}
        block: {type: array, items: {type: string}}
rest:
  prefix: /dns_overrides
  endpoints:
    - path: /health
      methods: [GET]
      summary: The app is loaded and answers.
tests:
  - test_app.py
```

Its logic, plain functions over the config and a name:

<!-- quoted from tests/fixtures/apps/dns_overrides/dns_overrides.py -->
```python
def matches(pattern, name):
    """Whether *name* is the domain *pattern*, or under it when it starts `*.`."""
    name = name.lower().rstrip(".")
    pattern = pattern.lower().rstrip(".")
    if pattern.startswith("*."):
        return name.endswith("." + pattern[2:])
    return name == pattern


def decide(config, name):
    """`block`, `allow` or `ask` for a query for *name*, by *config*'s overrides."""
    overrides = config.get("overrides", {})
    if any(matches(p, name) for p in overrides.get("block", [])):
        return "block"
    if any(matches(p, name) for p in overrides.get("allow", [])):
        return "allow"
    return "ask"
```

Its tests pin each decision and each edge: a name under the zone, the zone itself, a name that
only ends with the zone's letters (`xblocked-zone...`), case and a trailing dot:

<!-- quoted from tests/fixtures/apps/dns_overrides/test_app.py -->
```python
@covers("a zone covers every name under it but not itself")
def test_a_zone_covers_every_name_under_it_but_not_itself():
    assert decide(ZONE, "a.blocked-zone.example.invalid") == "block"
    assert decide(ZONE, "blocked-zone.example.invalid") == "ask"
    assert decide(ZONE, "xblocked-zone.example.invalid") == "ask"
```

`mercury app check` passes its `manifest`, `spec`, `static`, `examples` and `asserts` checks;
its `tests`, `mutation`, `survivors` and `reconcile` wait for the container harness, which
runs its code.

## A worked failure: a tautological test

The `tautology` fixture (`tests/fixtures/jobs/tautology/`) says whether a switch is busy:

<!-- quoted from tests/fixtures/jobs/tautology/job.py -->
```python
def label(count, busy):
    return "busy" if count > busy else "ok"
```

and its one test asserts what the code answers today, for one input:

<!-- quoted from tests/fixtures/jobs/tautology/test_job.py -->
```python
@covers("a busy switch is busy", "a quiet switch is ok")
def test_label():
    assert label(5, 3) == "busy"
```

It passes the `tests`, `examples` and `asserts` checks. The mutation step then changes the code
one place at a time, and three changes go unnoticed; `mercury job check` prints, under
`survivors`:

<!-- the gate's words on tests/fixtures/jobs/tautology -->
```text
your tests didn't notice when line 9's `>` became `>=` (job.py line 9: return "busy" if count > busy else "ok"; mutant 0cfa52e016550a2c)
your tests didn't notice when line 9's string `'ok'` became `''` (job.py line 9: return "busy" if count > busy else "ok"; mutant 259779f585688119)
your tests didn't notice when line 21's `3` became `4` (job.py line 21: ctx.output.log(label(inputs.count, 3)); mutant b1a2a9e8456a747f)
```

Each says what a test never checked: that a switch at exactly the threshold is ok (`>` and `>=`
differ only there), that a quiet switch's answer is `"ok"` (no test ever got one), and that the
job's threshold is 3 (a run at 4 links tells 3 from 4). One test per example, each pinning both
sides of the boundary, and a run on each side of the job's threshold, kill all three:

<!-- the fixed tests of tests/fixtures/jobs/tautology -->
```python
from job import Tautology, label
from modules.jobs import covers
from modules.jobs.testing import plan_run


@covers("a busy switch is busy")
def test_a_busy_switch_is_busy():
    assert label(4, 3) == "busy"
    assert label(5, 3) == "busy"


@covers("a quiet switch is ok")
def test_a_quiet_switch_is_ok():
    assert label(3, 3) == "ok"
    assert label(0, 3) == "ok"


def test_the_job_says_busy_past_three_links(ryu):
    for count, said in ((3, "ok"), (4, "busy")):
        ctx = plan_run(Tautology, {"count": count}, controller=ryu.driver())
        assert ctx.output.lines == [said]
```

With them, `survivors` reads "no survivors". Marking the survivors equivalent instead would have
been wrong: each was a real behaviour no test held.
