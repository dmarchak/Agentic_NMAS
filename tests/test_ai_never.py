"""The AI's NEVERs that had no test (C3662's survey, 2026-11-14; C3681, C3682, C3683): from a
model's answer, no path in Mercury's code reaches a settings write, a secret's write, a
notification store's write, a template approval, an approval or a confirm, or a job's start.

**The graph.** Every module-level function and class of the product (`modules/`, `routes/`,
`app.py`) is a unit. A unit's edges are what it reaches by the file's own imports, parsed
(`test_ai_fix_rule.references`, an attribute of an imported name, a ``getattr`` of a constant,
an ``import_module``; a docstring or a comment names nothing), its bare calls of an imported name,
and its bare calls of a unit of its own file. **The entries** are the units of `modules/ai/` that
ask a model: those reaching `gateway.ask` or the read loop's `run`, which asks through the ask it
is given. Everything reachable from an entry is the answer's reach.

**The populations** (each a function whose call writes, every one derived or named with why):
- **settings** (C3681): the settings write path (`settings_schema.write_settings`, the file
  writer under it, `ratify`, `migrate`), each network's settings writer (`list_settings.write`);
  the heal policy's, the background switches', the device state class's and every card's writes
  all go through these, so reaching any of them is reaching one of these;
- **secrets** (C3682): `secrets_store.set_secret`, the credential store's one writer
  (`credentials._save`, under every profile, override, read-only account and notify secret);
- **notifications** (C3681): the teams store's one writer (`notify.teams._write`);
- **template approval** (C3681): the approvals file's one writer (`nsot.approval._save`, under
  `approve`, `revoke` and the acknowledgement);
- **approvals and confirms** (C3682): the approval queue's resolve (`approval_queue.mark_done` and
  its unguarded half), and every view of a route the gate table marks ``approve`` or ``confirm``
  (`route_gates.GATES`, derived from the app's own url map);
- **job starters** (C3683, measured 2026-11-14: `capture_job.start`, `deploy_job.start` and
  `deploy_job.start_restore` were NOT in tests/test_ai_fix_rule.py's derived run population, which
  holds the catalog's starters, confirm views, sends and the device hold): every module-level
  ``start`` or ``start_*`` of the product that starts a thread or a job (`Thread`, or the job
  registry's `capture_job.start`), and the plan engine's run.

**What it assumes, and does not see.** A call through an object's attribute that no import
names (``self.x()``, a callable passed in as an argument, a name built at run time) is no edge:
the read loop's ``ask`` is handed in, so `read_loop.run` is an entry by name, and a run function
handed to the AI as a callable would not be seen (tests/test_ai_fix_rule.py C scans for such
references in modules/ai/). A class reached is reached whole.
"""
import ast
import os

import pytest

from tests.source_index import tracked
from tests.test_ai_fix_rule import ROOT, _source, bindings, references

#: The asks: a unit reaching one of these asks a model.
ENTRIES = ("modules.ai.gateway.ask", "modules.ai.read_loop.run")

SETTINGS = ("modules.settings_schema.write_settings", "modules.config.save_user_settings",
            "modules.settings_schema.ratify", "modules.settings_schema.migrate",
            "modules.list_settings.write")
SECRETS = ("modules.secrets_store.set_secret", "modules.credentials._save")
NOTIFY = ("modules.notify.teams._write",)
TEMPLATES = ("modules.nsot.approval._save",)
APPROVALS = ("modules.approval_queue.mark_done", "modules.approval_queue._mark_done_unguarded")
#: Floors: the product's units, and the asking units, on 2026-11-14 (about 9,000 and 40).
UNITS_AT_LEAST = 8000
ENTRIES_AT_LEAST = 12
#: What the entries reach, at least (1,559 units before the families' executors, 2026-11-14).
REACH_AT_LEAST = 1200


