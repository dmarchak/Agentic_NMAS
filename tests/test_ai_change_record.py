"""A change record drafted in the deploy preview (PHASE8_PLAN 16.11 item 3, Decision 5; board CR,
`ChangeRecordDraft.dc.html`; modules/ai/change_record.py), on tests/test_device_deploy_v2's lab
(r2's REAL capture and intent, edited so the program sends `lldp run` and a dangerous `shutdown`
on GigabitEthernet3), the gateway allowed with a fake `send`.

- What leaves the host: the program's shape in keywords and Mercury's own words, the allowed
  keys only; no value of the program, no stated reason, no address of r2's configuration, and a
  planted secret's line left out whole, counted, never in the bytes sent.
- The press: the preview planned again from the card's form, bound to the hash the card drew
  (a moved program sends nothing), one recorded call, trigger person; the draft drawn in place,
  each section marked Mercury or AI, the program's lines and the rollback the pipeline would
  run filled by Mercury; Deploy bound to the same program with or without it.
- Mercury's check: words naming an interface the program does not touch, another device, or
  quoting a configuration line are refused, never drawn; the call kept.
- The draft carried on a re-plan: drawn again from its call, stale when the program moved.
- Download (.md) is the draft as text, read from its call; the AI control's states.
"""
import html as html_mod
import json
import re

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, change_record, gateway
from tests.ai_person import PERSON, pressed_by

KEY = "sk-planted-test-key-0123456789"
WORDS = {"summary": "Enables LLDP on r2 and shuts GigabitEthernet3.",
         "risk": "Shutting GigabitEthernet3 takes its link down; verify reads it down and "
                 "watches every other interface and the route table against the moment before.",
         "mentions": ["r2", "GigabitEthernet3"]}
REASON = "the link is being retired"


def deploy_world(monkeypatch, tmp_path) -> dict:
    """tests/test_device_deploy_v2's `deploy` lab (r2's real capture: `lldp run` and a dangerous
    `shutdown` to send), hosted AI allowed with a key, the record of AI calls in *tmp_path*, and
    the provider replaced by a fake (``sent``: every request; ``state["answer"]``: the reply)."""
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    from tests.test_profile_apply import lab_setup

    lab = lab_setup(monkeypatch, tmp_path)
    real = lab["captured"]
    golden = real.replace("\nlldp run\n", "\n").replace(
        "\ninterface GigabitEthernet2\n", "\ninterface GigabitEthernet2\n load-interval 30\n")
    assert save_golden("Lab", [GoldenItem("r2", golden, "203.0.113.12", platform="cisco_iosxe")],
                       source="capture", actor="t", baseline=False).get("commit")
    intent = real.replace("\ninterface GigabitEthernet3\n",
                          "\ninterface GigabitEthernet3\n shutdown\n")
    hostvars.write_committed(lab["repo"], get_parser("cisco_iosxe").parse(intent))
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    # r5 is a device of the network this deploy does not change (what the draft may not name).
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"},
               {"hostname": "r5", "ip": "203.0.113.15", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"}]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in devices])
    lab["settings"].update(ai_hosted={"by": PERSON, "at": "2026-10-25T05:00:00Z",
                                      "reason": "the lab's proof of concept"},
                           ai_cap_usd_per_day=1.50)
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    sent, state = [], {"answer": dict(WORDS)}

    def send(body, key):
        sent.append({"bytes": json.dumps(body), "body": body})
        return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
            state["answer"])}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 1500, "output_tokens": 120}}, attempts=1, latency_s=0.2)
    monkeypatch.setattr(A, "send", send)
    lab.update(sent=sent, state=state, golden=golden)
    return lab


@pytest.fixture
def world(monkeypatch, tmp_path):
    return deploy_world(monkeypatch, tmp_path)


def _card(world, query=f"&dz::0={REASON}"):
    r = world["client"].get("/v2/device/r2/deploy?back=overview" + query)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _program_hash(card):
    m = re.search(r"data-op=\"change-record\"[^>]*?hx-vals='([^']*)'", card)
    assert m, "the control carries the program the card drew"
    return json.loads(html_mod.unescape(m.group(1)))["program_hash"]


def _confirm_hash(card):
    m = re.search(r"hx-vals='([^']*)'", card[card.index("op-confirm"):])
    return json.loads(html_mod.unescape(m.group(1)))["command_hash"]


