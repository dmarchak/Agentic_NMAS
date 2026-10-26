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


class TestTheWalksRemoval:
    """C1434, found again on the operator's Walk 3 (2026-10-26): a removal with no dangerous
    line read "not applicable" on the reason check, so Deploy was offered before the Why was
    given, and the apply refused "1 line(s) need an authorisation with a reason"."""

    def _spy_pipeline(self, monkeypatch):
        """The real apply (`routes.deploy._deploy_one`: the program computed again with its
        removals, every removal's reason checked on the path that connects), with only the
        pipeline, the part that reaches a device, replaced by a recorder that succeeds."""
        import modules.pipeline as P
        import routes.deploy as rd
        seen = []

        class _Runner:
            def __init__(self, ctx):
                self.ctx = ctx
                seen.append(ctx)

            def run(self):
                # As `PipelineRunner.run` answers: its own context, here every stage a pass.
                self.ctx.final_status = "success"
                return self.ctx
        monkeypatch.setattr(P, "PipelineRunner", _Runner)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        return seen

    def test_ticked_without_its_why_offers_no_deploy_and_names_the_line(self, out_of_band):
        _r, plain = _get(out_of_band, "/v2/device/r2/deploy?focus=removal")
        rid = _residue_id(plain, "load-interval 30")
        assert 'name="dz::' not in plain, "no dangerous line in this program"
        _r, ticked = _get(out_of_band, f"/v2/device/r2/deploy?rm={rid}")
        assert "op-confirm" not in ticked, "no Deploy for a program the apply would refuse"
        assert "waits on your stated reason for <code>no load-interval 30</code> (in its Why " \
               "box, beside the tick)" in ticked, ticked[ticked.find("Not available"):][:400]
        assert "<strong>lines needing a reason</strong>" in ticked
        button = re.search(r"<button[^>]*>Deploy \d+ line\(s\) to r2</button>", ticked)
        assert button and " disabled" in button.group(0) and "hx-post" not in button.group(0), \
            "Deploy drawn disabled, never offered"

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
#: htmx binds a swapped-in control while it settles: click only once nothing settles.
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


class TestInARealBrowser:
    def test_plan_give_the_reason_confirm_and_the_result_arrives_in_place(
            self, deploy, live_browser, monkeypatch):
        """The path a person takes: "Plan a deploy…", the dangerous line's reason typed (the
        card plans again and offers the confirm), the confirm, the stepper, the result by
        the job's announcement, the page never reloaded."""
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
                 "i.dispatchEvent(new Event('change', {bubbles: true})); return 1")
            b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
            vals = b.js("return document.querySelector('#device-op .op-confirm')"
                        ".getAttribute('hx-vals')")
            sent.append(json.loads(vals)["command_hash"])
            b.click("#device-op .op-confirm")
            b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}",
                       30)
            assert "Deploy to r2" in b.js(f"return {CARD}.textContent")
            assert b.js("return window.__notReloaded") == 1
            assert [x["device"] for x in reached] == ["r2"]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