def product_files() -> dict:
    """``{path: source}`` of every product file: what git tracks (`source_index.tracked`), and
    the files git does not track yet but does not ignore (a build in the working tree is
    product code too, and is scanned), both named by git, never by a walk of the disk. A
    planted module is added to this map by its test."""
    import subprocess

    rels = [os.path.relpath(p, ROOT) for p in tracked("modules", "routes", suffix=".py")]
    rels.append("app.py")
    new = subprocess.run(["git", "-C", ROOT, "ls-files", "--others", "--exclude-standard",
                          "--", "modules", "routes"], capture_output=True, text=True,
                         check=True).stdout.split()
    rels += [p for p in new if p.endswith(".py")]
    return {r: _source(r) for r in sorted(set(rels)) if os.path.isfile(os.path.join(ROOT, r))}


def module_of(rel: str) -> str:
    rel = rel[:-3]
    if rel.endswith("/__init__"):
        rel = rel[: -len("/__init__")]
    return rel.replace("/", ".")


def units_of(rel: str, source: str) -> dict:
    """``{unit name: (reached dotted names, own-file units called)}`` for one file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    package = module_of(rel) if rel.endswith("__init__.py") else os.path.dirname(rel).replace(
        "/", ".")
    bound, _imported = bindings(tree, package)
    refs = references(source, package)
    out = {}
    tops = [n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    names = {n.name for n in tops}
    for node in tops:
        lo, hi = node.lineno, node.end_lineno or node.lineno
        reached = {name for line, name in refs if lo <= line <= hi}
        local = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id in bound:
                    reached.add(bound[n.func.id])
                elif n.func.id in names:
                    local.add(n.func.id)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in names \
                    and n.id != node.name:
                local.add(n.id)              # a unit handed on (a job's work, a callback)
        out[node.name] = (reached, local)
    return out


def graph(files: dict) -> dict:
    """``{"module.unit": (reached dotted names, own-module units)}`` over *files*."""
    out = {}
    for rel, source in files.items():
        module = module_of(rel)
        for name, (reached, local) in units_of(rel, source).items():
            out[f"{module}.{name}"] = (reached, {f"{module}.{n}" for n in local})
    return out


def _unit_for(name: str, units: dict) -> str:
    """The unit a dotted name lands on: itself, or the unit it is an attribute of."""
    while name and name not in units:
        name = name.rpartition(".")[0]
    return name


def family_runs(files: dict) -> set:
    """Every read family's executor (`read_loop.ReadFamily(..., run=...)` in modules/ai/): the
    read loop calls it with what a model asked for, through the family, never by name, so it
    is an entry of its own."""
    out = set()
    for rel, source in files.items():
        if not rel.startswith("modules/ai/"):
            continue
        module = module_of(rel)
        tree = ast.parse(source)
        bound, _ = bindings(tree, os.path.dirname(rel).replace("/", "."))
        own = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(
                    node.func, "id", "")) == "ReadFamily"):
                continue
            for kw in node.keywords:
                if kw.arg == "run" and isinstance(kw.value, ast.Name):
                    name = kw.value.id
                    out.add(f"{module}.{name}" if name in own else bound.get(name, ""))
                elif kw.arg == "run" and isinstance(kw.value, ast.Attribute):
                    from tests.test_ai_fix_rule import resolved
                    out.add(resolved(kw.value, bound))
    return {o for o in out if o}


def entries(units: dict, files: dict = None) -> list:
    asking = {u for u, (reached, _l) in units.items() if u.startswith("modules.ai.")
              and any(r == e or r.startswith(e + ".") for r in reached for e in ENTRIES)}
    runs = family_runs(files) if files is not None else set()
    return sorted(asking | {r for r in runs if r in units})


def reach(units: dict, start) -> dict:
    """``{unit: the unit it was reached from}`` for everything reachable from *start*."""
    seen = {s: "" for s in start}
    todo = list(start)
    while todo:
        u = todo.pop()
        reached, local = units.get(u, (set(), set()))
        for nxt in sorted({_unit_for(r, units) for r in reached} | set(local)):
            if nxt and nxt not in seen:
                seen[nxt] = u
                todo.append(nxt)
    return seen


def path_to(seen: dict, unit: str) -> list:
    out = [unit]
    while seen.get(out[-1]):
        out.append(seen[out[-1]])
    return out[::-1]


def job_starters(units: dict) -> set:
    """Every module-level ``start``/``start_*`` that starts a thread or a job, and the plan
    engine's run (C3683)."""
    out = set()
    for u, (reached, _local) in units.items():
        name = u.rpartition(".")[2]
        if not (name == "start" or name.startswith("start_")):
            continue
        if any(r.endswith(".Thread") or r == "modules.nsot.capture_job.start"
               for r in reached):
            out.add(u)
    if "modules.plan_engine.run" in units:
        out.add("modules.plan_engine.run")
    return out