def _press(world, program_hash=None, reason=REASON, extra=None):
    card = _card(world, f"&dz::0={reason}")
    data = {"back": "overview", "plan": "card", "dz::0": reason,
            "program_hash": _program_hash(card) if program_hash is None else program_hash}
    data.update(extra or {})
    r = world["client"].post("/v2/device/r2/deploy/change-record", data=data,
                             headers={"HX-Request": "true"})
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _data_block(body, name):
    user = body["messages"][0]["content"]
    m = re.search(r'<data name="' + re.escape(name) + r'">\n?(.*?)\n?</data>', user, re.S)
    assert m, f"no data block {name!r}"
    return m.group(1)


# ── What leaves the host ─────────────────────────────────────────────────────────────────

class TestWhatLeaves:
    def test_the_request_is_the_prompt_and_the_change_s_shape_only(self, world):
        from modules.ai import prompts
        _press(world)
        assert len(world["sent"]) == 1, "one press, one request"
        body = world["sent"][0]["body"]
        assert body["system"][0]["text"] == prompts.load(*change_record.PROMPT)["text"]
        user = body["messages"][0]["content"]
        assert re.findall(r'<data name="([^"]+)">', user) == ["change"]
        change = json.loads(_data_block(body, "change"))
        assert sorted(change) == sorted(change_record.SENT_KEYS)
        assert change["device"] == "r2" and change["interfaces_touched"] == ["GigabitEthernet3"]
        sections = change["program"]["sections"]
        assert {"kind": "interface", "name": "GigabitEthernet3", "settings": ["shutdown"],
                "lines": 1} in sections
        assert change["counts"]["needing_a_stated_reason"] == 1

    def test_no_reason_no_value_and_no_address_of_the_configuration_is_sent(self, world):
        _press(world)
        sent = world["sent"][0]["bytes"]
        assert REASON not in sent, "a stated reason a person typed is never sent"
        change = json.loads(_data_block(world["sent"][0]["body"], "change"))
        # The preview's own words sent with it (the topology class): a verify check names the
        # neighbour it reads, by its router id; nothing else of r2's configuration is sent.
        topology = json.dumps([change["verify_checks"], change["expected_effects"]])
        held = re.findall(r"^ ip address (\S+)", world["captured"], re.M)
        described = re.findall(r"^ description (.+)$", world["captured"], re.M)
        assert len(held) >= 3 and len(described) >= 3, "the floor: r2's real addresses"
        for text in held + described:
            assert text not in sent or text in topology, text
            assert text not in json.dumps(change["program"]), text
        assert "load-interval" not in sent, "what is left on the device is not the program"

    def test_a_planted_secret_s_line_is_left_out_whole_and_never_in_the_bytes(self, monkeypatch,
                                                                            world):
        """The egress test (15.11 condition 1 and 2): a program carrying a community, an enable
        secret and a known stored value: each line left out of the shape, counted, and none of
        the three values in the bytes the adapter was handed."""
        planted = {"community": "plantedcommunity42", "secret": "plantedsecret77",
                   "known": "plantedknownvalue99"}
        commands = ["lldp run", f"snmp-server community {planted['community']} RO",
                    f"enable secret 9 $9${planted['secret']}",
                    f"ntp authentication-key 1 md5 {planted['known']}",
                    "interface GigabitEthernet3", " shutdown", "exit"]
        values = {"planted_known": planted["known"]}
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: dict(values))
        f = change_record.facts(
            host="r2", network="Lab", platform="cisco_iosxe", program_hash="a" * 64,
            lines=commands, commands=commands, captured=world["golden"], effects={},
            derived=[], checks=[], authorised=[], removals=0, values=values)
        assert f["shape"]["left_out"] == 3
        with pressed_by(PERSON):
            got = change_record.draft(f, actor=PERSON, trigger={"kind": "person", "by": PERSON},
                                      shown_hash="a" * 64, known=["r2"])
        assert got["ok"], got
        sent = world["sent"][-1]["bytes"]
        for value in planted.values():
            assert value not in sent, value
        change = json.loads(_data_block(world["sent"][-1]["body"], "change"))
        assert change["program"]["left_out_carrying_a_secret"] == 3
        # The control (able to fail): the shape without the left-out rule holds the community.
        assert planted["community"] in json.dumps(
            [l for l in commands if "community" in l]), "the plant is in the program"

    def test_a_network_whose_topology_class_is_off_sends_nothing(self, monkeypatch, world):
        monkeypatch.setattr("modules.ai.egress_classes.topology_allowed",
                            lambda network: {"allowed": False, "why": "planted: off for Lab"})
        page = _press(world)
        assert world["sent"] == []
        assert "Couldn't draft: planted: off for Lab" in html_mod.unescape(page)


