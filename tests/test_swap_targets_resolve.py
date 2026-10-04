"""C409: every v2 control's swap lands, every time (the operator, 2026-10-04: Monitoring's range
links drew "Couldn't load: nothing on this page is #tab-body"; the first click worked and every
later one failed until a reload).

The cause: `#fleet` carried `hx-swap="outerHTML"` for its own refresh, htmx passed it down to
the range links inside it, and their swap replaced `#tab-body` ITSELF with an answer holding no
`#tab-body`, so the next click had no target. C385's check caught an INHERITED `hx-select`; this
is the class around it: a swap whose select, target or swap does not fit its own answer.

For every GET control on the v2 pages of test_device_v2's lab (this lab's real fleet dashboard
set), its `hx-select`, `hx-target` and `hx-swap` resolved as htmx resolves them under the page's
OWN config (inherited from ancestors unless `disableInheritance` is set), and its REAL answer
fetched:
- its `hx-select` names something the answer holds;
- its `hx-target` names something on its page;
- an `outerHTML` swap into an `#id` keeps that id: the answer's root carries it, or the next
  swap has nothing to land in ("works once");
- the page's config turns inheritance off, so no control takes a swap meant for its container.
"""

import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest

from tests.test_device_v2 import lab  # noqa: F401 (the fixture)

PAGES = ["/v2/monitoring", "/v2/monitoring/coverage", "/v2/devices", "/v2/device/r3",
         "/v2/device/r3?tab=intent", "/v2/device/r3?tab=history", "/v2/device/r3?tab=monitoring",
         "/v2/device/r3?tab=logs", "/v2/device/r3?tab=netbox", "/v2/device/r3?tab=neighbours",
         "/v2/history", "/v2/credentials", "/v2/help/about"]
SHAPE = ("hx-select", "hx-target", "hx-swap")
VOID = {"input", "br", "img", "meta", "link", "hr", "source", "wbr", "col", "area", "base"}
FLEET = "rcn-lab-overview"


class _Controls(HTMLParser):
    """Every element with `hx-get`, with its attributes as htmx resolves them, and every id."""

    def __init__(self, inherit: bool):
        super().__init__(convert_charrefs=True)
        self.inherit, self.stack, self.controls, self.ids = inherit, [], [], set()

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if a.get("id"):
            self.ids.add(a["id"])
        if "hx-get" in a:
            got = {k: a[k] for k in SHAPE if k in a}
            if self.inherit:
                for _t, anc in reversed(self.stack):
                    dis = anc.get("hx-disinherit", "")
                    for k in SHAPE:
                        if k not in got and k in anc and dis != "*" and k not in dis.split():
                            got[k] = anc[k]
            self.controls.append(dict(got, **{"hx-get": a["hx-get"], "tag": tag,
                                              "text": a.get("aria-label", "")}))
        if tag not in VOID:
            self.stack.append((tag, a))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def _config(page: str) -> dict:
    m = re.search(r'<meta name="htmx-config" content=\'([^\']*)\'', page)
    return json.loads(m.group(1)) if m else {}


def _root_id(answer: str) -> str:
    m = re.match(r"\s*(?:<!--.*?-->\s*)*<[a-zA-Z][^>]*\bid=\"([^\"]+)\"", answer, re.S)
    return m.group(1) if m else ""


def _ids(answer: str) -> set:
    return set(re.findall(r'\bid="([^"]+)"', answer))


def _survey(lab):  # noqa: F811
    lab["settings"]["grafana_fleet_dashboard_uid"] = FLEET
    problems, checked = [], 0
    for page_url in PAGES:
        r = lab["client"].get(page_url)
        assert r.status_code == 200, (page_url, r.status_code)
        page = r.get_data(as_text=True)
        p = _Controls(inherit=not _config(page).get("disableInheritance"))
        p.feed(page)
        for c in p.controls:
            url = c["hx-get"].replace("&amp;", "&")
            if not url.startswith("/"):
                continue
            target = c.get("hx-target", "")
            if target.startswith("#") and target[1:] not in p.ids:
                problems.append((page_url, url, f"hx-target {target} is not on the page"))
            ans = lab["client"].get(url, headers={"HX-Request": "true"})
            if ans.status_code >= 400:
                continue          # said by the never-silent check, not this one
            body = ans.get_data(as_text=True)
            checked += 1
            sel = c.get("hx-select", "")
            if sel.startswith("#") and sel[1:] not in _ids(body):
                problems.append((page_url, url, f"hx-select {sel} is not in its answer"))
            swap = (c.get("hx-swap") or "innerHTML").split()[0]
            if swap == "outerHTML" and target.startswith("#") and not sel \
                    and _root_id(body) != target[1:]:
                problems.append((page_url, url, f"outerHTML into {target}, and the answer's root "
                                 f"is #{_root_id(body) or '(no id)'}: the next swap has no target"))
    return problems, checked


def test_every_swap_fits_its_own_answer(lab):  # noqa: F811
    problems, checked = _survey(lab)
    assert checked >= 40, f"the population is too small to mean anything ({checked})"
    assert problems == [], "\n".join(f"{p}: {u}: {why}" for p, u, why in problems)


def test_the_page_turns_inheritance_off(lab):  # noqa: F811
    page = lab["client"].get("/v2/devices").get_data(as_text=True)
    assert _config(page).get("disableInheritance") is True, \
        "inheritance on: a control takes the swap its container set for itself"
