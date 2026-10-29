"""The device page's Deploy, with Mode B, on v2 (7.3; the device-actions canvas, boards 5 and 6;
the last of the four device actions).

On test_profile_apply's lab (r2's REAL capture and intent), edited so the deploy has all three
things the board draws: r2's golden lacks `lldp run` and carries `load-interval 30` on
GigabitEthernet2, and its intent adds `shutdown` on GigabitEthernet3. So the program sends
`lldp run` and a dangerous `shutdown`, and `load-interval 30` is left on the device, offered for
removal. The plan is `routes.deploy.plan_devices`, the one `/deploy/plan` uses; the apply is
`apply_batch` as a job (`deploy_job`), the one the batch apply uses, its device path spied:

- the card (from "Plan a deploy…", or the page without script): the exact program, the
  dangerous line waiting on its reason (not confirmable), the residue with its box, what will
  not happen, the operands, the checks, no confirm until every reason is given;
- a reason typed plans again and offers the confirm bound to that program's hash; a residue
  line ticked plans its removal (Mode B) and waits on its own reason, then carries both, by id
  and with each reason, into the hash and the apply;
- the confirm starts the deploy as a job (kind "deploy", never "monitoring profile apply"),
  as the verified person; the card draws the pipeline's stages while it runs and listens for
  the job and each step; the result is the receipt's, in place;
- a program that moved is refused with nothing sent; a failed verify that rolled back draws
  "Rolled back" and its two ways out, each opening what it names;
- a confirm naming no list, an unknown list or no hash is refused.
"""

import html as html_mod
import json
import os
import re

import pytest