class TestKeywords:
    @pytest.mark.parametrize("line, words", [
        ("ipv6 ospf 1 area 0", "ipv6 ospf"),
        ("ip address 192.0.2.1 255.255.255.0", "ip address"),
        ("ipv6 address 2001:DB8::1/64", "ipv6 address"),
        ("description spare port desk 4", "description"),
        ("no shutdown", "no shutdown"),
        ("switchport trunk encapsulation dot1q", "switchport trunk"),
        ("snmp-server location rack-7", "snmp-server location"),
        ("ntp server 192.0.2.10", "ntp server"),
        ("ipv6 route 2001:DB8:5::/48 Null0", "ipv6 route"),
        ("hostname R3", "hostname"),
    ])
    def test_a_line_s_keywords_hold_no_value(self, line, words):
        assert change_record.keywords(line) == words

    def test_the_risk_rule(self):
        assert change_record.risk(reasons=[], removals=0, protocols=[], drops=0,
                                  down=[])["level"] == "low"
        assert change_record.risk(reasons=["shutdown"], removals=0, protocols=[], drops=0,
                                  down=["GigabitEthernet3"])["level"] == "medium"
        assert change_record.risk(reasons=[], removals=0, protocols=["ospfv3"], drops=0,
                                  down=[])["level"] == "medium"
        assert change_record.risk(reasons=[], removals=1, protocols=[], drops=0,
                                  down=[])["level"] == "high"
        hi = change_record.risk(reasons=["shutdown"], removals=0, protocols=["ospf"], drops=1,
                                down=["GigabitEthernet3"])
        assert hi["level"] == "high" and "1 adjacency expected to drop" in hi["rule"]


# ── The press and the draft ──────────────────────────────────────────────────────────────

class TestThePress:
    def test_the_card_offers_it_between_checks_and_the_confirm(self, world):
        card = _card(world)
        assert card.index('id="deploy-checks"') < card.index('id="change-record-part"') \
            < card.index('class="op-ft"')
        assert 'data-ai-control="change_record"' in card
        assert "Draft a change record" in card and 'data-op="change-record"' in card
        assert world["sent"] == [], "drawing the card asks no model"

    def test_a_press_draws_mercury_s_facts_and_the_model_s_words(self, world):
        page = html_mod.unescape(_press(world))
        assert "DRAFT by AI" in page and "Advisory (beta)" in page
        assert WORDS["summary"] in page and WORDS["risk"] in page
        for section in ("Summary", "Scope", "Risk", "Implementation", "Verification",
                        "Rollback plan", "Window and approver", "Status"):
            assert f"<h4>{section}" in page, section
        assert 'cr-src-mercury">Mercury<' in page and 'cr-src-ai">AI<' in page
        assert "lldp run" in page and " shutdown" in page, "the program's lines, Mercury's"
        assert "no lldp run" in page and "no shutdown" in page, "the rollback, Mercury's"
        assert f"“{REASON}”" in page, "the stated reason, Mercury's"
        assert 'name="cr"' in page and 'form="deploy-form"' in page
        assert "Was this right?" in page
        actor = calls.read()["rows"][0]["actor"]
        assert f"trigger person ({actor})" in page and "@" in actor

    def test_the_call_is_a_person_s_about_the_device_and_its_program(self, world):
        _press(world)
        rows = calls.read()["rows"]
        assert len(rows) == 1
        row = rows[0]
        assert row["feature"] == "change_record" and row["verdict"] == "ok"
        assert row["trigger"]["kind"] == "person" and row["trigger"]["by"] == row["actor"]
        assert "@" in row["actor"], "a person's press, recorded as that person"
        assert row["subject"]["kind"] == "deploy_preview" and row["subject"]["devices"] == ["r2"]
        assert REASON in json.dumps(row["subject"]["preview"]), "drawn again from its call"
        uses = calls.uses()[row["id"]]
        assert [u["use"] for u in uses] == ["shown: drafted"]

    def test_deploy_is_bound_to_the_same_program_with_or_without_a_draft(self, world):
        before = _confirm_hash(_card(world))
        page = _press(world)
        call = re.search(r'name="cr" value="([^"]+)"', page).group(1)
        after = _card(world, f"&dz::0={REASON}&cr={call}")
        assert _confirm_hash(after) == before
        assert "DRAFT by AI" in after, "the carried draft is drawn again"

    def test_a_moved_program_sends_nothing_and_names_both_hashes(self, world):
        page = html_mod.unescape(_press(world, program_hash="0" * 64))
        assert world["sent"] == []
        assert "Couldn't draft: the preview moved: the card drew program 000000000000" in page

    def test_a_reason_typed_since_makes_the_draft_stale(self, world):
        page = _press(world)
        call = re.search(r'name="cr" value="([^"]+)"', page).group(1)
        stale = html_mod.unescape(_card(world, f"&dz::0=another reason&cr={call}"))
        assert "This draft is for program" in stale and "no longer match" in stale
        assert "cr-doc-stale" in stale and 'name="cr"' in stale

    def test_download_is_the_draft_as_text_read_from_its_call(self, world):
        page = _press(world)
        call = re.search(r'name="cr" value="([^"]+)"', page).group(1)
        r = world["client"].get(f"/v2/device/r2/deploy/change-record/{call}.md")
        assert r.status_code == 200 and r.mimetype == "text/markdown"
        text = r.get_data(as_text=True)
        assert "## Rollback plan (Mercury)" in text and "no shutdown" in text
        assert WORDS["summary"] in text
        assert world["client"].get(
            "/v2/device/r2/deploy/change-record/ai-nonesuch.md").status_code == 404


