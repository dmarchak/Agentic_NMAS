"""Board N's network picker, clicked in a real browser (the manual's rule: every screen and
operation clicked for real): the top bar's Network opens the list, read as it opens; choosing a
network opens the same kind of page for it, its address carrying ``?list=``, and the top bar
names it. A second network is added to the served lab's registry.
"""

import json
import time

from tests.test_device_v2 import lab  # noqa: F401
from tests.test_v2_layout_in_a_browser import served  # noqa: F401


def _wait(b, script, bound=10.0):
    """Poll *script* until it is truthy; the bound is about 2.5x a measured 4 s open on the
    laptop's browser, named when it fires."""
    end = time.monotonic() + bound
    while time.monotonic() < end:
        got = b.js(f"return {script};")
        if got:
            return got
        time.sleep(0.1)
    raise AssertionError(f"waited {bound} s for: {script}")


def test_the_picker_opens_lists_and_chooses(served, tmp_path, monkeypatch):
    from modules import identity

    registry = tmp_path / "device_lists.json"
    registry.write_text(json.dumps({"current_list": "Lab",
                                    "lists": {"Lab": "lab", "Branch": "branch"}}))
    (tmp_path / "lists" / "branch").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(identity, "identify", lambda _r=None: identity.Identity(
        actor="ana@example.invalid", email="ana@example.invalid", kind="person", verified=True,
        outcome="ok", peer="198.51.100.7", peer_trusted=True, header_present=True))
    srv, b = served
    b.go(srv.url("/v2/devices"))
    _wait(b, "document.querySelector('.net-pick summary strong')")
    assert b.js("return document.querySelector('.net-pick summary strong').textContent;") == "Lab"
    b.js("document.querySelector('.net-pick summary').click();")
    _wait(b, "document.querySelectorAll('#net-pick-items .net-row').length >= 2")
    names = b.js("return Array.from(document.querySelectorAll('#net-pick-items .net-row "
                 ".grow')).map(function (e) { return e.textContent; });")
    assert {"Branch", "Lab"} <= set(names), names
    b.js("Array.from(document.querySelectorAll('#net-pick-items .net-row')).filter(function (e) "
         "{ return e.textContent.indexOf('Branch') === 0; })[0].click();")
    _wait(b, "location.search.indexOf('list=Branch') >= 0")
    assert b.js("return location.pathname;") == "/v2/devices"
    _wait(b, "document.querySelector('.net-pick summary strong')")
    assert b.js("return document.querySelector('.net-pick summary strong').textContent;") == "Branch"
