"""Devices › Change a setting on the ticked devices (7.4's board D, approved 2026-10-04 on canvas
v32; built 2026-10-10), on test_bulk_intent's lab: four devices' REAL fleet intent committed in a
real repository, rendered by the real template render with a stub secret lookup. Only the list
registry and the render's wiring are replaced at their edge.

- Devices' Actions offer Change a setting on the ticked devices, its how-link beside it;
- the page draws the ticked devices and one empty setting; Add a setting redraws the form with
  what was typed and one more row;
- a row's values are read as the intent file holds them (a YAML list, `(absent)`), and a row
  missing a value is refused naming it, before any device is read;
- the preview leads with the counts, draws the refused devices with both operands, groups the
  accepted ones by what changes in their render (collapsed, each device's intent diff inside),
  and binds one confirm to the core's hash;
- the apply commits once, as the verified person, and the result names the commit and offers a
  deploy plan for exactly the changed devices; a confirm whose hash is not the preview's commits
  nothing, naming both; a request that is no person commits nothing.
"""

import re
import subprocess

import pytest

from tests.test_bulk_intent import OLD_SETTINGS, _render, lab  # noqa: F401 (the fixture)

FLOW = "[" + ", ".join(OLD_SETTINGS) + "]"
KEPT = "[" + ", ".join(OLD_SETTINGS[:2]) + "]"


@pytest.fixture
def web(lab, tmp_path, monkeypatch):  # noqa: F811
    repo, hostvars, R = lab
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: str(name) == "Lab")
    monkeypatch.setattr("routes.templatize._bulk_render_and_eligible",
                        lambda list_name, repo: (_render, None))
    import app as A
    return {"client": A.app.test_client(), "repo": repo, "hostvars": hostvars, "R": R}


def _form(devices=("s1", "s2", "r1"), **over):
    body = {"list": "Lab", "device": list(devices), "summary": "drop the source interface",
            "path": ["logging.settings"], "before": [FLOW], "after": [KEPT]}
    body.update(over)
    return body


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def test_devices_actions_offer_the_change():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "templates", "v2", "_devices.html"), encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r'<button type="submit" role="menuitem" class="menu-item" data-op="bulk-intent" '
                  r'formaction="\{\{ url_for\(\'bulk_intent_v2.page\'\) \}\}"[^>]*>.*?</button>'
                  r"\{\{ how\('bulk-intent'", text, re.S)
    assert m and "Change a setting on" in m.group(0)


def test_the_page_draws_the_ticked_devices_and_one_setting(web):
    html = web["client"].get("/v2/devices/change?list=Lab&device=s1&device=r1") \
        .get_data(as_text=True)
    assert "Change a setting on 2 devices" in html
    assert html.count('name="path"') == 1 and "s1, r1" in html


def test_add_a_setting_keeps_what_was_typed(web):
    html = web["client"].get("/v2/devices/change?list=Lab&device=s1&path=logging.settings"
                             "&before=x&after=y&more=1", headers={"HX-Request": "true"}) \
        .get_data(as_text=True)
    assert html.count('name="path"') == 2 and 'value="logging.settings"' in html
    assert "<html" not in html, "the card alone, in place"


def test_a_row_missing_a_value_is_refused_before_any_device_is_read(web, monkeypatch):
    monkeypatch.setattr("modules.nsot.bulk_intent.plan", lambda *a, **k: pytest.fail("read"))
    r = web["client"].post("/v2/devices/change/preview", data=_form(after=[""]))
    assert r.status_code == 400
    assert "setting 1 (logging.settings) needs the value it holds now" in r.get_data(as_text=True)


def test_the_preview_groups_refuses_and_binds_one_confirm(web):
    repo, hostvars, R = web["repo"], web["hostvars"], web["R"]
    doc = hostvars.read_committed(repo, "s2")
    doc["logging"]["settings"] = ["trap errors"] + OLD_SETTINGS[1:]
    hostvars.write_committed(repo, doc)
    R.save_host_vars("Lab", ["s2"], message="host_vars: s2 drift")
    html = web["client"].post("/v2/devices/change/preview", data=_form()) \
        .get_data(as_text=True)
    assert "2 device(s), 1 group(s), 1 refused" in html
    refused = re.search(r'data-keep="bi-refused".*?</details>', html, re.S).group(0)
    assert "s2" in refused and "trap errors" in refused and "trap critical" in refused
    group = re.search(r'<details class="sc-grp" data-keep="bi-group-1">.*?</form>', html,
                      re.S).group(0)
    assert "logging source-interface Loopback0" in group, "the rendered line no longer drawn"
    r1 = re.search(r'<details class="bi-dev"><summary><span class="mono">r1</span>.*?</details>',
                   group, re.S).group(0)
    assert re.search(r'<span class="op-del">-\s+- source-interface Loopback0</span>', r1), \
        "r1's intent diff, the list item it loses"
    confirm = re.search(r'<form[^>]*action="/v2/devices/change/apply".*?</form>', html,
                        re.S).group(0)
    assert re.search(r'name="hash" value="[0-9a-f]{16}"', confirm)
    assert "Commit the change to 2 devices&#39; intent" in confirm or \
        "Commit the change to 2 devices' intent" in confirm


def test_the_apply_commits_once_as_the_person_and_offers_the_deploy(web):
    repo = web["repo"]
    before = _head(repo)
    pv = web["client"].post("/v2/devices/change/preview", data=_form()).get_data(as_text=True)
    h = re.search(r'name="hash" value="([0-9a-f]{16})"', pv).group(1)
    r = web["client"].post("/v2/devices/change/apply", data=_form(hash=h))
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html[:400]
    head = _head(repo)
    assert head != before
    log = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%s%n%b"],
                         capture_output=True, text=True).stdout
    assert log.startswith("host_vars: drop the source interface (3 device(s), 1 group(s))")
    assert "test-person@example.invalid" in log
    assert head[:12] in html and "as test-person@example.invalid" in html
    deploy = re.search(r'href="(/v2/devices/deploy[^"]*)"', html).group(1)
    assert sorted(re.findall(r"device=(\w+)", deploy)) == ["r1", "s1", "s2"]
    for host in ("s1", "s2", "r1"):
        assert OLD_SETTINGS[2] not in web["hostvars"].read_committed(repo, host)["logging"][
            "settings"]


def test_a_hash_not_the_preview_s_commits_nothing_naming_both(web):
    before = _head(web["repo"])
    r = web["client"].post("/v2/devices/change/apply", data=_form(hash="0" * 16))
    html = r.get_data(as_text=True)
    assert r.status_code == 409 and "you gave 0000000000000000" in html
    assert "Nothing was committed" in html and _head(web["repo"]) == before


@pytest.mark.real_identity
def test_no_person_commits_nothing(web, monkeypatch):
    monkeypatch.setattr("modules.nsot.bulk_intent.apply", lambda *a, **k: pytest.fail("applied"))
    r = web["client"].post("/v2/devices/change/apply", data=_form(hash="0" * 16))
    assert r.status_code in (401, 403)
