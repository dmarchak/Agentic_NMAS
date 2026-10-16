"""C906's reviewed re-key, from the device page, and where a refused key surfaces.

On test_persist_screen's lab (r2 at 192.0.2.12 in network Lab), through the real routes,
templates, record and Needs attention source; the device's key READ is replaced at
`connection.read_host_key` (its own test reads a real server: tests/test_host_keys.py), and
each key is a real RSA key generated for the run.

- a refused key is a Needs attention row naming both fingerprints, opening the re-key card;
- the preview draws the key held beside the key read now, what is known of why it changed,
  its checks and the confirm bound to both keys;
- the confirm, as the verified person and holding the device, keeps the new key with the old
  one in the record's history; History draws both; the Needs attention row clears;
- a key that moved between the preview and the confirm is refused with nothing kept;
- no key held, the same key, a held device and an unreadable record each fail their check by
  name, with no confirm.
"""

import json
import re

import paramiko
import pytest

from modules import host_keys as HK
from modules.nsot import rekey_op
from tests.test_persist_screen import lab  # noqa: F401 (the fixture)

IP = "192.0.2.12"


@pytest.fixture(scope="module")
def keys():
    return [paramiko.RSAKey.generate(2048) for _ in range(3)]


@pytest.fixture
def world(lab, keys, monkeypatch):  # noqa: F811
    """r2 kept with key 0; what it answers with now is `now[0]`."""
    now = [HK.offered(keys[1])]
    reads = []

    def read(ip, **kw):
        reads.append((ip, kw.get("owner")))
        return dict(now[0])

    monkeypatch.setattr("modules.connection.read_host_key", read)
    HK.check(IP, keys[0], owner="test:first-contact")
    return dict(lab, now=now, reads=reads, keys=keys)


def _card(world, device="r2", back="history"):
    r = world["client"].get(f"/v2/device/{device}/rekey?back={back}")
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_data(as_text=True)


def _confirm(world, html, device="r2", **over):
    vals = json.loads(re.search(r"hx-vals='([^']*)'", html[html.index("op-confirm"):]).group(1))
    return world["client"].post(f"/v2/device/{device}/rekey/confirm", data={**vals, **over})


def _held():
    rec = HK.held(IP)
    assert rec is not None, "no key is held for r2's address"
    return rec


def _one_row(got):
    assert len(got["rows"]) == 1, got["rows"]
    return got["rows"][0]


def _fp(world, i):
    return HK.offered(world["keys"][i])["fingerprint"]


class TestARefusedKeySurfaces:
    def test_needs_attention_names_both_keys_and_opens_the_card(self, world):
        from modules import attention
        with pytest.raises(HK.HostKeyRefused):
            HK.check(IP, world["keys"][1], owner="reader:capture")
        got = attention.host_key_source()
        row = _one_row(got)
        assert row["kind"] == "changed" and row["level"] == "danger"
        assert row["devices"] == ["r2"]
        assert row["what"].startswith("r2 answered with a different SSH host key")
        assert _fp(world, 1) in row["cause"] and _fp(world, 0) in row["cause"]
        assert row["action"]["href"] == "/v2/device/r2?op=rekey&list=Lab"
        assert row["clears"]["ways"] == ["resolves"] and "re-key" in row["clears"]["when"]
        page = world["client"].get("/v2/device/r2?op=rekey").get_data(as_text=True)
        body = page[page.index('id="tab-body"'):]
        assert 'id="device-op"' in body and "Re-key r2" in body and "op-confirm" in body

    def test_an_unreadable_record_is_the_source_s_own_row(self, world, lab):  # noqa: F811
        import os
        from modules import attention
        with open(HK.path(), "w") as fh:
            fh.write("{broken")
        os.chmod(HK.path(), 0o600)
        got = attention.host_key_source()
        assert got["state"] == "unreadable"
        row = _one_row(got)
        assert row["kind"] == "unreadable" and "could not be read" in row["cause"]


