"""C239: every render of a device goes through ONE template resolver,
`templates_repo.render_source()`, the device's bound template in the
network's own library.

Measured by editing the LIBRARY's IOS-XE template (a real global line r2's
real config does not carry, `ip tcp synwait-time 12`) and asking each path
that renders r2: the deploy plan, the editor's and bulk intent's renderer
(`routes.templates.artifact_for`), `intent_match`, restore validation, and
seed. Before the fix only the deploy plan saw the edit. And a scan: every
render call in the program passes a `template_root`, or is named here with why.
"""

import ast
import os

import pytest

from tests.test_capture import R2, build_capture_lab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = "ip tcp synwait-time 12"


@pytest.fixture
def lab(monkeypatch, tmp_path):
    from modules.nsot import approval, templates_repo

    monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
    lab = build_capture_lab(monkeypatch, tmp_path)
    path = os.path.join(templates_repo.templates_dir(lab["repo"]), "cisco_iosxe", "base.j2")
    text = open(path, encoding="utf-8").read()
    assert MARK not in open(R2, encoding="utf-8").read()                   # the case is reachable
    first, rest = text.split("\n", 1)
    open(path, "w", encoding="utf-8").write(f"{first}\n{MARK}\n{rest}")    # after the import line
    return lab


class TestEveryPathRendersTheLibrary:
    def test_the_resolver_names_the_library(self, lab):
        from modules.nsot import templates_repo

        src = templates_repo.render_source(lab["repo"], "r2", "cisco_iosxe")
        assert src["from"] == "library" and src["template"] == "cisco_iosxe/base.j2"
        assert src["root"] == templates_repo.templates_dir(lab["repo"])

    def test_the_deploy_plan(self, lab):
        import routes.deploy as rd

        (artifact, captured, _d), err = rd._artifact_for("Lab", "r2")
        assert not err and MARK in rd._current_program(artifact, captured)

    def test_the_editor_and_bulk_intents_renderer(self, lab):
        from modules.nsot import hostvars
        from routes.templates import artifact_for

        intent = hostvars.read_committed(lab["repo"], "r2")
        art = artifact_for("r2", open(R2, encoding="utf-8").read(), lab["repo"], "cisco_iosxe",
                           "cisco_iosxe/base.j2", host_vars=hostvars.hydrate_secrets(intent, "r2", "Lab"))
        assert MARK in art.rendered_masked

    def test_intent_match(self, lab):
        from modules.nsot.intent_match import intent_match

        got = intent_match(lab["repo"], "Lab", "r2", open(R2, encoding="utf-8").read(), "cisco_iosxe")
        assert got["state"] == "differs" and any(MARK in l for l in got["lines"]), got

    def test_restore_validation(self, lab):
        from modules.nsot import hostvars
        from modules.nsot.restore import validate_restored_intent

        intent = hostvars.read_committed(lab["repo"], "r2")
        gaps = validate_restored_intent(lab["repo"], "r2", intent, open(R2, encoding="utf-8").read(),
                                        "cisco_iosxe", ref="HEAD")
        assert any("does not round-trip" in g or MARK in g for g in gaps), gaps

    def test_the_built_in_seeds_only_where_the_library_lacks_the_template(self, tmp_path):
        from modules.nsot import roundtrip, templates_repo

        src = templates_repo.render_source(str(tmp_path / "config_repo"), "r2", "cisco_iosxe")
        assert src["from"] == "built-in" and src["root"] == roundtrip.TEMPLATE_ROOT
        assert "is not in this network's template library" in src["why"]


#: A render call allowed without its own `template_root`, and why.
EXEMPT = {
    # bulk intent's injected renderer is `routes.templatize`'s, which calls
    # artifact_for (itself resolved); this is the call of the injected one.
    ("modules/nsot/bulk_intent.py", "plan"),
}
RENDERERS = {"build_artifact", "render", "validate_device", "render_for_deploy"}


def _calls():
    """(file, enclosing function, callee, has template_root) for every call."""
    out = []
    for rel in ["app.py"] + [os.path.join(d, f) for d in ("modules", "modules/nsot", "routes")
                             for f in sorted(os.listdir(os.path.join(ROOT, d))) if f.endswith(".py")]:
        tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ""
                if name not in RENDERERS or (name == "render" and owner not in ("roundtrip", "")):
                    continue
                if name == "render" and owner == "" and rel not in ("modules/nsot/roundtrip.py",
                                                                     "modules/nsot/bulk_intent.py"):
                    continue                 # an unrelated local `render`
                kws = {k.arg for k in node.keywords}
                out.append((rel, fn.name, name, "template_root" in kws or None in kws))
    return out


def test_every_render_takes_its_template_from_the_resolver():
    calls = _calls()
    assert len(calls) >= 12, calls                                   # the floor: the renders exist
    bad = sorted({(rel, fn, name) for rel, fn, name, ok in calls
                  if not ok and (rel, fn) not in EXEMPT})
    assert bad == [], f"renders with no template_root (the built-in seeds by default): {bad}"
    used = {(rel, fn) for rel, fn, _n, ok in calls if not ok}
    assert set(EXEMPT) <= used, f"an exemption nothing needs is a hole: {sorted(set(EXEMPT) - used)}"


def test_the_resolver_is_called_by_each_render_path():
    import inspect

    import modules.nsot.intent_match as im
    import modules.nsot.restore as rs
    import modules.nsot.seed as sd
    import routes.deploy as rd
    import routes.templates as rt
    import routes.templatize as tz

    for fn in (rd._artifact_for, rt.artifact_for, im.intent_match, rs.validate_restored_intent,
               sd.entry_for):
        assert "render_source(" in inspect.getsource(fn), fn.__qualname__
    assert "render_source(" in inspect.getsource(tz)
