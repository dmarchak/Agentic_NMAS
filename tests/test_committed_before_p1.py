"""C568 (the operator's walk, 2026-10-07): Coverage's combined deploy, on the host's REAL documents.

The walk brought in the shipped `_common.j2`, approved both base templates, ticked r2 and s1 on
Coverage and pressed Deploy missing templates: every device's program was refused, "'dict object'
has no attribute 'source_interfaces'", followed by a guess about interface keys and routing. The
committed profile was right (`management: {data: {source_interfaces: {ssh, tftp}}}`); the fault
was the device's OWN intent, rendered alone to measure what the profile adds: every intent on the
host was committed before P1 added `source_interfaces` to the schema, and the shipped template
reads it. The suite's lab never met such an intent: it parses r2's golden with today's parser,
which emits the key.

THE FIXTURES ARE THE HOST'S COMMITTED FILES (tests/fixtures/committed/README.md): r2's and s1's
intent, the profile, and their goldens, read through `scripts/nmas-config-read` (masked) on
2026-10-07, one edit (10.0.0.x to 192.0.2.x, in intent and golden alike). The secret lookup
answers each reference with the placeholder the masked golden holds in its place, so a secret
line renders equal to its golden. On these, the walk's preview must be exactly the two lines on
each ticked device, and only the ticked ones.
"""

import os

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "committed")
LINES = ["ip ssh source-interface Loopback0", "ip tftp source-interface Loopback0"]
DEVICES = {"r2": {"hostname": "r2", "ip": "192.0.2.12", "device_type": "cisco_xe",
                  "platform": "cisco_iosxe", "role": "router"},
           "s1": {"hostname": "s1", "ip": "192.0.2.21", "device_type": "cisco_ios",
                  "platform": "cisco_ios", "role": "switch"}}
#: Each secret reference, answered with what the masked golden holds in its place (a stored
#: user secret is its type and hash together).
SECRETS = {"snmp_community_ro": "<redacted:snmp_community>",
           "user_admin_secret": "9 <redacted:user_password>"}


def _text(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def host(monkeypatch, tmp_path):
    """A list 'Lab' holding r2 and s1 as the host holds them: golden, committed intent, the
    committed profile, and the shipped templates, approved (the walk's steps 1 to 3)."""
    import app as A
    import routes.golden as golden
    from modules.nsot import approval, templates_repo
    from modules.nsot import repo as R
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars

    list_dir = tmp_path / "lab"
    repo = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
    settings = {"nsot_git_author_name": "NMAS", "nsot_git_author_email": "nmas@localhost"}
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
    templates_repo.seed_templates(repo)
    assert R.save_templates("Lab", ["_common.j2", "cisco_ios/base.j2", "cisco_iosxe/base.j2"],
                            actor="t", message="the shipped templates")["ok"]
    goldens = {d: _text(f"{d}.cfg") for d in DEVICES}
    save_golden("Lab", [GoldenItem(d, goldens[d], DEVICES[d]["ip"],
                                   platform=DEVICES[d]["platform"]) for d in DEVICES],
                source="onboarding", actor="t", allow_new=True, baseline=False)
    for d in DEVICES:
        with open(os.path.join(repo, "host_vars", f"{d}.yml"), "w", encoding="utf-8") as fh:
            fh.write(_text(f"{d}.yml"))
    assert save_host_vars("Lab", list(DEVICES), actor="t", source="extraction")["ok"]
    os.makedirs(os.path.join(repo, "profiles"), exist_ok=True)
    with open(os.path.join(repo, "profiles", "monitoring.yml"), "w", encoding="utf-8") as fh:
        fh.write(_text("profile.yml"))
    assert R._commit_paths("Lab", ["profiles/monitoring.yml"], "profile: the host's",
                           ["Actor: t"], "profile")["ok"]
    monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets",
                        lambda hv, h, ln="": {**hv, "secrets": dict(SECRETS)})
    monkeypatch.setattr("modules.credentials.get_template_secret",
                        lambda key: SECRETS.get(key.rsplit(":", 1)[-1]))
    monkeypatch.setattr("modules.nsot.restore._devices_of",
                        lambda ln: [dict(v) for v in DEVICES.values()])
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda *a, **k: [dict(v) for v in DEVICES.values()])
    monkeypatch.setattr(golden, "_read_running", lambda d, phases=None: (goldens[d["hostname"]], ""))
    from modules.nsot import listref
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    return {"client": A.app.test_client(), "app": A.app, "repo": repo}


def _rows(host, *devices):
    """Coverage's combined deploy, as the form a ticked selection sends asks for it."""
    from flask import request

    from routes import v2
    query = "&".join(["list=Lab", "scope=templates", "picked=1"]
                     + [f"device={d}" for d in devices])
    with host["app"].test_request_context(f"/v2/monitoring/apply?{query}"):
        return {r["name"]: r for r in v2._apply_ctx(request)["rows"]}


