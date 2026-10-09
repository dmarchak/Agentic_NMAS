"""7.3's PERSIST (C164): save the running config on the device and read the
startup config back, from the Device page, over the real module, route and
recorder, with the device side faked at `onboard.persist_on_device` (the ONE
save of a startup config, whose own tests drive its session).

The remedy the worst Needs attention rows name (`not_safe_to_reboot`), until
now reachable only as `nmas-persist-native` on the host.
"""

import ast
import json
import os
import threading

import pytest

from modules.nsot import persist_op as PO
from tests.payload_render import render_preview, render_result

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW = "Persist-Pw-7h3x9q"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    import app as A
    from modules import device

    lists = tmp_path / "lists"
    list_dir = lists / "lab"
    list_dir.mkdir(parents=True)
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.LISTS_DIR", str(lists))
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    f = device.fernet
    rows = [{"hostname": "r2", "device_type": "cisco_xe", "ip": "192.0.2.12",
             "username": "admin", "password": f.encrypt(PW.encode()).decode(),
             "secret": f.encrypt(b"").decode(), "platform": "cisco_iosxe"},
            {"hostname": "s9", "device_type": "", "ip": "192.0.2.99", "username": "admin",
             "password": f.encrypt(PW.encode()).decode(), "secret": "",
             "platform": "cisco_ios"}]
    device.write_devices_csv(rows, str(list_dir / "devices.csv"))
    records = []
    monkeypatch.setattr("modules.nsot.onboard._record_native_persist",
                        lambda host, out, actor, via: records.append(
                            {"device": host, "state": out.get("state"), "actor": actor,
                             "via": via}))
    sent = []

    def persist(ip, username, password, secret, device_type):
        from modules.nsot import device_ops

        sent.append({"ip": ip, "held": device_ops.may_write(ip), "type": device_type,
                     "password_ok": password == PW})
        return dict(lab_state["answer"])

    lab_state = {"answer": {"ok": True, "state": "persisted",
                            "detail": "the startup config carries every username line "
                                      "the running config holds (1)"}}
    monkeypatch.setattr("modules.nsot.onboard.persist_on_device", persist)
    return {"client": A.app.test_client(), "data": str(data), "records": records,
            "sent": sent, "state": lab_state}


def _preview(lab, device="r2"):
    r = lab["client"].post("/persist/preview", json={"device": device})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["preview"]


