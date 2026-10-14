"""The functions and classes a Python source defines, found by parsing: ONE walker for every
check that asks "what does this module define" (tests/test_no_duplicate_definitions.py, which
refuses a name defined twice in one scope, and scripts/nmas_coverage.py, which counts the
functions a test reaches). Two walkers would be two answers to one question.

The counting rules (docs/TESTING.md, "How function coverage is counted"; each pinned by
tests/test_nmas_coverage.py):

- **Counted:** every `def` and `async def` at module level or in a class body (nested classes
  too), under any `if`, `try`, `with` or `for` at that level as well. A method is named
  `Class.method`.
- **Nested functions and closures** are not listed on their own: they are part of the function
  that encloses them, and run only when it does. Their lines count toward it.
- **Lambdas** are expressions, never counted.
- **Listed but not counted, each with its reason** (`Definition.excluded`):
  - a property or its setter, getter or deleter: an accessor, read like an attribute;
  - an `@overload` signature: a typing declaration, whose body never runs;
  - an `@abstractmethod`, or any method of a `Protocol` class: a declaration;
  - a stub, whose body is only a docstring, `pass`, `...` or `raise NotImplementedError`;
  - a function under `if TYPE_CHECKING:`, which never runs;
  - a function under `if __name__ == "__main__":`, which an import never defines.
"""
import ast
from dataclasses import dataclass, field

ACCESSORS = ("setter", "getter", "deleter")

#: Why a definition is listed but not counted, by the rule that excludes it.
WHY = {
    "property": "a property or its accessor: read like an attribute",
    "overload": "an @overload signature: a typing declaration, its body never runs",
    "abstract": "an @abstractmethod: a declaration",
    "protocol": "a Protocol class's method: a declaration",
    "stub": "a stub (docstring, pass, ... or raise NotImplementedError only): no behaviour",
    "type_checking": "under `if TYPE_CHECKING:`: never runs",
    "main": "under `if __name__ == \"__main__\":`: an import never defines it",
}


@dataclass(frozen=True)
class Definition:
    """One definition. `body_lines` are the lines of its body after the docstring, nested
    functions included: a function ran when any of them did. `direct` is True when it sits
    straight in a module or class body (not under an `if`, `try` and so on): the scope the
    duplicate-definition check compares."""
    qualname: str
    name: str
    kind: str                     # "function", "method" or "class"
    lineno: int
    end_lineno: int
    scope: str                    # "" for the module, "Class." for a class body
    direct: bool
    excluded: str = ""            # a WHY key, or "" when counted
    body_lines: tuple = field(default=(), compare=False)
    #: `@<its own name>.setter` (or getter, deleter): the one repeat a scope allows.
    accessor: bool = False

    @property
    def counted(self) -> bool:
        """Whether function coverage counts it (a function or method, not excluded)."""
        return self.kind != "class" and not self.excluded


def _decorator_names(node) -> set:
    names = set()
    for d in node.decorator_list:
        d = d.func if isinstance(d, ast.Call) else d
        if isinstance(d, ast.Name):
            names.add(d.id)
        elif isinstance(d, ast.Attribute):
            names.add(d.attr)
    return names


def _is_accessor(node, name: str = "") -> bool:
    """`@x.setter` (or getter, deleter); with *name*, only where x is that name."""
    return any(isinstance(d, ast.Attribute) and d.attr in ACCESSORS
               and isinstance(d.value, ast.Name) and (not name or d.value.id == name)
               for d in node.decorator_list)


def _docstring_len(body) -> int:
    return 1 if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                 and isinstance(body[0].value.value, str)) else 0


def _is_stub(body) -> bool:
    rest = body[_docstring_len(body):]
    if not rest:
        return True
    for stmt in rest:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                and stmt.value.value is Ellipsis:
            continue
        if isinstance(stmt, ast.Raise):
            exc = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                continue
        return False
    return True


def _body_lines(node) -> tuple:
    body = node.body[_docstring_len(node.body):]
    lines = set()
    for stmt in body:
        lines.update(range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1))
    return tuple(sorted(lines))


def _guard(test) -> str:
    """The exclusion an `if` test puts on what it holds: TYPE_CHECKING or __main__."""
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return "type_checking"
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return "type_checking"
    if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
            and test.left.id == "__name__" and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"):
        return "main"
    return ""


def _is_protocol(cls) -> bool:
    return any((isinstance(b, ast.Name) and b.id == "Protocol")
               or (isinstance(b, ast.Attribute) and b.attr == "Protocol") for b in cls.bases)


def definitions(source: str) -> list:
    """Every definition in *source*, in source order (see the module's counting rules)."""
    tree = ast.parse(source)
    out = []

    def scan(body, scope, direct, guard, protocol):
        for node in body:
            if isinstance(node, ast.ClassDef):
                out.append(Definition(f"{scope}{node.name}", node.name, "class", node.lineno,
                                      node.end_lineno or node.lineno, scope, direct, guard))
                scan(node.body, f"{scope}{node.name}.", True, guard, _is_protocol(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = _decorator_names(node)
                excluded = (guard
                            or ("property" if names & {"property", "cached_property"}
                                or _is_accessor(node) else "")
                            or ("overload" if "overload" in names else "")
                            or ("abstract" if "abstractmethod" in names else "")
                            or ("protocol" if protocol else "")
                            or ("stub" if _is_stub(node.body) else ""))
                out.append(Definition(f"{scope}{node.name}", node.name,
                                      "method" if scope else "function", node.lineno,
                                      node.end_lineno or node.lineno, scope, direct, excluded,
                                      _body_lines(node), _is_accessor(node, node.name)))
                # Nested functions are part of this one: not scanned on their own.
            elif isinstance(node, ast.If):
                inner = _guard(node.test) or guard
                scan(node.body, scope, False, inner, protocol)
                scan(node.orelse, scope, False, guard, protocol)
            elif isinstance(node, (ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor,
                                   ast.While)):
                for block in ("body", "orelse", "finalbody"):
                    scan(getattr(node, block, []) or [], scope, False, guard, protocol)
                for handler in getattr(node, "handlers", []) or []:
                    scan(handler.body, scope, False, guard, protocol)

    scan(tree.body, "", True, "", False)
    return out


def duplicates(source: str, label: str = "") -> list:
    """Each name defined twice in one module or class body: `label:Class.name: lines A and B`.
    Two repeats are allowed: an accessor of the same name (a property's setter) and the
    definition after `@overload` signatures, which is the one that runs."""
    seen, overloaded, found = {}, set(), []
    for d in definitions(source):
        if not d.direct:
            continue
        key = (d.scope, d.name)
        if key in seen and not d.accessor and key not in overloaded:
            found.append(f"{label}:{d.scope}{d.name}: lines {seen[key]} and {d.lineno}")
        seen[key] = d.lineno
        if d.excluded == "overload":
            overloaded.add(key)
        else:
            overloaded.discard(key)
    return found