class TestTheHostsDocuments:
    def test_the_premise_every_committed_intent_predates_the_key(self):
        """What the walk met: the committed intent has no `source_interfaces`; the profile
        holds it under `management.data`, the level the merge lifts."""
        for d in DEVICES:
            assert "source_interfaces" not in yaml.safe_load(_text(f"{d}.yml"))
        prof = yaml.safe_load(_text("profile.yml"))["sections"]["management"]
        assert prof["data"] == {"source_interfaces": {"ssh": "Loopback0", "tftp": "Loopback0"}}

    def test_the_own_intent_renders_with_the_shipped_template(self, host):
        from modules.nsot import hostvars, roundtrip
        for d, dev in DEVICES.items():
            own = hostvars.read_committed(host["repo"], d)
            assert "source_interfaces" not in own
            text = roundtrip.render(own, dev["platform"],
                                    template_root=os.path.join(host["repo"], "templates"))
            assert not set(LINES) & {l.strip() for l in text.splitlines()}


class TestTheWalksPreview:
    def test_exactly_the_two_lines_on_each_ticked_device(self, host):
        rows = _rows(host, "r2", "s1")
        assert sorted(rows) == ["r2", "s1"]
        for d, r in rows.items():
            assert not r["refused"], f"{d}: {r['refused']}"
            assert r["selectable"], (d, r["state"], r["blocking"])
            assert sorted(l.strip() for l in r["program"]) == LINES, (d, r["program"])

    def test_only_the_ticked_device_is_previewed(self, host):
        rows = _rows(host, "r2")
        assert list(rows) == ["r2"]
        assert sorted(l.strip() for l in rows["r2"]["program"]) == LINES

    def test_the_page_draws_only_the_ticked_device(self, host):
        html = host["client"].get("/v2/monitoring/apply?list=Lab&scope=templates&picked=1"
                                  "&device=s1").get_data(as_text=True)
        assert 'id="apply-s1"' in html and 'id="apply-r2"' not in html
        assert "Not sent:" not in html
        program = html[html.index('id="apply-s1"'):].split('<pre class="apply-program">', 1)[1]
        assert program.split("</pre>", 1)[0].splitlines() == LINES


def test_a_real_browser_sends_only_the_ticked_devices(host):
    """The walk's selection, clicked: Coverage offers r2 and s1 (Mgmt sources missing on both),
    both ticked on arrival; unticking s1 and pressing Deploy missing templates previews r2
    alone, with exactly the two lines."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    settled = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
    with browser.Served(host["app"]) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/monitoring/coverage"))
            b.wait_for("return window.Alpine && window.htmx && document.querySelector('#cov-s1')"
                       " && " + settled, 15)
            boxes = dict(b.js("return Array.prototype.map.call(document.querySelectorAll("
                              "'#coverage input[name=device]'), function (x) {"
                              " return [x.value, x.checked]; })"))
            assert boxes == {"r2": True, "s1": True}, boxes
            b.click("#cov-s1")
            b.click("#cov-bar button[type=submit]")
            b.wait_for("return !!document.getElementById('apply-preview')", 30)
            shown = b.js("return Array.prototype.map.call(document.querySelectorAll("
                         "'#apply-preview .cdep-device'), function (x) { return x.id; })")
            assert shown == ["apply-r2"], shown
            program = b.js("return document.querySelector('#apply-r2 pre.apply-program')"
                           ".textContent")
            assert program.splitlines() == LINES, program
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


class TestARefusalNamesThePath:
    """The render's refusal names the template line, the exact path read and what the intent
    holds there; never the old guess about interface keys and routing."""

    def test_a_top_level_section_the_intent_lacks(self):
        from jinja2.exceptions import UndefinedError

        from modules.nsot import roundtrip
        own = yaml.safe_load(_text("r2.yml"))
        own.pop("logging")
        with pytest.raises(UndefinedError) as e:
            roundtrip.render(own, "cisco_iosxe")
        words = str(e.value)
        assert words.startswith("The template (templates/_common.j2 line ")
        assert "reads `logging`, and the intent does not hold it: at the intent's top level, " \
               f"it holds {len(own) + 1} keys: acls, " in words, words
        assert "interface keys" not in words and "routing, vlans" not in words

    def test_a_nested_key(self):
        from jinja2.exceptions import UndefinedError

        from modules.nsot import roundtrip
        own = yaml.safe_load(_text("r2.yml"))
        own["routing"] = {k: v for k, v in own["routing"].items() if k != "bgp"}
        with pytest.raises(UndefinedError) as e:
            roundtrip.render(own, "cisco_iosxe")
        assert "reads `routing.bgp`, and the intent does not hold it: at routing, it holds " \
               f"{len(own['routing'])} keys: {', '.join(sorted(own['routing']))}." in str(e.value)