def gated_views(app, kinds=("approve", "confirm")) -> set:
    """The views of every route the gate table marks one of *kinds*, dotted."""
    import inspect

    from modules import route_gates as G

    out = set()
    for endpoint, gate in G.GATES.items():
        if gate.kind not in kinds:
            continue
        view = app.view_functions.get(endpoint)
        if view is not None:
            view = inspect.unwrap(view)
            out.add(f"{view.__module__}.{view.__name__}")
    return out


def findings(seen: dict, population) -> list:
    return sorted(" -> ".join(path_to(seen, u)) for u in seen if u in set(population))


@pytest.fixture(scope="module")
def world():
    import app as A
    files = product_files()
    units = graph(files)
    start = entries(units, files)
    return {"app": A.app, "units": units, "entries": start, "seen": reach(units, start)}


class TestThePopulations:
    def test_the_graph_and_its_entries_have_their_floors(self, world):
        assert len(world["units"]) >= UNITS_AT_LEAST, len(world["units"])
        assert len(world["entries"]) >= ENTRIES_AT_LEAST, world["entries"]
        # The read families' executors are entries (the loop calls them through the family).
        assert {"modules.ai.router_reads.run", "modules.ai.fixit_reads.run"} <= set(
            world["entries"]), world["entries"]
        # The reach is real: an answer's own path through the door, the incident's record,
        # the catalog's preview and the reads engine is in it (measured 2026-11-14: about 1,600
        # units of 10,500).
        seen = world["seen"]
        assert len(seen) >= REACH_AT_LEAST, len(seen)
        for one in ("modules.ai.fix_proposal.for_incident",
                    "modules.fixit.incident.record_proposal", "modules.heal.catalog.preview",
                    "modules.nsot.reads.run", "modules.ai.calls.record_use"):
            assert one in seen, one
        for one in ("modules.ai.fixit_troubleshoot.troubleshoot",
                    "modules.ai.heal_analysis.analyse", "modules.ai.explain.explain"):
            assert one in world["entries"] or any(
                e.startswith(one.rpartition(".")[0] + ".") for e in world["entries"]), one

    def test_every_named_writer_is_a_unit_of_the_product(self, world):
        for name in SETTINGS + SECRETS + NOTIFY + TEMPLATES + APPROVALS:
            assert name in world["units"], name

    def test_the_job_starters_are_derived_and_hold_the_three_measured(self, world):
        found = job_starters(world["units"])
        assert {"modules.nsot.capture_job.start", "modules.deploy_job.start",
                "modules.deploy_job.start_restore"} <= found, sorted(found)
        assert len(found) >= 6, sorted(found)

    def test_the_gated_views_are_derived_from_the_gate_table(self, world):
        views = gated_views(world["app"])
        assert len(views) >= 20, len(views)
        assert all(v in world["units"] for v in views), sorted(v for v in views
                                                             if v not in world["units"])


class TestNoAnswerReaches:
    """From every unit that asks a model, nothing reachable writes."""

    def test_no_settings_write(self, world):
        assert findings(world["seen"], SETTINGS) == []

    def test_no_secret_write(self, world):
        assert findings(world["seen"], SECRETS) == []

    def test_no_notification_or_template_approval_write(self, world):
        assert findings(world["seen"], NOTIFY + TEMPLATES) == []

    def test_no_approval_and_no_confirm(self, world):
        assert findings(world["seen"], APPROVALS + tuple(gated_views(world["app"]))) == []

    def test_no_job_is_started(self, world):
        assert findings(world["seen"], job_starters(world["units"])) == []


