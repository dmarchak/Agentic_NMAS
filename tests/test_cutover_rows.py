"""docs/CUTOVER.md, the checklist for retiring today's interface, held to `app.url_map` (C630,
2026-10-10: its header said 265 routes when the map held 379, four rows named routes removed in
ba28d2b, four family counts were wrong, and about fourteen PLANNED rows had a built v2).

A row names its routes in backticks, as a person reads them: a full path (`/golden/capture/
preview`), a shorthand continuing the path before it (`/apply` after it is
`/golden/capture/apply`), or a family (`/topology/*`), a family's count in brackets after it.

1. **Every path a row names is a route**, its parameters compared by place, never by name.
2. **Every route outside the redesign** (`/v2/...`, `/update/...`) **is named by a row**: each
   is assigned to the MOST specific path that names it anywhere in the table, so a new route
   cannot arrive unlisted.
3. **A family's count is what it was assigned** (the rules a more specific path claims are that
   path's, so `/topology/*` does not count `/topology/service/*`'s).

The checks parse the doc's table rows and the map; a planted row, path and count are each found.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "CUTOVER.md")
REDESIGN = ("/v2/", "/update/")
_TOKEN = re.compile(r"`(/[^`\s]*)`(\s*\((\d+))?")


def _norm(path: str) -> str:
    """A rule's path with each parameter as ``<>``: compared by place, never by name."""
    return re.sub(r"<[^>]*>", "<>", path.rstrip("/") or "/")


def rules() -> list:
    """Every route's path, one per Flask rule (endpoint), normalised."""
    import app as A

    return [_norm(r.rule) for r in A.app.url_map.iter_rules()]


def table_rows(text: str) -> list:
    """``[(family, routes cell)]`` for every row of the legacy-routes table."""
    sect = text.split("## Legacy routes by family", 1)[1].split("\n## ", 1)[0]
    out = []
    for line in sect.splitlines():
        if not line.startswith("| ") or line.startswith("| Family") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        out.append((cells[0], cells[1]))
    return out


def tokens(text: str) -> list:
    """``[(family, path or family prefix, is_family, count or None)]``. A path that is not a
    route as written, after a full path in its cell, is a shorthand under that path's folder
    (`/apply` after `/golden/capture/preview`) when that is a route; a family is as written."""
    out = []
    for family, cell in table_rows(text):
        prev = ""
        for m in _TOKEN.finditer(cell):
            raw, count = m.group(1), m.group(3)
            is_family = raw.endswith("/*")
            path = _norm(raw[:-2] if is_family else raw)
            if not is_family and path not in _RULES_CACHE and prev:
                joined = _norm(prev.rsplit("/", 1)[0] + path)
                if joined in _RULES_CACHE:
                    path = joined
            prev = path
            out.append((family, path, is_family, int(count) if count else None))
    return out


_RULES_CACHE: list = []


def check(text: str, all_rules: list) -> list:
    """Every problem: a path no route has, a route no row names, a family's wrong count."""
    _RULES_CACHE[:] = all_rules
    toks = tokens(text)
    problems = []
    for family, path, is_family, _count in toks:
        hit = (any(r == path or r.startswith(path + "/") for r in all_rules) if is_family
               else path in all_rules)
        if not hit:
            problems.append(f"{family}: `{path}{'/*' if is_family else ''}` is no route")
    assigned: dict = {}
    for r in all_rules:
        if r.startswith(REDESIGN) or r == "/v2":
            continue
        best = None
        for _family, path, is_family, _count in toks:
            if r == path or (is_family and r.startswith(path + "/")):
                if best is None or len(path) > len(best[0]) or (len(path) == len(best[0])
                                                                  and not is_family):
                    best = (path, is_family)
        if best is None:
            problems.append(f"`{r}` is a route no row names")
        else:
            assigned.setdefault(best, []).append(r)
    for family, path, is_family, count in toks:
        if is_family and count is not None:
            got = len(assigned.get((path, True), []))
            if got != count:
                problems.append(f"{family}: `{path}/*` says {count}, and {got} routes are its")
    return problems


def test_every_row_names_routes_and_every_route_a_row():
    all_rules = rules()
    assert len(all_rules) >= 300, len(all_rules)              # the floor; 379 on 2026-10-10
    text = open(DOC, encoding="utf-8").read()
    assert len(table_rows(text)) >= 40, len(table_rows(text))
    problems = check(text, all_rules)
    assert problems == [], "\n".join(problems)


PLANTED = """
## Legacy routes by family

| Family | Routes | Status | Home or reason |
|---|---|---|---|
| Real | `/a/one`, `/two`, `/fam/*` (2) | REMOVE | x |
| Gone | `/a/three` | REMOVE | x |
| Counted | `/c/*` (1) | REMOVE | x |

## Next
"""


def test_the_scan_names_each_planted_case():
    got = check(PLANTED, ["/a/one", "/a/two", "/fam/x", "/fam/y", "/c/p", "/c/q", "/z",
                          "/v2/ok"])
    assert got == ["Gone: `/a/three` is no route", "`/z` is a route no row names",
                   "Counted: `/c/*` says 1, and 2 routes are its"], got


@pytest.mark.parametrize("path,want", [("/device/<ip>/backup_config", "/device/<>/backup_config"),
                                       ("/settings/", "/settings")])
def test_parameters_compare_by_place(path, want):
    assert _norm(path) == want
