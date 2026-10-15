""""Disabled" is a state to report, not a reason to withhold.

`GET /ai/agent_log?limit=2` returned `{"entries": [], "status": {}}` with a
503 the moment AI was switched off. So disabling the agent **suppressed the
26 recorded failures and the workspace-id error that were the reason for
disabling it.** The health surface built so a dead component could not look
quiet went silent exactly when its history mattered most, and an operator
finding it disabled next month would have learned nothing.

The mechanism is worth naming, because the route was not carelessly written:
**the guard was correct for an older payload.** When `/ai/agent_log` returned
only a log, "AI is disabled" plausibly meant "nothing to say". Adding
`health` to it changed what the route carries and nobody revisited the
guard. A guard ages against its own payload.

**A read reports; an action refuses.** The agent's routes, the instance above and its
behavioural tests, left with the AI family (D15, 2026-10-14); the rule and the scan below
stay for every GET route that names a degraded state.
"""

import ast
import io
import os
import re


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Every **GET** route whose body returns something mentioning a disabled or
#: unconfigured state, classified. The default is not "fine" — a route that
#: shows up in the AST scan and is missing here fails the test below.
#:
#: The scan is deliberately broader than "refuses": it finds every GET that
#: *says something* about a degraded state, because from the AST a healthy
#: report and a refusal look alike. Deciding which it is, is the point.
#:
#: ``reports``  — carries status or accumulated history. It must survive the
#:                degraded state, because the state is *what the operator
#:                needs to see*.
#: ``fetches``  — returns a resource that genuinely does not exist when the
#:                feature is off. Refusing is correct; the refusal must still
#:                say what to do about it.
#: Empty since 2026-10-15: its last member, GET /drift/settings ("reports"), left at 7.8 (a
#: duplicate read nothing called; /drift/status reports the same switch).
CLASSIFIED: dict = {}

_STATE = re.compile(r"disabled|not configured|not_configured|unconfigured|"
                    r"no api key|not enabled", re.I)


def _gets_mentioning_a_degraded_state(paths=None):
    """GET routes that return something naming a disabled/unconfigured state: app.py's and
    every route file's, or the *paths* given."""
    found = []
    if paths is None:
        paths = [os.path.join(ROOT, "app.py")]
        routes_dir = os.path.join(ROOT, "routes")
        paths += [os.path.join(routes_dir, f) for f in sorted(os.listdir(routes_dir))
                  if f.endswith(".py")]

    for path in paths:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            rule, methods = "", set()
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "route":
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        rule = dec.args[0].value
                    for kw in dec.keywords:
                        if kw.arg == "methods":
                            methods = {e.value for e in kw.value.elts}
            if not rule or (methods and methods != {"GET"}):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and sub.value is not None:
                    if _STATE.search(ast.unparse(sub.value)):
                        found.append(rule)
                        break
    return sorted(set(found))


class TestEveryDegradedReadIsClassified:
    """The list must not grow silently, which is the only way this stays a
    check rather than a snapshot of one afternoon."""

    def test_the_scan_finds_a_planted_one(self, tmp_path):
        """A scan that cannot find anything would make the test below vacuous, and this
        project has found five controls that could not fail. The real population is empty
        since 2026-10-15 (1 since 2026-10-12, when the monitoring stack panel's per-tool card
        and the topology service's SVG left; GET /drift/settings, the last, left at 7.8), so
        the floor is a planted GET in the shape the scan reads, and a POST beside it that it
        must not count."""
        planted = tmp_path / "planted_routes.py"
        planted.write_text(
            '@bp.route("/planted/state", methods=["GET"])\n'
            "def state():\n"
            '    return {"disabled": True}\n\n\n'
            '@bp.route("/planted/write", methods=["POST"])\n'
            "def set_state():\n"
            '    return {"disabled": False}\n', encoding="utf-8")
        assert _gets_mentioning_a_degraded_state([str(planted)]) == ["/planted/state"]
        assert isinstance(_gets_mentioning_a_degraded_state(), list)

    def test_every_one_is_classified(self):
        unclassified = [r for r in _gets_mentioning_a_degraded_state() if r not in CLASSIFIED]
        assert not unclassified, (
            "a GET route names a disabled/unconfigured state in a return and "
            "is not classified in CLASSIFIED: " + str(unclassified) +
            " — decide whether it REPORTS the state or FETCHES a resource")

    def test_the_classification_names_no_ghosts(self):
        """An entry for a route that no longer short-circuits is a decision
        about nothing, and it hides the day the route changes back."""
        live = set(_gets_mentioning_a_degraded_state())
        ghosts = [r for r in CLASSIFIED if r not in live]
        assert not ghosts, (
            f"classified but no longer naming a degraded state: {ghosts} — "
            "either it was fixed (drop the entry; a behavioural test is "
            "stronger) or it was deleted")