PLANTED = {
    "a settings write": ("from modules.settings_schema import write_settings\n"
                         "from modules.ai import gateway\n\n"
                         "def act(answer):\n    gateway.ask('x')\n"
                         "    write_settings({'heal_mode': answer})\n", SETTINGS),
    "through a helper": ("from modules.ai import gateway\n\n"
                         "def _apply(v):\n    from modules import list_settings\n"
                         "    list_settings.write('Default', v)\n\n"
                         "def act(answer):\n    gateway.ask('x')\n    _apply(answer)\n",
                         SETTINGS),
    "a secret": ("import modules.secrets_store as S\nfrom modules.ai import gateway\n\n"
                 "def act(answer):\n    gateway.ask('x')\n    S.set_secret('k', answer)\n",
                 SECRETS),
    "a credential": ("from modules import credentials\nfrom modules.ai import read_loop\n\n"
                     "def act(a):\n    read_loop.run(a)\n    credentials.save_profile('p', a)\n",
                     SECRETS),
    "an approval": ("from modules import approval_queue as Q\nfrom modules.ai import gateway\n\n"
                    "def act(a):\n    gateway.ask('x')\n    Q.mark_done(a)\n", APPROVALS),
    "a template approval": ("from modules.nsot.approval import approve\n"
                            "from modules.ai import gateway\n\n"
                            "def act(a):\n    gateway.ask('x')\n    approve('r', 't', [])\n",
                            TEMPLATES),
    "a job": ("from modules import deploy_job\nfrom modules.ai import gateway\n\n"
              "def act(a):\n    gateway.ask('x')\n    deploy_job.start('Default', [], {}, {})\n",
              "starters"),
}


@pytest.mark.parametrize("writer", SETTINGS + SECRETS + NOTIFY + TEMPLATES + APPROVALS)
def test_each_named_writer_is_held_by_its_own_name(world, writer):
    """Each writer of the populations, called by a planted answer handler, is found as itself:
    a path ending at that writer (so no writer is held only through another one under it)."""
    module, _, name = writer.rpartition(".")
    files = dict(product_files())
    files["modules/ai/planted_fixer.py"] = (
        f"from {module} import {name} as target\nfrom modules.ai import gateway\n\n"
        "def act(a):\n    gateway.ask('x')\n    target(a)\n")
    units = graph(files)
    seen = reach(units, entries(units, files))
    found = findings(seen, (writer,))
    assert found and all(f.endswith(" -> " + writer) for f in found), found
    assert any(f.startswith("modules.ai.planted_fixer.act -> " + writer) for f in found), found


@pytest.mark.parametrize("name", sorted(PLANTED))
def test_a_planted_answer_handler_reaching_a_writer_is_found(world, name):
    """The control beside each property: a planted module under modules/ai/ that asks a model
    and then writes is found, its path named, by the same graph over the real product."""
    source, population = PLANTED[name]
    files = dict(product_files())
    files["modules/ai/planted_fixer.py"] = source
    units = graph(files)
    start = entries(units, files)
    assert "modules.ai.planted_fixer.act" in start
    seen = reach(units, start)
    pop = job_starters(units) if population == "starters" else population
    found = findings(seen, pop)
    assert found and all(f.startswith("modules.ai.planted_fixer.act") for f in found), found
    # The first writer on the path is the one the planted module calls: each is held by name.
    first = {"through a helper": "modules.list_settings.write",
             "a credential": "modules.credentials._save",
             "a template approval": "modules.nsot.approval._save",
             "a job": "modules.deploy_job.start"}.get(name)
    if first:
        assert any(f.endswith(" -> " + first) for f in found), (first, found)


