"""A preview field the plan did not read says WHY, never "?" (the operator, 2026-10-03: a
preview drew "account ? (privilege ?)" when its preflight stopped before reading, which looks
like a value).

- By parsing `modules/preview_confirm.py`: every operand (a dict with "name" and "value") whose
  value expression can produce a bare "?" is found; there are none. A floor on the operands
  found, and a planted one is found.
- Rotate's preview with a plan that stopped before reading draws each unread operand as
  "not read: <the plan's own error>".
"""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "modules", "preview_confirm.py")


def _operands(tree) -> list:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "name" in keys and "value" in keys:
                out.append(node.values[keys.index("value")])
    return out


def _bare_question_marks(tree) -> list:
    bad = []
    for value in _operands(tree):
        for n in ast.walk(value):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip() == "?":
                bad.append(n.lineno)
    return bad


def test_no_operand_can_draw_a_bare_question_mark():
    tree = ast.parse(open(SOURCE, encoding="utf-8").read())
    assert len(_operands(tree)) >= 60, len(_operands(tree))
    assert _bare_question_marks(tree) == [], "an operand value falls back to '?': say why"


def test_a_planted_one_is_found():
    planted = 'x = [{"name": "account", "value": plan.get("username") or "?"}]'
    assert _bare_question_marks(ast.parse(planted)) == [1]


def test_rotates_unread_operands_say_why():
    from modules.preview_confirm import rotate_preview
    plan = {"ok": False, "device": "r2", "error": "the Oxidized helper is not installed"}
    p = rotate_preview(plan, busy="", request=None)
    ops = {o["name"]: o["value"] for o in p["targets"][0]["operands"]}
    for name in ("list", "management address", "account", "entry kind",
                 "its line now (read live, masked)"):
        assert ops[name] == "not read: the Oxidized helper is not installed", (name, ops[name])
    assert "?" not in " ".join(str(v) for v in ops.values())
