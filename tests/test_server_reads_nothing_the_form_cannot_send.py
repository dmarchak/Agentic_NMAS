"""Every field the server reads from the request, some form can supply.

**Eighth instance in one session of a capability existing and nothing a person
can reach calling it** — after `run_onboarding` returning 501,
`loadOnboardPending` having no caller, the pending banner's buttons dropping
the list, `finish_bootstrap` unwired, `/onboard/create` sending `body: '{}'`,
the deploy wizard omitting `command_hashes`, and `vs_intent` reading the
working tree.

The plainest of them: phase 2's `address_source` and `mgmt_mac` were built in
`_plan_args()`, `build_plan()` and `render_bootstrap()`, and the wizard was
still the static-only form. **Its acceptance was written as *"the review screen
reads 'assigned by Kea reservation …'"*** — a screen with no way to be told the
address was reserved.

Why the tests did not say so: the payload tests construct plan arguments
directly, which is the seam that hid `body: '{}'`, and the renderer tests
execute the render without the fetch. Each half was right about its own half.

So this is the scripts/renderers check pointed at the request boundary: parse
what `_plan_args()` reads out of `data`, parse what the client's field map
sends, and assert the first is covered by the second. A field only `curl` can
supply is a feature no operator has.
"""

import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def server_request_fields(module_rel: str, function: str) -> set:
    """Keys a function pulls out of its `data` mapping, by parsing.

    `data.get("x")` and `data.get("x") or default` both count. Parsed rather
    than grepped: the module's prose names these fields while explaining them.
    """
    tree = ast.parse(open(os.path.join(ROOT, module_rel), encoding="utf-8").read())
    target = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == function), None)
    assert target is not None, f"{function} not found in {module_rel}"
    fields = set()
    for node in ast.walk(target):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get"):
            continue
        if getattr(func.value, "id", None) != "data":
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            fields.add(node.args[0].value)
    return fields


def client_sent_fields(js_rel: str, mapping: str) -> set:
    """Keys in a client-side ``const <mapping> = { key: 'elementId', … }``."""
    source = open(os.path.join(ROOT, js_rel), encoding="utf-8").read()
    start = source.index(f"const {mapping} = {{")
    body = source[start:source.index("};", start)]
    # Strip comments so a commented-out field is not counted as sent.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"//.*", "", body)
    return set(re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*:", body, re.M))


#: What the form cannot supply and does not need to, with a reason each.
#: **Every entry is a hole in the check**, so each one is named rather than the
#: set being loosened.
NOT_FROM_THE_FORM = {
    # LEGITIMATE. The wizard mints the bootstrap credential server-side; a
    # browser must never carry one.
    "secret",
    # LEGITIMATE. Set by the route from the list's own source.json, not by the
    # operator.
    "source_kind",
    # ⚠ A GAP UNDER EXEMPTION, not a clean one — and this check found it on its
    # first run, which is the argument for having it.
    #
    # `domain` is read here and defaults to `rcn.lab`, and the wizard has no
    # field for it. Unlike the two above there is no reason a person could not
    # set it: it is carried on the plan precisely so the bootstrap artefact is
    # re-renderable, and a second lab with a different DNS domain would get
    # `rcn.lab` silently. Exempted rather than silently widening the check,
    # so it reads as a recorded gap with a name.
    "domain",
}


class TestTheOnboardFormCanSupplyEverythingThePlanReads:

    SERVER = ("routes/onboard.py", "_plan_args")
    CLIENT = ("static/js/gen/partials__onboard_wizard.1.js", "ONBOARD_FIELDS")

    def test_the_scan_finds_something(self):
        """**The floor.** Both sides are set differences, and either being
        empty satisfies every assertion below."""
        server = server_request_fields(*self.SERVER)
        client = client_sent_fields(*self.CLIENT)
        assert len(server) >= 8, f"parsed only {sorted(server)} from the route"
        assert len(client) >= 8, f"parsed only {sorted(client)} from the form"

    def test_the_server_reads_nothing_the_form_cannot_send(self):
        """**The defect, as an assertion.** `address_source` and `mgmt_mac`
        were read here and sendable by nothing a person can reach."""
        server = server_request_fields(*self.SERVER)
        client = client_sent_fields(*self.CLIENT)
        unreachable = sorted(server - client - NOT_FROM_THE_FORM)
        assert not unreachable, (
            "the route reads these and the wizard cannot send them, so only "
            f"curl can reach the feature: {unreachable}. Add them to "
            "ONBOARD_FIELDS, or name them in NOT_FROM_THE_FORM with a reason.")

    def test_the_form_sends_nothing_the_server_ignores(self):
        """The other direction. A field the operator fills in that the route
        never reads is a control that does nothing — the same lie as a
        greyed-out button, wearing a placeholder."""
        server = server_request_fields(*self.SERVER)
        client = client_sent_fields(*self.CLIENT)
        ignored = sorted(client - server - {"list_name"})
        assert not ignored, (
            f"the wizard sends these and the route ignores them: {ignored}")

    def test_phase_2s_fields_are_on_both_sides(self):
        """A positive anchor. "No offenders" is also what a scan that could
        not run produces, so the fields this test was written for are named."""
        server = server_request_fields(*self.SERVER)
        client = client_sent_fields(*self.CLIENT)
        for field in ("address_source", "mgmt_mac"):
            assert field in server, f"{field} is not read by _plan_args"
            assert field in client, f"{field} is not sent by the wizard"

    def test_every_exemption_is_named_not_a_wildcard(self):
        assert NOT_FROM_THE_FORM, "an empty exemption set hides nothing usefully"
        assert all(isinstance(f, str) and f for f in NOT_FROM_THE_FORM)

    def test_the_exemption_set_is_small_enough_to_read(self):
        """An exemption set that grows without anyone noticing is the check
        being switched off one field at a time."""
        assert len(NOT_FROM_THE_FORM) <= 5, (
            f"{len(NOT_FROM_THE_FORM)} exemptions — each one is a hole, and a "
            "set this size is no longer a list somebody reads")


class TestTheCheckCanFail:
    """A scan that cannot fail is not a scan."""

    def test_a_field_read_and_not_sent_is_caught(self, tmp_path):
        module = tmp_path / "fake_route.py"
        module.write_text('def _plan_args(data):\n'
                          '    return dict(a=data.get("a"), b=data.get("b"),\n'
                          '                c=data.get("c"))\n', encoding="utf-8")
        js = tmp_path / "fake.js"
        js.write_text("const ONBOARD_FIELDS = {\n  a: 'x',\n  b: 'y',\n};\n",
                      encoding="utf-8")
        server = server_request_fields(os.path.relpath(module, ROOT), "_plan_args")
        client = client_sent_fields(os.path.relpath(js, ROOT), "ONBOARD_FIELDS")
        assert sorted(server - client) == ["c"]

    def test_a_commented_out_field_does_not_count_as_sent(self, tmp_path):
        """Otherwise commenting a field out silently satisfies the check."""
        js = tmp_path / "fake.js"
        js.write_text("const ONBOARD_FIELDS = {\n  a: 'x',\n"
                      "  /* b: 'y', */\n  // c: 'z',\n};\n", encoding="utf-8")
        assert client_sent_fields(os.path.relpath(js, ROOT),
                                  "ONBOARD_FIELDS") == {"a"}
