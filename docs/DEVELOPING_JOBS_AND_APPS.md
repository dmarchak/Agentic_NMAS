# Developing jobs and controller apps for Mercury

For the team building on Mercury for the final SDN lab. It covers writing a **job** (a saved,
rerunnable script that reaches the network only through Mercury) and a **controller app** (a
Ryu app that Mercury packages, checks and deploys). What is here is the published contract:
the shapes are fixed now, so the pure logic can be written and unit-tested before the framework
that runs it lands.

The design behind it is the SDN platform design, revision 4: section 11 (jobs, I-1),
section 12 (controller apps, I-2) and section 14 (the lab as the acceptance test).

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
  Ryu driver reading Ryu's recorded answers, so a job sees exactly the shapes it will see on
  the lab.
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
| `rest` | `prefix` and `endpoints`, each a `path` and its `methods`; `/health` answering GET is required; `/validate`, if offered, answers POST |
| `owns_flows` | optional: `cookie_prefix` and `cookie_mask` (64-bit hex), and the protected `classes` it owns |
| `tests` | optional: its unit tests, as paths relative to the app's folder |

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

## What you get, and when

| What | Ready by |
|---|---|
| The contracts (this guide, and the modules it names) | Sat Nov 7 |
| The container harness (real OVS and Ryu, one command to run an app against it) | Mon Nov 9 |
| H's harness (deploy your app the way the lab will) | Thu Nov 12 |
| The first two sessions' recordings, masked | Fri Nov 13 |

**`dns-blacklist` is due Wed Nov 18:** the logic, its `manifest.yml` and its unit tests, as
one PR. It deploys on hardware at the Nov 19 session.

## The workflow

1. Branch from `main`.
2. Write the logic and its unit tests (pytest, no network).
3. Run the harness locally (real Ryu and OVS in containers), once it lands.
4. Open a PR saying what it does, which contract it implements and what you tested.
5. The operator reviews and merges. Every contribution is flagged by author before anything is
   published, so say in the PR what is yours.
6. Deploy at the lab through Mercury (a job run or an app deploy), never by scp or by hand.