class TestMercurysCheck:
    @pytest.mark.parametrize("words, said", [
        ({"summary": "Shuts GigabitEthernet3 and Gi1.", "risk": "", "mentions": []},
         "the answer named GigabitEthernet1, which the program does not touch"),
        ({"summary": "Shuts GigabitEthernet3, the link to r5.", "risk": "", "mentions": []},
         "the answer named r5, a device this deploy does not change"),
        ({"summary": "Shuts GigabitEthernet3.", "risk": "", "mentions": ["r5"]},
         "the answer named r5, a device this deploy does not change"),
        ({"summary": "Shuts GigabitEthernet3.", "risk": "", "mentions": ["GigabitEthernet9"]},
         "the answer named GigabitEthernet9, which the program does not touch"),
        ({"summary": "Adds `ip ospf cost 5` on GigabitEthernet3.", "risk": "",
          "mentions": []}, "the answer quoted 'ip ospf cost 5' as a line"),
        ({"summary": "", "risk": "", "mentions": []}, "the answer has no summary"),
    ])
    def test_words_naming_what_the_change_does_not_hold_are_refused(self, world, words, said):
        world["state"]["answer"] = words
        page = html_mod.unescape(_press(world, extra={}))
        assert f"Couldn't draft: {said}" in page
        assert "DRAFT by AI" not in page, "a refused draft is never drawn"
        row = calls.read()["rows"][0]
        assert [u["use"] for u in calls.uses()[row["id"]]] == ["refused by validation"]

    def test_words_naming_only_the_change_and_what_its_preview_names_pass(self, world):
        f = {"host": "r2", "interfaces": ["GigabitEthernet3"], "derived": [],
             "checks": [{"check": "OSPF to r6 (192.0.2.6) over GigabitEthernet2",
                         "expects": "held", "read": "within OSPF's settle window"}]}
        ok = change_record.ChangeRecordWords(**WORDS)
        assert change_record.check(ok, f, known=["r2", "r5", "r6"]) == ""
        watched = change_record.ChangeRecordWords(
            summary="Shuts GigabitEthernet3 on r2.",
            risk="Verify holds the OSPF adjacency to r6 over GigabitEthernet2.",
            mentions=["r2", "r6", "GigabitEthernet2"])
        assert change_record.check(watched, f, known=["r2", "r5", "r6"]) == ""
        # The control: the same words with no check naming r6 and Gi2 are refused.
        bare = dict(f, checks=[])
        assert "GigabitEthernet2" in change_record.check(watched, bare, known=["r2", "r6"])


def test_the_control_is_an_ai_control_and_the_preview_stays_usable(world, monkeypatch):
    """15.13 in the deploy preview: ready, Draft a change record live; not ready (each kind),
    disabled with the reason, and the preview's own controls (its reason box, Preview it
    again) drawn as ever."""
    from tests import ai_controls_check as AIC

    def get():
        return _card(world, "")

    def parity(html):
        assert 'name="dz::0"' in html, "the preview's reason box drawn"
        assert "Deploy committed intent to r2" in html
    AIC.check_screen(monkeypatch, get, "change_record", parity)