def test_what_reaches_no_writer_is_not_found(world):
    """A planted answer handler that only reads settings and records its call is not found."""
    files = dict(product_files())
    files["modules/ai/planted_reader.py"] = (
        "from modules.settings_schema import get_setting\nfrom modules.ai import gateway\n\n"
        "def act(a):\n    gateway.ask('x')\n    return get_setting('heal_mode')\n")
    units = graph(files)
    seen = reach(units, ["modules.ai.planted_reader.act"])
    assert findings(seen, SETTINGS + SECRETS + NOTIFY + TEMPLATES + APPROVALS) == []


# ── C3682: a model's text never fills a secret field ─────────────────────────────────────────

#: A field a secret goes in, by its name: a password, a passphrase, a secret, a token, a key.
SECRETISH = r"(password|passphrase|secret|token|api_key|private_key|community)"


def _fields(schema, path=""):
    """``(where, field name)`` for every property of a JSON schema, at any depth (its
    properties, items, any/all/one of, and its definitions)."""
    if not isinstance(schema, dict):
        return
    for name, sub in (schema.get("properties") or {}).items():
        yield f"{path}.{name}", name
        yield from _fields(sub, f"{path}.{name}")
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            yield from _fields(schema[key], f"{path}.{key}")
    for key in ("anyOf", "allOf", "oneOf"):
        for i, sub in enumerate(schema.get(key) or []):
            yield from _fields(sub, f"{path}.{key}[{i}]")
    for name, sub in (schema.get("$defs") or {}).items():
        yield from _fields(sub, f"$defs.{name}")


def secret_fields(models) -> list:
    """Each field of *models* (``{label: a pydantic model}``) a secret would go in: one of
    `secrets_store.SECRET_KEYS`, or one named as a secret (`SECRETISH`)."""
    import re

    from modules import secrets_store

    keys, pattern = set(secrets_store.SECRET_KEYS), re.compile(SECRETISH, re.I)
    return sorted(f"{label}{where}" for label, model in models.items()
                  for where, field in _fields(model.model_json_schema())
                  if field in keys or pattern.search(field))


def test_no_ai_schema_has_a_field_a_secret_goes_in():
    """Every registered AI answer schema (`schemas.REGISTRY`): no field, at any depth, is one a
    secret goes in, so a model's answer has nowhere to type one, and nothing filled from an
    answer can carry one into a secret field (C3682)."""
    from modules.ai import schemas

    assert len(schemas.REGISTRY) >= 20, len(schemas.REGISTRY)
    assert secret_fields({f"{n}.v{v}": m for (n, v), m in schemas.REGISTRY.items()}) == []


def test_no_catalog_operation_or_plan_takes_a_secret():
    """What an answer may fill: the catalog's operations' parameters (`heal.catalog.CATALOG`)
    and the plan engine's steps and plans (`plan_engine.STEP_KINDS`, `PLANS`, the forms it fills
    from an answer): none is a secret's, so a pre-filled form leaves every secret empty."""
    import re

    from modules import plan_engine
    from modules.heal import catalog

    pattern, names = re.compile(SECRETISH, re.I), []
    for key, op in catalog.CATALOG.items():
        names += [(f"catalog {key}", p.name) for p in op.params]
    for key, kind in plan_engine.STEP_KINDS.items():
        names += [(f"step {key}", p.name) for p in kind.params]
    for key, plan in plan_engine.PLANS.items():
        names += [(f"plan {key}", p.name) for p in plan.params]
    assert len(names) >= 10, names
    assert [n for n in names if pattern.search(n[1])] == []


def test_the_secret_field_scan_finds_a_planted_one():
    """The control: a planted answer schema with a secret field two levels down, and one named
    by a secret's settings key, are both found."""
    from typing import Optional

    from modules import secrets_store
    from modules.ai.schemas import StrictModel

    class Inner(StrictModel):
        enable_secret: Optional[str]

    class Planted(StrictModel):
        operation: str
        params: list[Inner]

    key = sorted(secrets_store.SECRET_KEYS)[0]
    Keyed = type("Keyed", (StrictModel,), {"__annotations__": {key: str}})
    found = secret_fields({"planted": Planted, "keyed": Keyed})
    assert any(f.endswith("enable_secret") for f in found), found
    assert any(f.endswith(key) for f in found), found