def _apply(lab, preview, device="r2"):
    data = preview["what"]["targets"][0]["select_data"]
    r = lab["client"].post("/persist/apply", json={"list_name": data["list"], "device": device,
                                                  "hash": data["hash"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["result"]


def _gate(p, name):
    (g,) = [g for g in p["targets"][0]["gates"] if g["name"] == name]
    return g


class TestThePreview:
    def test_every_step_and_what_it_will_not_do(self, lab):
        p = _preview(lab)
        program = p["targets"][0]["program"]
        assert program["lines"] == ["write memory (the device's own save)"], (
            "the program is exactly what is SENT; the reads are not lines sent")
        (note,) = program["notes"]
        assert any("read the startup config back" in l for l in note["lines"])
        assert any(l.startswith("record the outcome") for l in note["lines"])
        said = " ".join(i["text"] for i in p["what_not"]["items"])
        for claim in ("running configuration is not changed", "no credential is rotated",
                      "containerlab startup file and Oxidized's router.db are not written",
                      "no golden is committed"):
            assert claim in said, claim
        assert p["what"]["targets"][0]["selectable"] is True
        html = render_preview(p)
        assert "no credential is rotated" in html

    def test_it_contacts_no_device(self, lab, monkeypatch):
        """A preview is safe to repeat because it reads only the inventory and
        the check's record."""
        def _never(*a, **k):
            raise AssertionError("the preview opened a session")
        monkeypatch.setattr("modules.connection.open_ssh", _never)
        _preview(lab)
        assert lab["sent"] == []

    def test_the_confirm_says_what_a_save_carries_with_it(self, lab):
        """Saving copies the running config AS IT IS, so a change not in
        intent survives the next boot: the effect says so at the confirm."""
        confirm = _preview(lab)["confirm"]
        assert "including any change not in its committed intent" in confirm.get("effect", "")
        assert confirm.get("button") == "Save and read back r2"

    def test_the_driver_and_the_dialect_are_drawn_apart(self, lab):
        """The operator, 2026-09-29: the preview named `driver: cisco_ios` for
        r2, an IOS-XE router. The Netmiko driver and the config dialect are
        different facts, and each is named for what it is."""
        op = {o["name"]: o["value"] for o in _preview(lab)["targets"][0]["operands"]}
        assert op["session driver (Netmiko)"] == "cisco_xe"
        assert op["config dialect (the inventory's platform)"] == "cisco_iosxe"

    def test_the_last_hourly_check_is_drawn_with_its_age(self, lab):
        import time

        with open(os.path.join(lab["data"], "startup_check.json"), "w") as fh:
            json.dump({"at": time.time() - 600, "devices": [
                {"list": "Lab", "device": "r2", "state": "not_persisted",
                 "detail": "the startup config does not carry username admin secret 9 <value>"}]},
                fh)
        op = {o["name"]: o["value"] for o in _preview(lab)["targets"][0]["operands"]}
        said = op["startup config, last checked"]
        assert said.startswith("the last hourly check read it NOT persisted, 10 min ago")
        assert "<value>" in said

    def test_a_never_run_check_and_an_unreadable_one_are_different(self, lab):
        op = {o["name"]: o["value"] for o in _preview(lab)["targets"][0]["operands"]}
        assert op["startup config, last checked"].startswith("not checked")
        with open(os.path.join(lab["data"], "startup_check.json"), "w") as fh:
            fh.write("{ not json")
        op = {o["name"]: o["value"] for o in _preview(lab)["targets"][0]["operands"]}
        assert op["startup config, last checked"].startswith(
            "the check's record could not be read")

    def test_each_refusal_is_a_named_gate(self, lab):
        p = _preview(lab, device="s9")
        assert p["what"]["targets"][0]["selectable"] is False
        assert _gate(p, "its platform driver is recorded")["state"] == "fail"
        p = _preview(lab, device="nope")
        assert _gate(p, "the device is in this list's inventory")["state"] == "fail"

    def test_every_refusal_key_the_plan_makes_is_a_gate(self):
        """By AST: a refusal with no gate would be a reason drawn nowhere."""
        src = open(os.path.join(ROOT, "modules", "nsot", "persist_op.py")).read()
        tree = ast.parse(src)
        keys = {n.args[0].value for n in ast.walk(tree)
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "refuse"
                and n.args and isinstance(n.args[0], ast.Constant)}
        # The device-side checks Save shares (`row_checks`, 2026-10-09) name theirs as
        # `refused["<key>"] = ...`.
        keys |= {t.slice.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                 for t in n.targets if isinstance(t, ast.Subscript)
                 and getattr(t.value, "id", "") == "refused"
                 and isinstance(t.slice, ast.Constant)}
        assert keys and keys == {k for k, _t, _d in PO.GATES}, keys


class TestThePreviewAndTheResultAgree:
    """The operator, 2026-09-29: the preview said "(3 line(s))" for one line
    sent and two reads, while the result said "Sent to the device: write
    memory". The preview and the result must not disagree about what the
    operation does, and a count must say what it counts."""

    def test_what_the_preview_says_is_sent_is_what_the_result_says_was(self, lab):
        p = _preview(lab)
        result = _apply(lab, p)
        assert p["targets"][0]["program"]["lines"] == result["targets"][0]["sent"]["lines"]
        html = render_preview(p)
        assert "Sent to the device (1 line(s) sent)" in html, html[:2000]
        assert "(3 line(s))" not in html

    def test_a_captioned_program_that_does_not_say_what_it_counts_is_refused(self):
        from modules.preview_confirm import PreviewIncomplete, build, gate

        target = {"name": "x", "state": "s", "selectable": True, "select_data": {},
                  "program": {"lines": ["a"], "caption": "Sent somewhere"},
                  "operands": [{"name": "n", "value": "v"}],
                  "gates": [gate("g", "pass")]}
        with pytest.raises(PreviewIncomplete, match="what its count counts"):
            build(action="x", summary="s", targets=[target], what_not=[],
                  nothing_left_out="n", confirm={"statement": "s"})
        target["program"]["unit"] = "line(s) sent"
        build(action="x", summary="s", targets=[target], what_not=[],
              nothing_left_out="n", confirm={"statement": "s"})


class TestTheApply:
    def test_it_saves_holding_the_device_and_records_as_the_person(self, lab):
        result = _apply(lab, _preview(lab))
        assert lab["sent"] == [{"ip": "192.0.2.12", "held": True, "type": "cisco_xe",
                                "password_ok": True}]
        assert result["level"] == "success"
        assert result["happened"]["summary"].startswith("r2 is persisted")
        (rec,) = lab["records"]
        assert rec["device"] == "r2" and rec["state"] == "persisted"
        assert rec["via"] == "device page" and rec["actor"]
        html = render_result(result)
        assert "write memory (the device&#39;s own save)" in html or \
            "write memory (the device's own save)" in html

    def test_a_read_back_that_does_not_match_leads_with_it(self, lab):
        lab["state"]["answer"] = {"ok": False, "state": "not_persisted",
                                  "detail": "the startup config does not carry username "
                                            "admin secret 9 <value>"}
        result = _apply(lab, _preview(lab))
        assert result["level"] == "failed"
        assert result["happened"]["summary"].startswith(
            "r2 was saved and the read-back does NOT match")
        assert "nmas-persist-native r2" in result["happened"]["summary"]
        assert lab["records"][0]["state"] == "not_persisted"

    def test_a_moved_plan_is_refused_with_nothing_sent(self, lab):
        p = _preview(lab)
        p["what"]["targets"][0]["select_data"]["hash"] = "0000000000000000"
        result = _apply(lab, p)
        assert lab["sent"] == [] and lab["records"] == []
        assert "the plan changed since the preview" in result["happened"]["summary"]
        assert result["record"]["statement"] == "Nothing was recorded: nothing was sent."

    def test_a_held_device_is_refused_naming_the_holder(self, lab):
        from modules.nsot import device_ops

        p = _preview(lab)
        held, done = threading.Event(), threading.Event()

        def _other():
            with device_ops.hold("Lab", "r2", "deploy", "someone@example.com"):
                held.set()
                done.wait(10)

        worker = threading.Thread(target=_other)
        worker.start()
        try:
            assert held.wait(10)
            result = _apply(lab, p)
        finally:
            done.set()
            worker.join(10)
        assert lab["sent"] == [] and lab["records"] == []
        assert "someone@example.com" in result["happened"]["summary"]

    def test_the_apply_needs_its_list(self, lab):
        r = lab["client"].post("/persist/apply", json={"device": "r2", "hash": "x"})
        assert r.status_code == 400 and "never from whichever list is active" in \
            r.get_json()["error"]
        assert lab["sent"] == []


class TestTheDevicePageOffersIt:
    def test_the_button_and_the_client_are_shipped(self):
        page = open(os.path.join(ROOT, "templates", "device.html")).read()
        assert 'onclick="openPersist(this.dataset.hostname)"' in page
        base = open(os.path.join(ROOT, "templates", "base.html")).read()
        assert "js/nmas_persist.js" in base
