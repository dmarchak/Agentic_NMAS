"""Ask the parsed structure, not the source text. (Not a test module.)

`inspect.getsource()` returns the docstring and the comments along with the
code, so a test that greps it is searching the *explanation* of the code
alongside the code. Four false positives in one stage, each passing while the
thing it claimed to check was broken:

* `source.count("save_host_vars(") == 1` matched the **comment** saying it
  commits once -- while the script it guarded could not run at all;
* `"key.key" not in source` matched the **docstring paragraph** explaining
  why that module must never read it;
* `source.count("save_golden(") == 1` matched a **docstring** naming it;
* `"slug == list_name" not in source` matched the **comment** describing the
  very defect the test was written to confirm was fixed.

The better the code explains itself, the more prose there is to trip over --
so the discipline that makes this codebase readable is the same one that
makes text-matching tests unreliable. These helpers exist so the fix is one
import rather than a decision each time.

Text matching is still right when the claim IS about prose: the tab
descriptions are checked as rendered text on purpose.
"""

import ast
import inspect
import textwrap


def tree_of(func):
    """The function's AST, dedented so a method parses."""
    return ast.parse(textwrap.dedent(inspect.getsource(func)))


def calls_in(func, name) -> int:
    """How many times *func* calls *name*. Comments and docstrings cannot
    contribute, because they are not `ast.Call` nodes."""
    return sum(1 for node in ast.walk(tree_of(func))
               if isinstance(node, ast.Call)
               and getattr(node.func, "attr",
                           getattr(node.func, "id", "")) == name)


def code_of(func) -> str:
    """The function's source with comments and docstrings removed.

    For the cases a call count cannot express -- an operator, an attribute
    access, a comparison. `ast.unparse` drops comments on its own; the
    docstring is stripped explicitly because it survives as a statement.
    """
    tree = tree_of(func)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)
