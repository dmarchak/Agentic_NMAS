"""Nothing in Mercury reads the read loop's answer to act (board H, part H26; docs/HEAL_TO_INTENT.md
19.5: "Nothing in the heal loop reads the steps or the answer. Section 12's mechanised test is
extended to the loop's module"; section 12: the analysis is advisory, no fix is ever chosen or
run from AI text).

tests/test_heal_analysis_never_read.py holds `modules/heal/` to no reference to `modules.ai` or
to an analysis. This scan holds the WHOLE product (every Python module under `modules/`,
`routes/` and `scripts/`, and the root's: a floor on the population, so a scan of nothing never
passes) to an exact list of who may reach what the loop produced, each one a drawer, the
notifier or the loop's own writer, none an actor:

- **the loop** (`modules.ai.read_loop`): the read family it is declared over and the one feature
  asked through it (`KNOWN_LOOP`);
- **its answer and its store** (`modules.ai.heal_analysis`: the analysis, its kept rows): the
  notifier and the pages that draw it (`KNOWN_ANALYSIS`);
- **the send log** (`modules.ai.read_log`): the loop that writes it and History, which draws it
  (`KNOWN_LOG`);
- **the step log's advisory step** (`steplog.advisories` and `steplog.record_advisory`, by
  attribute or by name): History reads it, the analysis writes it (`KNOWN_STEP`); and in
  `modules/heal/` no code but the step log's own names the row (``"advisory"``), so no reader
  of the heal loop can pick it out of the rows it reads.

Each list is exact: an entry no longer found fails, so it only shrinks, and any new reader is a
failure to look at, never a pass. Planted cases show each kind of reference is found.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The product's Python modules, at least this many (461 under modules/ and routes/ on
#: 2026-11-07, 15 under scripts/, and two at the root).
FLOOR = 400
LOOP = "modules.ai.read_loop"
ANALYSIS = "modules.ai.heal_analysis"
LOG = "modules.ai.read_log"
STEPLOG = "modules.heal.steplog"
STEP_NAMES = ("advisories", "record_advisory")
#: Who may import the loop: its router read family, and the one feature asked through it.
KNOWN_LOOP = {"modules/ai/router_reads.py", "modules/ai/heal_analysis.py", "modules/ai/sdn_analyst_tools.py"}
#: Who may import the analysis (its answer, its kept rows): the notifier and the pages.
KNOWN_ANALYSIS = {"modules/heal_notice.py", "modules/heal_page.py", "modules/attention.py",
                  "routes/v2.py"}
#: Who may import the send log: the loop that writes it, and History, which draws it.
KNOWN_LOG = {"modules/ai/read_loop.py", "modules/history_sources.py"}
#: Who may reach the step log's advisory step, and how: History and the incident page read it
#: (the incident page's AI troubleshooting frame draws the kept advisory, 2026-11-12), the
#: analysis writes it.
KNOWN_STEP = {("modules/history_sources.py", "advisories"),
              ("modules/incident_page.py", "advisories"),
              ("modules/ai/heal_analysis.py", "record_advisory")}
#: The one module of `modules/heal/` whose code names the advisory row: the step log's own.
ROW_NAMER = "modules/heal/steplog.py"


def _files() -> dict:
    from tests.source_index import tracked

    out = {}
    for p in tracked("modules", "routes", "scripts", suffix=".py"):
        out[os.path.relpath(p, ROOT)] = p
    for p in tracked(ROOT, suffix=".py", recursive=False):
        out[os.path.relpath(p, ROOT)] = p
    return out


def _docstrings(tree) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value,
                                                                     ast.Constant):
                out.add(id(body[0].value))
    return out


def references(source: str) -> dict:
    """What *source* reaches, parsed (never matched as text): ``{"imports": {full dotted
    names}, "step": {the advisory step's names it reaches}, "row": [lines naming the
    advisory row in code]}``. An ``import a.b`` is ``a.b``; a ``from a import b`` is ``a.b``
    and ``a``; the step is reached by an attribute of a name bound to the step log, or by a
    name imported from it."""
    tree = ast.parse(source)
    docs = _docstrings(tree)
    imports, step, row, bound = set(), set(), [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name)
                if a.name == STEPLOG:
                    bound.add(a.asname or a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                full = f"{node.module}.{a.name}"
                imports.update({full, node.module})
                if full == STEPLOG:
                    bound.add(a.asname or a.name)
                if node.module == STEPLOG and a.name in STEP_NAMES:
                    step.add(a.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in STEP_NAMES:
            base = node.value
            name = (base.id if isinstance(base, ast.Name) else
                    f"{ast.unparse(base)}" if isinstance(base, ast.Attribute) else "")
            if name in bound or name == STEPLOG:
                step.add(node.attr)
        elif isinstance(node, ast.Constant) and node.value == "advisory" \
                and id(node) not in docs:
            row.append(node.lineno)
    return {"imports": imports, "step": step, "row": row}


def found(files: dict) -> dict:
    """``{"loop", "analysis", "log", "step", "row"}``: who reaches each, from *files*
    (``{path: source}``)."""
    out = {"loop": set(), "analysis": set(), "log": set(), "step": set(), "row": set()}
    for path, source in files.items():
        got = references(source)
        imp = got["imports"]
        if any(i == LOOP or i.startswith(LOOP + ".") for i in imp):
            out["loop"].add(path)
        if any(i == ANALYSIS or i.startswith(ANALYSIS + ".") for i in imp):
            out["analysis"].add(path)
        if any(i == LOG or i.startswith(LOG + ".") for i in imp):
            out["log"].add(path)
        out["step"] |= {(path, n) for n in got["step"]}
        if path.startswith("modules/heal/") and got["row"]:
            out["row"].add(path)
    return out


def _sources() -> dict:
    out = {}
    for rel, p in _files().items():
        with open(p, encoding="utf-8") as fh:
            out[rel] = fh.read()
    return out


def test_the_scan_reads_the_whole_product():
    files = _files()
    assert len(files) >= FLOOR, len(files)
    assert "modules/ai/read_loop.py" in files and "modules/heal/act.py" in files


def test_only_the_known_reach_what_the_loop_produced_and_each_list_is_exact():
    got = found(_sources())
    assert got["loop"] == KNOWN_LOOP, got["loop"]
    assert got["analysis"] == KNOWN_ANALYSIS, got["analysis"]
    assert got["log"] == KNOWN_LOG, got["log"]
    assert got["step"] == KNOWN_STEP, got["step"]
    assert got["row"] == {ROW_NAMER}, got["row"]


def test_no_reader_is_in_the_heal_loop_or_a_path_that_changes_a_device():
    # The lists' members draw, notify or write the loop's own records: none is the heal loop,
    # the deploy pipeline or an operation that sends to a device.
    acting = ("modules/heal/", "modules/nsot/", "modules/pipeline", "pipeline.py",
              "modules/device_actions", "modules/sdn/")
    members = KNOWN_LOOP | KNOWN_ANALYSIS | KNOWN_LOG | {p for p, _n in KNOWN_STEP}
    assert not [m for m in members if m.startswith(acting)], members


def test_each_planted_reference_is_found():
    planted = {
        "loop": "from modules.ai import read_loop as RL\n",
        "loop:from": "from modules.ai.read_loop import run\n",
        "analysis": "def f():\n    from modules.ai import heal_analysis\n"
                    "    return heal_analysis.latest('n', 'i')\n",
        "log": "import modules.ai.read_log\n",
        "step:attr": "from modules.heal import steplog\n"
                     "def f():\n    return steplog.advisories('n')\n",
        "step:alias": "from modules.heal import steplog as SL\n"
                      "def f():\n    return SL.advisories('n')['by_incident']\n",
        "step:name": "from modules.heal.steplog import advisories\n",
        "step:module": "import modules.heal.steplog\n"
                       "def f():\n    return modules.heal.steplog.advisories('n')\n",
        "row": "def f(rows):\n    return [r for r in rows if r['row'] == 'advisory']\n",
    }
    for key, src in planted.items():
        got = found({"modules/heal/decide.py": src})
        kind = key.split(":")[0]
        assert got[kind], (key, got)
    # A docstring may say the word, and a deploy plan's own "advisories" is no step log's.
    quiet = {"modules/heal/decide.py": '"""Never reads the advisory step."""\n',
             "modules/preview_confirm.py": "def f(plan):\n    return plan.get('advisories')\n"
                                           "def g(p):\n    return p.advisories\n"}
    assert found(quiet) == {"loop": set(), "analysis": set(), "log": set(), "step": set(),
                            "row": set()}


def test_the_step_is_never_one_of_an_entrys_steps():
    """The step log folds every row of an incident into its entry but the advisory one, which
    no reader of the heal loop then meets (`steplog._fold`)."""
    from modules.heal import steplog
    rows = [{"row": "decision", "decision": "d1", "incident": "i1", "device": "r1",
             "steps": [{"step": "decide", "result": "cant_fix", "words": "w"}],
             "outcome": "cant_fix", "at": "2026-11-07T00:00:00Z", "epoch": 1.0},
            {"row": "advisory", "decision": "", "incident": "i1", "device": "r1",
             "advisory": {"words": "AI analysis: asked for 1 read; 1 run; second pass "
                                   "answered", "steps": [{"step": "pass 1"}]},
             "at": "2026-11-07T00:00:09Z", "epoch": 9.0}]
    (entry,) = steplog._fold(rows)
    assert [s["step"] for s in entry["steps"]] == ["decide"]
    assert entry["epoch"] == 1.0 and "advisory" not in entry, "its time and fields unmoved"
    assert steplog._fold(rows[:1])[0]["steps"] == entry["steps"]