from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def deploy(lab, monkeypatch):  # noqa: F811
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    real = lab["captured"]
    assert "\nlldp run\n" in real and "\ninterface GigabitEthernet2\n" in real
    golden = real.replace("\nlldp run\n", "\n").replace(
        "\ninterface GigabitEthernet2\n", "\ninterface GigabitEthernet2\n load-interval 30\n")
    out = save_golden("Lab", [GoldenItem("r2", golden, "203.0.113.12", platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert out.get("commit"), out
    intent = real.replace("\ninterface GigabitEthernet3\n", "\ninterface GigabitEthernet3\n shutdown\n")
    hostvars.write_committed(lab["repo"], get_parser("cisco_iosxe").parse(intent))
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"}]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in devices])
    return lab


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _vals(card):
    m = re.search(r"hx-vals='([^']*)'", card[card.index("op-confirm"):])
    return json.loads(html_mod.unescape(m.group(1)))


def _residue_id(card, text="load-interval 30"):
    m = re.search(r'name="rm" value="([^"]+)" id="rm-[^"]+"[^>]*>\s*<label[^>]*><code>[^<]*'
                  + re.escape(text), card)
    assert m, "the residue line has its box"
    return m.group(1)


def _spy(monkeypatch, outcome="deployed", rollback=None, sent_hash=None):
    import routes.deploy as rd
    reached = []

    def spy(entry, list_name, rows, authorise, **kw):
        reached.append({"device": entry["artifact"].device, "authorise": authorise,
                        "scope": kw.get("scope", "")})
        return {"device": entry["artifact"].device, "outcome": outcome,
                "commands": ["lldp run"], "stage": "verify" if rollback else "",
                **({"program_hash": sent_hash[0]} if sent_hash else {}),
                "verify": {"ok": not rollback, "checked_protocols": ["ospf"],
                           "pre": {"ospf": 6}, "post": {"ospf": 5 if rollback else 6}},
                "reason": "OSPF 5 of 6 after the settle window" if rollback else "",
                **({"rolled_back": True, "rollback_outcome": rollback} if rollback else {})}
    monkeypatch.setattr(rd, "_deploy_one", spy)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
    return reached


def _reasons(dz="the link is being retired"):
    return f"&dz::0={dz}"


class TestTheCard:
    def test_the_program_the_dangerous_line_the_residue_and_no_confirm_yet(self, deploy):
        r, card = _get(deploy, "/v2/device/r2/deploy")
        assert r.status_code == 200
        assert "Deploy committed intent to r2" in card and 'id="device-op"' in card
        assert "lldp run" in card and "shutdown" in card
        assert 'name="dz::0"' in card, "the dangerous line waits on its reason"
        assert "load-interval 30" in card and 'name="rm"' in card
        assert "What will not happen" in card and "Operands" in card and "Checks" in card
        assert "op-confirm" not in card, "no confirm until every reason is given"
        assert "waits on your stated reason" in card
        assert "default-src" in r.headers.get("Content-Security-Policy", "")

    def test_a_reason_plans_again_and_offers_the_confirm_bound_to_that_program(self, deploy):
        _r, card = _get(deploy, "/v2/device/r2/deploy?back=overview" + _reasons())
        vals = _vals(card)
        assert vals["list"] == "Lab" and vals["capture_hash"] and vals["command_hash"]
        assert json.loads(vals["authorise"]) == [{"line": "shutdown",
                                                   "reason": "the link is being retired"}]
        assert json.loads(vals["remove"]) == []
        assert 'data-op="deploy"' in card[card.index("op-confirm") - 200:]

    def test_a_ticked_line_is_removed_with_its_own_reason_in_the_hash(self, deploy):
        _r, plain = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        rid = _residue_id(plain)
        _r, ticked = _get(deploy, f"/v2/device/r2/deploy?rm={rid}" + _reasons())
        assert "will be removed" in ticked and f'name="why::{rid}"' in ticked
        assert "op-confirm" not in ticked, "a ticked line waits on its own reason"
        _r, both = _get(deploy, f"/v2/device/r2/deploy?rm={rid}&why::{rid}=left+over+from+the+old+design"
                        + _reasons())
        assert "no load-interval 30" in both, "the removal is in the program"
        vals, before = _vals(both), _vals(plain)
        assert json.loads(vals["remove"]) == [rid]
        assert vals["command_hash"] != before["command_hash"]
        assert {"reason": "left over from the old design"} .items() <= next(
            a for a in json.loads(vals["authorise"]) if "load-interval" in a["line"]).items()

    def test_a_freed_card_keeps_what_its_person_entered(self, deploy):
        """C473 (2026-10-05): a card refused because another operation held the device redraws
        when the hold ends, and it drew the card from its start, empty: the ticked removal and
        every typed reason gone. Its redraw now sends the card's form, and `when_free` plans
        from it, the same program and hash as the card had."""
        _r, plain = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        rid = _residue_id(plain)
        q = f"rm={rid}&why::{rid}=left+over+from+the+old+design" + _reasons()
        _r, direct = _get(deploy, f"/v2/device/r2/deploy?{q}")
        _r, freed = _get(deploy, f"/v2/device/r2/when-free?op=deploy&back=overview&{q}")
        assert "no load-interval 30" in freed, "the ticked removal survived"
        assert _vals(freed)["command_hash"] == _vals(direct)["command_hash"]

    def test_every_held_card_with_fields_sends_its_form_when_freed(self):
        """The shape: each held card whose form a person fills (deploy, restore, retry) includes
        that form in its `when_free` redraw. Retire and revert carry theirs in the URL."""
        for name in ("_deploy.html", "_restore.html", "_retry.html"):
            text = open(os.path.join(ROOT, "templates", "v2", name), encoding="utf-8").read()
            held = [line for line in text.splitlines() if "device_v2.when_free" in line]
            assert held and all('hx-include="find .op-form"' in line for line in held), name

    def test_the_header_opens_the_card_and_the_page_draws_it_without_script(self, deploy):
        _r, page = _get(deploy, "/v2/device/r2")
        head = page[page.index('data-op="deploy"') - 40:page.index("Plan a deploy")]
        assert 'hx-get="/v2/device/r2/deploy' in head
        _r, page = _get(deploy, "/v2/device/r2?op=deploy")
        assert "Deploy committed intent to r2" in page


@pytest.fixture
def profiled(lab, monkeypatch):  # noqa: F811
    """r6 (r2's REAL capture without its SNMP and discovery lines) under the network's committed
    monitoring profile, which supplies them; its golden lacks `ip ssh maxstartups 128`, which
    its intent holds (pending before any edit). With `edit`, its intent then adds an NTP server
    in a commit of its own (this edit); without, its one intent commit is its first."""
    from modules.nsot import hostvars
    from modules.nsot import repo as R
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    from tests.test_profile_apply import _commit_proposal

    _commit_proposal()
    r6 = lab["r6"]
    assert "\nip ssh maxstartups 128\n" in r6
    out = save_golden("Lab", [GoldenItem("r6", r6.replace("\nip ssh maxstartups 128\n", "\n"),
                                         "203.0.113.16", platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert out.get("commit"), out
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    devices = [{"hostname": "r6", "ip": "203.0.113.16", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"}]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in devices])

    def edit():
        hv = hostvars.read_committed(lab["repo"], "r6")
        hv["ntp_servers"] = list(hv.get("ntp_servers") or []) + ["192.0.2.99"]
        hostvars.write_committed(lab["repo"], hv)
        assert save_host_vars("Lab", ["r6"], actor="t", source="extraction")["ok"]
        return R.git(lab["repo"], "log", "-1", "--format=%H %s", "--", "host_vars/r6.yml")[1]

    return dict(lab, edit=edit)


def _attribution(card):
    """The attribution's part of the card: its heading, the edit's line, its warning, and each
    line group by name, with the group's words and lines (unescaped)."""
    assert "<div data-attribution>" in card, "the card draws no attribution"
    i = card.index("<div data-attribution>")
    part = card[i:card.index('id="expected"', i)]
    groups = {g: html_mod.unescape(body) for g, body in
              re.findall(r'<div data-attribution-group="(\w+)">(.*?)</div>', part, re.S)}
    edit = re.search(r"<p[^>]*data-attribution-edit>(.*?)</p>", part, re.S)
    warn = re.search(r'<div class="notice notice-warn">.*?<p>(.*?)</p>', part, re.S)
    return {"part": part, "groups": groups, "edit": edit and edit.group(1),
            "warn": warn and html_mod.unescape(warn.group(1))}


def _pre(group):
    m = re.search(r'<pre class="op-diff">(.*?)</pre>', group, re.S)
    return m.group(1).split("\n") if m else []


class TestTheAttribution:
    """C867 (D4 again, on v2): where each added line comes from, drawn before the confirm, as
    today's wizard drew it (static/js/nmas_preview_confirm.js): the edit's commit and subject,
    its warning, the profile's lines apart, this edit's, and those already pending."""

    def test_this_edits_line_and_the_pending_one_each_under_its_count(self, deploy):
        from modules.nsot import repo as R
        sha, subject = R.git(deploy["repo"], "log", "-1", "--format=%H %s", "--",
                             "host_vars/r2.yml")[1].strip().split(" ", 1)
        _r, card = _get(deploy, "/v2/device/r2/deploy")
        a = _attribution(card)
        assert card.index("<div data-attribution>") < card.index("Expected effects")
        assert "Where the added lines come from" in a["part"]
        assert a["edit"] == f"This edit: <code>{sha[:8]}</code> {subject}"
        g = a["groups"]
        assert set(g) == {"edit", "pending"}, "no profile group: r2's profile supplies nothing"
        assert "From this edit: <strong>1</strong> line(s)" in g["edit"]
        assert _pre(g["edit"]) == [" shutdown"]
        assert ("Not from this edit: <strong>1</strong> line(s), already pending before it. "
                "They are sent too.") in g["pending"]
        assert _pre(g["pending"]) == ["lldp run"]
        assert a["warn"] is None

    def test_the_profiles_lines_are_drawn_apart_from_the_edits(self, profiled):
        sha, subject = profiled["edit"]().strip().split(" ", 1)
        _r, card = _get(profiled, "/v2/device/r6/deploy")
        a = _attribution(card)
        assert a["edit"] == f"This edit: <code>{sha[:8]}</code> {subject}"
        g = a["groups"]
        assert list(g) == ["profile", "edit", "pending"], "the profile's group first, apart"
        inherited = _pre(g["profile"])
        assert ("Inherited from the network's monitoring profile: "
                f"<strong>{len(inherited)}</strong> line(s)") in g["profile"]
        assert "lldp run" in inherited and "snmp-server trap-source Loopback0" in inherited
        assert all(line.startswith(("snmp", "lldp")) for line in inherited), inherited
        assert _pre(g["edit"]) == ["ntp server 192.0.2.99"]
        assert "From this edit: <strong>1</strong> line(s)" in g["edit"]
        assert _pre(g["pending"]) == ["ip ssh maxstartups 128"]
        assert "Not from this edit: <strong>1</strong> line(s)" in g["pending"]
        # Every line sent is in exactly one group: none rides along unattributed.
        sent = re.findall(r'<span class="op-add">(.*?)</span>', card)
        grouped = inherited + _pre(g["edit"]) + _pre(g["pending"])
        assert sorted(html_mod.unescape(s) for s in sent) == sorted(grouped)

    def test_a_first_intent_commit_warns_and_attributes_nothing_to_the_edit(self, profiled):
        _r, card = _get(profiled, "/v2/device/r6/deploy")
        a = _attribution(card)
        assert a["warn"] and a["warn"].startswith("First committed intent for this device")
        assert a["warn"].endswith("."), a["warn"]
        g = a["groups"]
        assert list(g) == ["profile", "edit", "pending"], list(g)
        assert "From this edit: <strong>0</strong> line(s)" in g["edit"] and _pre(g["edit"]) == []
        assert _pre(g["pending"]) == ["ip ssh maxstartups 128"]
        assert "lldp run" in _pre(g["profile"])

    def test_devices_plan_a_deploy_draws_the_same_attribution(self, deploy):
        """C878: Devices › Plan a deploy (the batch preview, `_apply_preview.html`) carried the
        attribution note whole and drew only its title; it draws it through the one macro."""
        from modules.nsot import repo as R
        sha, subject = R.git(deploy["repo"], "log", "-1", "--format=%H %s", "--",
                             "host_vars/r2.yml")[1].strip().split(" ", 1)
        r, page = _get(deploy, "/v2/devices/deploy?device=r2")
        assert r.status_code == 200
        assert "Where the added lines come from" in page
        assert "<div data-attribution>" in page, "the batch preview draws only the note's title"
        i = page.index("<div data-attribution>")
        part = page[i:page.index("Not from this edit", i) + 400]
        groups = {g: html_mod.unescape(body) for g, body in
                  re.findall(r'<div data-attribution-group="(\w+)">(.*?)</div>', part, re.S)}
        assert f"This edit: <code>{sha[:8]}</code> {subject}" in part
        assert set(groups) == {"edit", "pending"}, list(groups)
        assert "From this edit: <strong>1</strong> line(s)" in groups["edit"]
        assert _pre(groups["edit"]) == [" shutdown"]
        assert _pre(groups["pending"]) == ["lldp run"]


@pytest.fixture
def out_of_band(lab, monkeypatch):  # noqa: F811
    """The operator's Walk 3 (2026-10-26, C1434): `load-interval 30` typed on the device out
    of band and taken in by a Capture (the golden holds it), intent otherwise the device's own,
    so the only line to send is the removal and no line is dangerous."""
    from modules.nsot.repo import GoldenItem, save_golden
    real = lab["captured"]
    golden = real.replace("\ninterface GigabitEthernet2\n",
                          "\ninterface GigabitEthernet2\n load-interval 30\n")
    assert golden != real
    out = save_golden("Lab", [GoldenItem("r2", golden, "203.0.113.12", platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert out.get("commit"), out
    # Intent stays the lab's own, committed from this same capture (the device's config): the
    # program being the removal alone, asserted below, is what shows nothing else differs.
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"}]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in devices])
    return lab


def _spy_pipeline(monkeypatch):
    """The real apply (`routes.deploy._deploy_one`: the program computed again with its
    removals, every removal's reason checked on the path that connects), with only the
    pipeline, the part that reaches a device, replaced by a recorder that succeeds. Returns
    ``(contexts, authorisations)``: each pipeline context, and each `authorise` the job handed
    the real `_deploy_one`."""
    import modules.pipeline as P
    import routes.deploy as rd
    seen, authorised = [], []

    class _Runner:
        def __init__(self, ctx):
            self.ctx = ctx
            seen.append(ctx)

        def run(self):
            # As `PipelineRunner.run` answers: its own context, here every stage a pass.
            self.ctx.final_status = "success"
            return self.ctx
    real = rd._deploy_one

    def deploy_one(entry, list_name, rows, authorise, **kw):
        authorised.append(authorise)
        return real(entry, list_name, rows, authorise, **kw)
    monkeypatch.setattr(P, "PipelineRunner", _Runner)
    monkeypatch.setattr(rd, "_deploy_one", deploy_one)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
    return seen, authorised


def _program(ctx, ip):
    """The program the pipeline was handed for *ip*, its mode changes (`exit`, `end`) out."""
    return [line.rstrip() for line in ctx.confirmed_commands[ip]
            if line.strip() not in ("exit", "end")]


S1_IP = "192.0.2.21"
GI11 = ("interface GigabitEthernet1/1\n description h2 - VLAN 20\n switchport access vlan 20\n"
        " switchport mode access\n negotiation auto\n!\n")
#: The capture's own unused port, the shape the sibling Gi1/10 is given (s1 has no Gi1/10).
UNUSED = "interface GigabitEthernet0/1\n negotiation auto\n!\n"


@pytest.fixture
def walk_s1(lab, monkeypatch):  # noqa: F811
    """The device the operator's Walk 3 (2026-10-26, C1434) removed a line on: s1, a vIOS-L2
    switch (IOS 15.2), from its REAL golden (tests/fixtures/configs/fleet/s1.cfg, the reference
    lab's capture with its credential hashes replaced by valid fakes; the session transcript
    in tests/fixtures/transcripts/s1/ comes masked, its SNMP community `<redacted:…>`, which
    no template reproduces), with two minimal edits:

    - a sibling `interface GigabitEthernet1/10` beside `GigabitEthernet1/1`, in the shape of
      the capture's own unused port (`GigabitEthernet0/1`: ` negotiation auto`). The capture
      has none (vIOS-L2 numbers its ports 0/0 to 3/3); a 48-port IOS switch has both, and a
      section matcher that took `GigabitEthernet1/1` for a prefix of `GigabitEthernet1/10`
      would place or find the removal in the wrong section;
    - `load-interval 30` under `GigabitEthernet1/1` only, typed on the device out of band and
      taken in by a Capture (the golden holds it, intent does not).

    Intent is the device's own, so the only line to send is the removal, and no line is
    dangerous. In r2's lab list, beside it."""
    from modules import credentials
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars

    with open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "s1.cfg"),
              encoding="utf-8") as fh:
        real = fh.read()
    assert GI11 in real and UNUSED in real and "GigabitEthernet1/10" not in real
    device = real.replace(GI11, GI11 + UNUSED.replace("0/1", "1/10"))
    golden = device.replace("\ninterface GigabitEthernet1/1\n",
                            "\ninterface GigabitEthernet1/1\n load-interval 30\n")
    assert golden.count("load-interval 30") == 1 and golden != device
    intent = get_parser("cisco_ios").parse(device)
    intent["hostname"] = "s1"
    secrets = dict(intent.get("secrets") or {})
    out = save_golden("Lab", [GoldenItem("s1", golden, S1_IP, platform="cisco_ios")],
                      source="capture", actor="t", allow_new=True, baseline=False)
    assert out.get("commit"), out
    hostvars.write_committed(lab["repo"], intent)
    assert save_host_vars("Lab", ["s1"], actor="t", source="extraction")["ok"]
    # The lab hydrates r2's secrets for any device; s1's are its own.
    hydrate, stored = hostvars.hydrate_secrets, credentials.get_template_secret
    monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets",
                        lambda hv, host, ln="": ({**hv, "secrets": dict(secrets)}
                                                 if host == "s1" else hydrate(hv, host, ln)))
    monkeypatch.setattr("modules.credentials.get_template_secret",
                        lambda key: (secrets.get(key.rsplit(":", 1)[-1])
                                     if key.split(":")[1:2] == ["s1"] else stored(key)))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"},
               {"hostname": "s1", "ip": S1_IP, "device_type": "cisco_ios",
                "platform": "cisco_ios", "username": "admin"}]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in devices])
    # The plan reads the device's row (its platform, so its template) from the list's own
    # inventory, which the lab gives r2 and r6.
    monkeypatch.setattr("modules.nsot.restore._devices_of",
                        lambda ln: [dict(d) for d in devices])
    return dict(lab, s1_golden=golden)


def _deploy_button(card):
    """The card's Deploy (`data-needs`), its tag and its `hx-vals`."""
    m = re.search(r"<button[^>]*\bdata-needs=[^>]*>", card)
    assert m, "the card draws no Deploy"
    vals = re.search(r"hx-vals='([^']*)'", m.group(0))
    return m.group(0), json.loads(html_mod.unescape(vals.group(1)))


def _press(lab, host, card, fields):
    """Deploy pressed as the page presses it: its `hx-vals`, and the card's form (`hx-include`)
    as *fields*, the hidden ones the card draws included."""
    _tag, vals = _deploy_button(card)
    hidden = dict(re.findall(r'<input type="hidden" name="(back|plan|focus)" value="([^"]*)"',
                             card))
    assert hidden.get("plan") == "card", "the card's form says it is the card's"
    return lab["client"].post(f"/v2/device/{host}/deploy/confirm",
                              data=dict(hidden, **fields, **vals))


class TestOneClickOnTheWalksSwitch:
    """C1434, the operator's bar (2026-10-26): a Why typed and Deploy pressed at once sends that
    Why. Deploy carries the card's form and the program it drew; the server plans again with
    the reasons as typed and sends only that program, bound by the new plan's hashes."""

    def test_the_why_pressed_with_deploy_is_sent_and_only_gi1_1s_removal(self, walk_s1,
                                                                         monkeypatch):
        from modules.nsot import capture_job
        seen, authorised = _spy_pipeline(monkeypatch)
        _r, plain = _get(walk_s1, "/v2/device/s1/deploy?focus=removal")
        rid = _residue_id(plain, "load-interval 30")
        assert "GigabitEthernet1/10" not in plain[plain.index('id="removal"'):], \
            "nothing of Gi1/10 is left on the device"
        _r, ticked = _get(walk_s1, f"/v2/device/s1/deploy?rm={rid}")
        tag, _vals = _deploy_button(ticked)
        assert " disabled" in tag and f'data-needs="why::{rid}"' in tag
        r = _press(walk_s1, "s1", ticked, {"rm": rid,
                                           f"why::{rid}": "left over from the old design"})
        waiting = r.get_data(as_text=True)
        assert r.status_code == 200 and "Deploying to s1" in waiting, waiting[:600]
        job = re.search(r"/deploy/job/([0-9a-f]+)", waiting).group(1)
        assert capture_job.wait(job, 20)
        assert len(seen) == 1, ("the apply refused before the pipeline", capture_job.get(job))
        assert _program(seen[0], S1_IP) == ["interface GigabitEthernet1/1",
                                            " no load-interval 30"]
        assert not any("1/10" in line for line in seen[0].confirmed_commands[S1_IP])
        assert authorised == [{"s1": [{"line": "no load-interval 30",
                                       "reason": "left over from the old design"}]}]
        _r, out = _get(walk_s1, f"/v2/device/s1/deploy/job/{job}")
        assert "op-ok" in out, out[out.find("What happened"):][:600]

    def test_pressed_with_no_why_nothing_is_sent_and_the_line_is_named(self, walk_s1,
                                                                       monkeypatch):
        seen, _a = _spy_pipeline(monkeypatch)
        _r, plain = _get(walk_s1, "/v2/device/s1/deploy?focus=removal")
        rid = _residue_id(plain, "load-interval 30")
        _r, ticked = _get(walk_s1, f"/v2/device/s1/deploy?rm={rid}")
        r = _press(walk_s1, "s1", ticked, {"rm": rid, f"why::{rid}": ""})
        card = r.get_data(as_text=True)
        assert "Deploying to s1" not in card and seen == []
        assert "waits on your stated reason for <code>no load-interval 30</code>" in card

    def test_a_program_moved_since_it_was_drawn_is_not_sent_and_says_what_moved(
            self, walk_s1, monkeypatch):
        from modules.nsot.repo import GoldenItem, save_golden
        seen, _a = _spy_pipeline(monkeypatch)
        _r, plain = _get(walk_s1, "/v2/device/s1/deploy?focus=removal")
        rid = _residue_id(plain, "load-interval 30")
        _r, ticked = _get(walk_s1, f"/v2/device/s1/deploy?rm={rid}")
        # Between the draw and the press a Capture takes in Gi1/10 without its line, so intent
        # now sends it back: the program the press would send is not the one drawn.
        now = walk_s1["s1_golden"]
        bare = UNUSED.replace("0/1", "1/10")
        assert bare in now
        out = save_golden("Lab", [GoldenItem("s1", now.replace(
            bare, "interface GigabitEthernet1/10\n!\n"), S1_IP, platform="cisco_ios")],
            source="capture", actor="t", baseline=False)
        assert out.get("commit"), out
        r = _press(walk_s1, "s1", ticked, {"rm": rid,
                                           f"why::{rid}": "left over from the old design"})
        card = html_mod.unescape(r.get_data(as_text=True))
        assert "Deploying to s1" not in card and seen == []
        assert "Not sent: the program moved after this card drew it" in card
        said = card[card.find("Not sent"):][:900]
        assert "s1's captured configuration changed (capture " in said, said
        assert "now sent and not drawn: interface GigabitEthernet1/10; negotiation auto" \
            in said, said
        # The plan now is drawn, Why kept, and Deploy offered for IT.
        assert "left over from the old design" in card and "op-confirm" in card


class TestTheWalksRemoval:
    """C1434, found again on the operator's Walk 3 (2026-10-26): a removal with no dangerous
    line read "not applicable" on the reason check, so Deploy was offered before the Why was
    given, and the apply refused "1 line(s) need an authorisation with a reason"."""

    def _spy_pipeline(self, monkeypatch):
        return _spy_pipeline(monkeypatch)[0]

    def test_ticked_without_its_why_offers_no_deploy_and_names_the_line(self, out_of_band):
        _r, plain = _get(out_of_band, "/v2/device/r2/deploy?focus=removal")
        rid = _residue_id(plain, "load-interval 30")
        assert 'name="dz::' not in plain, "no dangerous line in this program"
        _r, ticked = _get(out_of_band, f"/v2/device/r2/deploy?rm={rid}")
        assert "op-confirm" not in ticked, "no Deploy for a program the apply would refuse"
        assert "waits on your stated reason for <code>no load-interval 30</code> (in its Why " \
               "box, beside the tick)" in ticked, ticked[ticked.find("Not available"):][:400]
        assert "<strong>lines needing a reason</strong>" in ticked
        # Drawn as the one confirm pattern (tests/test_v2_one_confirm.py), disabled, and not
        # marked the offered confirm: a disabled button sends nothing, and a press without its
        # Why is refused by the server too (TestOneClickOnTheWalksSwitch).
        button = re.search(r'<button[^>]*data-waits="1"[^>]*>', ticked)
        classes = re.search(r'class="([^"]*)"', button.group(0)).group(1).split() if button \
            else []
        assert button and " disabled" in button.group(0) and "op-confirm" not in classes \
            and re.search(r"Deploy \d+ line\(s\) to r2", ticked), \
            "Deploy drawn disabled, never offered"

    def test_the_regions_the_why_decides_are_drawn_for_the_page_to_draw_again(self,
                                                                              out_of_band):
        """C1847 (the operator's Mode B re-walk, 2026-10-27): the page plans again as a Why is
        typed and draws again only the checks, the operands and the authorisation note, so
        each is drawn with its id in both plans, the reason's check marked: failing with
        "authorised lines 0" before the Why, passing with 1 after it, the note gone."""
        _r, plain = _get(out_of_band, "/v2/device/r2/deploy?focus=removal")
        rid = _residue_id(plain, "load-interval 30")
        _r, waiting = _get(out_of_band, f"/v2/device/r2/deploy?rm={rid}")
        _r, given = _get(out_of_band, f"/v2/device/r2/deploy?rm={rid}"
                         f"&why::{rid}=left+over+from+the+old+design")

        def drawn(card):
            gate = re.search(r'<li data-gate="(\w+)" data-reason-gate>', card)
            auth = re.search(r'<dd class="mono" data-operand="authorised lines">([^<]*)</dd>',
                             card)
            note = re.search(r'<p class="op-note" id="deploy-auth-note"( hidden)?>', card)
            return (gate and gate.group(1), auth and auth.group(1),
                    note and not note.group(1),
                    [i for i in ("deploy-checks", "deploy-operands", "deploy-auth-note")
                     if f'id="{i}"' in card])
        every = ["deploy-checks", "deploy-operands", "deploy-auth-note"]
        assert drawn(waiting)[:2] == ("fail", "0") and drawn(waiting)[3] == every, \
            drawn(waiting)
        assert drawn(given) == ("pass", "1", False, every), drawn(given)

    def test_the_why_alone_authorises_it_and_only_the_removal_is_sent(self, out_of_band,
                                                                      monkeypatch):
        from modules.nsot import capture_job
        seen = self._spy_pipeline(monkeypatch)
        _r, plain = _get(out_of_band, "/v2/device/r2/deploy?focus=removal")
        rid = _residue_id(plain, "load-interval 30")
        _r, card = _get(out_of_band, f"/v2/device/r2/deploy?rm={rid}"
                        f"&why::{rid}=left+over+from+the+old+design")
        assert "op-confirm" in card, card[card.find("Not available"):][:400]
        vals = _vals(card)
        assert json.loads(vals["authorise"]) == [{"line": "no load-interval 30",
                                                   "reason": "left over from the old design"}]
        r = out_of_band["client"].post("/v2/device/r2/deploy/confirm", data=vals)
        waiting = r.get_data(as_text=True)
        assert r.status_code == 200 and "Deploying to r2" in waiting, waiting[:400]
        job = re.search(r"/deploy/job/([0-9a-f]+)", waiting).group(1)
        assert capture_job.wait(job, 20)
        assert len(seen) == 1, ("the apply refused before the pipeline",
                                capture_job.get(job))
        ctx = seen[0]
        sent = ctx.confirmed_commands["203.0.113.12"]
        assert [l.strip() for l in sent if l.strip() not in ("exit", "end")] == \
            ["interface GigabitEthernet2", "no load-interval 30"], sent
        assert ctx.removals["203.0.113.12"]["units"][0]["line"].strip() == "load-interval 30"
        assert "no load-interval 30" in ctx.params["allowed_dangerous"]
        _r, out = _get(out_of_band, f"/v2/device/r2/deploy/job/{job}")
        assert "op-ok" in out, {k: v for k, v in capture_job.get(job).items()
                                if k in ("error", "detail", "result", "reason")}


class TestTheConfirm:
    def _confirm(self, lab, vals, **change):
        return lab["client"].post("/v2/device/r2/deploy/confirm", data=dict(vals, **change))

    def test_it_runs_as_a_job_as_the_person_and_draws_the_result(self, deploy, monkeypatch):
        from modules.nsot import capture_job
        sent = []
        reached = _spy(monkeypatch, sent_hash=sent)
        _r, plain = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        rid = _residue_id(plain)
        _r, card = _get(deploy, f"/v2/device/r2/deploy?rm={rid}"
                        "&why::{rid}=left+over+from+the+old+design".replace("{rid}", rid)
                        + _reasons())
        # The device path sends exactly the program confirmed (the pipeline's own hash).
        sent.append(_vals(card)["command_hash"])
        r = self._confirm(deploy, _vals(card))
        assert r.status_code == 200
        waiting = r.get_data(as_text=True)
        assert "Deploying to r2" in waiting and "data-run-stepper" in waiting
        assert "nmas:deploy_job from:body, nmas:device_progress from:body" in waiting
        job = re.search(r"/deploy/job/([0-9a-f]+)", waiting).group(1)
        assert capture_job.get(job)["kind"] == "deploy", "never 'monitoring profile apply'"
        assert capture_job.wait(job, 20)
        assert [x["device"] for x in reached] == ["r2"] and reached[0]["scope"] == ""
        lines = {a["line"]: a["reason"] for a in reached[0]["authorise"]["r2"]}
        assert lines.get("shutdown") == "the link is being retired"
        assert any("load-interval" in k and v == "left over from the old design" for k, v in lines.items())
        _r, out = _get(deploy, f"/v2/device/r2/deploy/job/{job}")
        assert "Deploy to r2" in out and "op-ok" in out and "Open in History" in out
        assert "hx-trigger" not in out, "a finished deploy listens for nothing"

    def test_a_program_that_moved_is_refused_with_nothing_sent(self, deploy, monkeypatch):
        from modules.nsot import capture_job
        reached = _spy(monkeypatch)
        _r, card = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        r = self._confirm(deploy, _vals(card), command_hash="0" * 16)
        job = re.search(r"/deploy/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 20)
        assert reached == [], "nothing was sent"
        _r, out = _get(deploy, f"/v2/device/r2/deploy/job/{job}")
        assert "refused" in out and "op-ok" not in out
        # The refusal's reason reaches the screen, naming which side moved and that nothing was
        # sent (rebased from today's wizard's result, tests/test_deploy_plan_apply_seam.py's
        # TestTheSpecificReasonReachesTheSCREEN, when the wizard left at 7.8).
        text = html_mod.unescape(out)
        assert "the exact command list changed since you confirmed it" in text, text[-1500:]
        assert "captured config is unchanged" in text and "intent or the template" in text
        assert "Nothing was sent" in text

    def test_a_failed_verify_rolled_back_offers_its_two_ways_out(self, deploy, monkeypatch):
        from modules.nsot import capture_job
        _spy(monkeypatch, outcome="failed",
             rollback={"state": "restored",
                       "detail": "the rollback undid what landed and read r2 back as it was"})
        _r, card = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        r = self._confirm(deploy, _vals(card))
        job = re.search(r"/deploy/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 20)
        _r, out = _get(deploy, f"/v2/device/r2/deploy/job/{job}")
        assert "Rolled back" in out and "read r2 back as it was" in out
        assert 'data-next-acts="revert"' in out and 'data-next-acts="retry"' in out
        # The two ways out open their cards here (board 11), in place of this one.
        assert 'hx-get="/v2/device/r2/revert?back=' in out and 'hx-get="/v2/device/r2/retry?back=' in out
        assert "op=revert" in out and "op=retry" in out

    @pytest.mark.parametrize("state, badge", [
        ("restored", "Rolled back"),
        ("nothing_to_undo", "Rolled back"),
        ("incomplete", "Rollback incomplete"),
        ("sent_unverified", "Rollback not read back"),
        ("failed", "Rollback failed"),
    ])
    def test_the_headline_says_rolled_back_only_when_the_rollback_restored(
            self, deploy, monkeypatch, state, badge):
        """C1268: a rollback that did not restore the device (incomplete, sent but not read back,
        failed) was headed "Rolled back", its state only in the line beneath, so a device left
        half-changed read as restored at a glance. The headline names the state."""
        from modules.nsot import capture_job
        _spy(monkeypatch, outcome="failed", rollback={"state": state, "detail": "as recorded"})
        _r, card = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        r = self._confirm(deploy, _vals(card))
        job = re.search(r"/deploy/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 20)
        _r, out = _get(deploy, f"/v2/device/r2/deploy/job/{job}")
        head = re.search(r'<h2 id="op-title">(.*?)</h2>', out, re.S).group(1)
        assert re.sub(r"<[^>]+>", " ", head).split("Deploy to r2", 1)[1].strip() == badge, head

    def test_the_result_draws_verify_s_scope_and_each_line_not_read_back(self, deploy,
                                                                         monkeypatch):
        """C1270: verify's scope (quick or full, and why), how many new lines it read back, and
        each line it did not, drawn on the card, as today's renderer drew them."""
        import routes.deploy as rd
        from modules.nsot import capture_job

        def spy(entry, list_name, rows, authorise, **kw):
            return {"device": entry["artifact"].device, "outcome": "failed",
                    "commands": ["lldp run", "lldp timer 20"], "stage": "verify",
                    "verify": {"ok": False, "checked_protocols": [],
                               "verify_scope": {"scope": "quick",
                                                "why": "management and services lines only"},
                               "read_back": {"checked": 2, "missing": ["lldp timer 20"],
                                             "skipped": []}},
                    "reason": "1 sent line(s) did not read back: lldp timer 20"}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        _r, card = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        r = self._confirm(deploy, _vals(card))
        job = re.search(r"/deploy/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 20)
        _r, out = _get(deploy, f"/v2/device/r2/deploy/job/{job}")
        text = re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", out)))
        assert "Verify was quick: management and services lines only" in text, text[-1500:]
        assert "2 new line(s) looked for, 1 read back" in text, text[-1500:]
        assert "Not read back: lldp timer 20" in text, text[-1500:]

    @pytest.mark.parametrize("change, words", [
        ({"list": ""}, "names no list"),
        ({"list": "Nowhere"}, "names no list"),
        ({"command_hash": ""}, "no program to be bound to"),
        # Lab 7 (b), the second sample (a hand mutant: mutmut makes none of a decorated route):
        # the capture hash is half of what the preview showed, and a confirm without it is
        # refused here, never handed to the job.
        ({"capture_hash": ""}, "no program to be bound to"),
    ])
    def test_a_confirm_without_its_list_or_hash_is_refused(self, deploy, monkeypatch, change,
                                                           words):
        reached = _spy(monkeypatch)
        _r, card = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        r = self._confirm(deploy, _vals(card), **change)
        assert r.status_code in (400, 404) and words in r.get_data(as_text=True)
        assert reached == []


@pytest.fixture(scope="module")
def live_browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


CARD = "document.getElementById('device-op')"
#: C2142: the scenario's own precondition, the operator's bar (C1434), and how many attempts it
#: gets before the test says inconclusive (the operator, 2026-10-29).
PRECONDITION_MS = 100
PRECONDITION_TRIES = 3
#: htmx binds a swapped-in control while it settles: click only once nothing settles.
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


class TestInARealBrowser:
    def test_plan_give_the_reason_confirm_and_the_result_arrives_in_place(
            self, deploy, live_browser, monkeypatch):
        """The path a person takes: "Plan a deploy…", the dangerous line's reason typed (Deploy
        is offered as it is typed, and plans again with it when pressed, C1434), the confirm,
        the stepper, the result by the job's announcement, the page never reloaded."""
        browser, srv, b = live_browser
        sent = []
        reached = _spy(monkeypatch, sent_hash=sent)
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r2"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       "NMAS.live().state === 'connected' && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            # "Plan a deploy…" is the Actions menu's first row (2026-10-05), no separate button.
            b.click('.page-actions button[aria-haspopup="menu"]')
            b.wait_for("var m = document.querySelector('.page-actions [role=menu]');"
                       "return m && m.offsetParent !== null", 10)
            b.click('.page-actions a[data-op="deploy"]')
            b.wait_for(f"return {CARD} && {CARD}.querySelector('input[name=\"dz::0\"]') "
                       f"&& {SETTLED}", 15)
            b.js("var i = document.querySelector('input[name=\"dz::0\"]');"
                 "i.value = 'the link is being retired';"
                 "i.dispatchEvent(new Event('input', {bubbles: true}));"
                 "i.dispatchEvent(new Event('change', {bubbles: true})); return 1")
            b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm:not([disabled])') "
                       f"&& {SETTLED}", 15)
            # The program the press binds is the plan with that reason: one plan, one hash.
            _r, planned = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
            sent.append(_vals(planned)["command_hash"])
            b.click("#device-op .op-confirm")
            b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}",
                       30)
            assert "Deploy to r2" in b.js(f"return {CARD}.textContent")
            assert b.js("return window.__notReloaded") == 1
            assert [x["device"] for x in reached] == ["r2"]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()

    def test_a_why_typed_and_deploy_pressed_at_once_sends_that_why(self, walk_s1, live_browser,
                                                                   monkeypatch):
        """C1434, the operator's bar (2026-10-26): on the walk's switch, the line ticked for
        removal, its Why typed with real keys and Deploy pressed within 100 ms of the last one
        (the key and the press in ONE WebDriver actions call, no round trip between). The press
        is never lost: the job carries that Why as the removal's authorisation, the pipeline is
        handed exactly Gi1/1's removal, and the result arrives in place."""
        browser, srv, b = live_browser
        seen, authorised = _spy_pipeline(monkeypatch)
        why = "left over from the old design"
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            # C2142 (the operator, 2026-10-29): the 100 ms bar is this scenario's precondition,
            # not the product's result. A press that lands past it did not test the race, so
            # the scenario runs again on a fresh page, at most PRECONDITION_TRIES times; every
            # attempt missing it is inconclusive, never a pass. The product is judged only on an
            # attempt that met it.
            gaps = []
            for _attempt in range(PRECONDITION_TRIES):
                seen.clear()
                authorised.clear()
                t = self._type_why_and_press(b, srv, why)
                if t.get("pressed") is None:
                    break                       # the press was lost: judged below, a failure
                gaps.append(round(t["pressed"] - t["typed"], 1))
                if 0 <= gaps[-1] < PRECONDITION_MS:
                    break
            else:
                pytest.skip(f"inconclusive (C2142): Deploy was never pressed within "
                            f"{PRECONDITION_MS} ms of the last key in {PRECONDITION_TRIES} "
                            f"tries (gaps {gaps} ms); the race was not tested")
            assert t.get("pressed") is not None and 0 <= t["pressed"] - t["typed"] < 100, t
            assert "op-ok" in b.js(f"return {CARD}.className"), b.js(f"return {CARD}.textContent")
            assert b.js("return window.__notReloaded") == 1
            assert authorised == [{"s1": [{"line": "no load-interval 30", "reason": why}]}]
            assert len(seen) == 1 and _program(seen[0], S1_IP) == [
                "interface GigabitEthernet1/1", " no load-interval 30"]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


    def _type_why_and_press(self, b, srv, why):
        """One attempt of the scenario on a freshly loaded page: Gi1/1 ticked for removal, its
        Why typed with real keys, the last key and Deploy's press in one actions call, and the
        result waited for. Returns the page's timings (`typed`, `pressed`)."""
        b.go(srv.url("/v2/device/s1?op=deploy"))
        b.wait_for("return !!window.Alpine && window.NMAS && "
                   f"NMAS.live().state === 'connected' && {CARD} && " + SETTLED, 15)
        b.js("window.__notReloaded = 1; return 1")
        rid = _residue_box(b)
        b.click(f"#rm-{rid}")
        field = f'#device-op input[name="why::{rid}"]'
        press = "#device-op button[data-needs]"
        b.wait_for(f"return document.querySelector('{field}') && {SETTLED}", 15)
        assert b.js(f"return document.querySelector('{press}').disabled") is True, \
            "no Why yet: Deploy waits"
        b.js(f"var w = document.querySelector('{field}'), t = window.__t = {{}};"
             "w.addEventListener('input', function () { t.typed = performance.now(); });"
             "document.addEventListener('click', function (e) {"
             f"  if (e.target.closest && e.target.closest('{press}') && !t.pressed)"
             "    t.pressed = performance.now(); }, true); return 1")
        b.type(field, why[:-1])
        # Deploy in view for the pointer, the field keeping the focus (and its caret).
        assert b.js(f"document.querySelector('{press}').scrollIntoView({{block: 'center'}});"
                    f"return document.activeElement === document.querySelector('{field}')"), \
            "the field lost its focus while the Why was typed"
        _type_and_press(b, why[-1], press)
        b.wait_for(f"return {CARD} && /op-(ok|warn|danger)/.test({CARD}.className) "
                   f"&& {SETTLED}", 30)
        return b.js("return window.__t")

    def test_the_checks_follow_the_why_and_deploy_follows_the_checks(self, walk_s1,
                                                                     live_browser,
                                                                     monkeypatch):
        """C1847, the operator's Mode B re-walk (2026-10-27): with the Why typed, the card
        drew "lines needing a reason: fail" and "Authorised lines 0" beside an enabled
        Deploy. On the walk's switch: the Why typed with real keys, the card plans again
        once after the last key, and the check reads pass with "authorised lines" 1, Deploy
        offered; the Why cleared, the check fails again and Deploy is disabled; typed again
        and pressed, the job succeeds with that Why. Throughout, a watcher on every change
        of the page counts any moment a failing check is drawn beside an enabled Deploy:
        none. The operator's bar is 1 s from the last key to the check reading pass; the
        test asserts the work (one plan per pause in typing, REPLAN_MS 300 ms after the
        last key) and prints the time it took, never a wall-clock bound (CLAUDE.md,
        performance tests)."""
        import time as _time
        browser, srv, b = live_browser
        seen, authorised = _spy_pipeline(monkeypatch)
        why = "Mode B test"
        gate = "#device-op #deploy-checks [data-reason-gate]"
        auth = '#device-op #deploy-operands [data-operand="authorised lines"]'
        press = "#device-op button[data-needs]"
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/s1?op=deploy"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       f"NMAS.live().state === 'connected' && {CARD} && " + SETTLED, 15)
            rid = _residue_box(b)
            b.click(f"#rm-{rid}")
            field = f'#device-op input[name="why::{rid}"]'
            b.wait_for(f"return document.querySelector('{field}') && {SETTLED}", 15)
            b.js("window.__both = 0; window.__plans = 0;"
                 "var f = window.fetch; window.fetch = function (u) {"
                 "  if (String(u).indexOf('/deploy?') >= 0) window.__plans++;"
                 "  return f.apply(this, arguments); };"
                 "var look = function () { var c = document.getElementById('device-op');"
                 "  var d = c && c.querySelector('button[data-needs]');"
                 "  if (d && !d.disabled && c.querySelector('#deploy-checks [data-gate=\"fail\"]'))"
                 "    window.__both++; };"
                 "new MutationObserver(look).observe(document.body, {subtree: true,"
                 "  childList: true, attributes: true, characterData: true}); return 1")

            def state():
                return b.js(f"var g = document.querySelector('{gate}'),"
                            f" a = document.querySelector('{auth}'),"
                            f" d = document.querySelector('{press}');"
                            "return [g && g.getAttribute('data-gate'), a && a.textContent.trim(),"
                            " d && !d.disabled, window.__plans, window.__both]")
            assert state() == ["fail", "0", False, 0, 0], state()
            b.type(field, why)
            typed = _time.monotonic()
            b.wait_for(f"var g = document.querySelector('{gate}');"
                       "return g && g.getAttribute('data-gate') === 'pass'", 10)
            took = _time.monotonic() - typed
            print(f"C1847: the check read pass {took:.2f} s after the last key")
            s = state()
            assert s[:3] == ["pass", "1", True] and s[3] >= 1 and s[4] == 0, s
            plans = s[3]
            assert b.js(f"return document.activeElement === document.querySelector('{field}')"), \
                "the field kept its focus"
            # Cleared: the check fails again and Deploy is disabled.
            b.js(f"var w = document.querySelector('{field}'); w.value = '';"
                 "w.dispatchEvent(new Event('input', {bubbles: true})); return 1")
            assert b.js(f"return document.querySelector('{press}').disabled") is True
            b.wait_for(f"var g = document.querySelector('{gate}');"
                       "return g && g.getAttribute('data-gate') === 'fail'", 10)
            s = state()
            assert s[:3] == ["fail", "0", False] and s[3] > plans and s[4] == 0, s
            plans = s[3]
            # Text the server refuses (a reason is at least three words): the box holds text,
            # the drawn check fails, and Deploy follows the check, not the box.
            b.type(field, "x")
            b.wait_for(f"return window.__plans > {plans} && document.querySelector('{gate}')"
                       ".getAttribute('data-gate') === 'fail'", 10)
            s = state()
            assert s[0] == "fail" and s[2] is False and s[4] == 0, s
            plans = s[3]
            b.js(f"var w = document.querySelector('{field}'); w.value = '';"
                 "w.dispatchEvent(new Event('input', {bubbles: true})); return 1")
            b.type(field, why)
            b.wait_for(f"var g = document.querySelector('{gate}');"
                       "return g && g.getAttribute('data-gate') === 'pass'", 10)
            s = state()
            assert s[:3] == ["pass", "1", True] and s[3] > plans and s[4] == 0, s
            b.click(press)
            b.wait_for(f"return {CARD} && /op-(ok|warn|danger)/.test({CARD}.className) "
                       f"&& {SETTLED}", 30)
            assert "op-ok" in b.js(f"return {CARD}.className"), b.js(f"return {CARD}.textContent")
            assert b.js("return window.__both") == 0
            assert authorised == [{"s1": [{"line": "no load-interval 30", "reason": why}]}]
            assert len(seen) == 1 and _program(seen[0], S1_IP) == [
                "interface GigabitEthernet1/1", " no load-interval 30"]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()

    def test_one_reason_then_another_typed_keeps_the_focus_and_every_key(
            self, deploy, live_browser, monkeypatch):
        """C1434: the card is never redrawn while a person types. On r2 (a dangerous line and
        a ticked removal, two reasons), the first reason typed with real keys, then the second
        field clicked and typed: leaving the first plans nothing, so the second keeps its focus
        and every key; Deploy then sends both reasons."""
        browser, srv, b = live_browser
        sent = []
        reached = _spy(monkeypatch, sent_hash=sent)
        first, second = "the link is being retired", "left over from the old design"
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r2?op=deploy"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       f"NMAS.live().state === 'connected' && {CARD} && " + SETTLED, 15)
            rid = _residue_box(b)
            b.click(f"#rm-{rid}")
            field = f'#device-op input[name="why::{rid}"]'
            b.wait_for(f"return document.querySelector('{field}') && {SETTLED}", 15)
            b.js("window.__asked = 0; document.addEventListener('htmx:beforeRequest', "
                 "function () { window.__asked++; }); return 1")
            b.type('#device-op input[name="dz::0"]', first)
            b.click(field)
            b.type(field, second, pause=0.02)
            got = b.js(f"var f = document.querySelector('{field}'); return [f.value, "
                       "document.activeElement === f, window.__asked, document.querySelector("
                       "'#device-op input[name=\"dz::0\"]').value]")
            assert got == [second, True, 0, first], got
            _r, planned = _get(deploy, f"/v2/device/r2/deploy?rm={rid}&why::{rid}={second}"
                               + _reasons(first))
            sent.append(_vals(planned)["command_hash"])
            b.click("#device-op button[data-needs]")
            b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}",
                       30)
            lines = {a["line"]: a["reason"] for a in reached[0]["authorise"]["r2"]}
            assert lines == {"shutdown": first, "no load-interval 30": second}, lines
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def _residue_box(b, text="load-interval 30"):
    """The id of the box the drawn card offers for the residue line *text*."""
    rid = b.js("var want = arguments[0], b = Array.prototype.find.call("
               "document.querySelectorAll('#device-op input[name=rm]'), function (i) {"
               "  var l = document.querySelector('label[for=\"' + i.id + '\"]');"
               "  return l && l.textContent.indexOf(want) >= 0; });"
               "return b && b.value", text)
    assert rid, "the residue line has its box"
    return rid


#: WebDriver's element reference key.
ELEMENT = "element-6066-11e4-a52e-4f735466cecf"


def _type_and_press(b, text, css):
    """Type *text* into the focused field and press *css* in ONE WebDriver actions call: each
    key down and up, then the pointer moved to the button, down and up, on consecutive ticks,
    as a person who types the last letter and clicks at once."""
    el = b._call("POST", f"/session/{b.session}/element", {"using": "css selector", "value": css})
    ref = next(iter(el.values()))
    keys = [a for ch in text for a in ({"type": "keyDown", "value": ch},
                                       {"type": "keyUp", "value": ch})]
    pause = {"type": "pause", "duration": 0}
    pointer = [pause] * len(keys) + [
        {"type": "pointerMove", "duration": 0, "origin": {ELEMENT: ref}, "x": 0, "y": 0},
        {"type": "pointerDown", "button": 0}, {"type": "pointerUp", "button": 0}]
    from urllib.error import HTTPError
    try:
        b._call("POST", f"/session/{b.session}/actions", {"actions": [
            {"type": "key", "id": "keyboard", "actions": keys + [pause] * 3},
            {"type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
             "actions": pointer}]})
    except HTTPError as exc:          # the driver's own words, not only its status
        raise AssertionError(f"the actions call was refused: {exc.read()[:600]!r}") from exc
    b._call("DELETE", f"/session/{b.session}/actions")