class TestThePreview:
    def test_it_draws_both_keys_why_and_the_bound_confirm(self, world):
        html = _card(world)
        assert world["reads"] == [(IP, "rekey:preview")], "the key is read once, no credential"
        what = html[html.index("<h3>What</h3>"):html.index("What will not happen")]
        assert f"{_fp(world, 0)} (ssh-rsa), kept" in what and "test:first-contact" in what
        assert f"{_fp(world, 1)} (ssh-rsa)" in what
        nots = html[html.index("What will not happen"):html.index("Operands")]
        assert "Nothing is sent to the device" in nots and "The old key is not forgotten" in nots
        ops = html[html.index("Operands"):html.index("Checks")]
        assert "NO restart recorded since the key was kept" in ops
        assert "Plan hash" in ops
        checks = html[html.index("Checks"):html.index("op-ft")]
        assert "badge-danger" not in checks
        assert "You are a verified person: test-person@example.invalid" in checks
        foot = html[html.index("op-ft"):]
        h = re.search(r'"hash": "([0-9a-f]+)"', foot).group(1)
        assert h == rekey_op.plan("Lab", "r2")["hash"]
        assert f"Bound to plan {h}" in foot and 'class="op-idle">Keep the new key for r2' in foot
        assert 'hx-disabled-elt="this"' in foot and '"list": "Lab"' in foot

    def test_the_same_key_has_nothing_to_re_key(self, world):
        world["now"][0] = HK.offered(world["keys"][0])
        html = _card(world)
        assert "there is nothing to re-key" in html and "op-confirm" not in html

    def test_no_key_held_has_nothing_to_replace(self, world):
        import os
        os.remove(HK.path())
        html = _card(world)
        assert "Mercury holds no key for r2" in html and "op-confirm" not in html

    def test_a_held_device_fails_its_check_by_name(self, world):
        from modules.nsot import device_ops
        device_ops.acquire("Lab", "r2", "deploy", "alex@example.invalid")
        try:
            html = _card(world)
        finally:
            device_ops.release("Lab", "r2")
        assert "alex@example.invalid" in html[html.index("Checks"):]
        assert "op-confirm" not in html

    def test_every_refusal_has_its_gate(self):
        assert {k for k, _t, _d in rekey_op.GATES} >= {"list", "present", "store", "held",
                                                       "read", "changed"}


class TestTheConfirm:
    def test_it_keeps_the_new_key_and_the_old_in_history(self, world):
        from modules import attention, history_sources
        with pytest.raises(HK.HostKeyRefused):
            HK.check(IP, world["keys"][1], owner="reader:capture")
        out = _confirm(world, _card(world)).get_data(as_text=True)
        assert "op-card op-ok" in out and "Re-keyed" in out
        rec = _held()
        assert rec["fingerprint"] == _fp(world, 1) and rec["how"] == HK.REKEYED
        assert rec["kept_by"] == "test-person@example.invalid"
        assert rec["history"][-1]["fingerprint"] == _fp(world, 0)
        assert rec["history"][-1]["replaced_by"] == "test-person@example.invalid"
        assert "refused" not in rec
        assert attention.host_key_source()["rows"] == [], "the row clears"
        # The next session signs in to the new key.
        assert HK.check(IP, world["keys"][1], owner="test")["state"] == "matched"
        from modules.nsot.listref import resolve
        tl = history_sources.timeline(resolve("Lab"), device="r2", kinds=["hostkeys"])
        assert [e["what"] for e in tl["events"]] == ["SSH host key re-keyed",
                                                     "SSH host key kept on first contact"]
        assert tl["events"][0]["who"] == "test-person@example.invalid"

    def test_a_key_that_moved_since_the_preview_is_refused(self, world):
        html = _card(world)
        world["now"][0] = HK.offered(world["keys"][2])
        out = _confirm(world, html).get_data(as_text=True)
        assert "Refused: nothing was kept" in out and "the plan changed since the preview" in out
        assert _fp(world, 2) in out
        assert _held()["fingerprint"] == _fp(world, 0), "nothing was kept"

    def test_a_record_that_moved_since_the_preview_is_refused(self, world):
        html = _card(world)
        HK.replace(IP, expected=_fp(world, 0), new=HK.offered(world["keys"][2]),
                   by="someone@example.invalid", why="another re-key")
        world["now"][0] = HK.offered(world["keys"][1])
        out = _confirm(world, html).get_data(as_text=True)
        assert "Refused: nothing was kept" in out
        assert _held()["fingerprint"] == _fp(world, 2)

    @pytest.mark.parametrize("over,code", [({"hash": ""}, 400), ({"list": ""}, 400),
                                           ({"list": "Nowhere"}, 400)])
    def test_a_confirm_with_no_plan_or_list_keeps_nothing(self, world, over, code):
        r = _confirm(world, _card(world), **over)
        assert r.status_code == code and "Nothing was kept" in r.get_data(as_text=True)
        assert _held()["fingerprint"] == _fp(world, 0)

    def test_a_viewer_who_may_not_confirm_gets_no_confirm(self, world, monkeypatch):
        from modules import identity
        monkeypatch.setattr(identity, "identify",
                            lambda r: identity.Identity(peer="198.51.100.7"))
        html = _card(world)
        assert "op-confirm" not in html
