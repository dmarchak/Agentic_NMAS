"""A device whose stored credential the key cannot open is refused by name in every device
operation's preview, never a crash (C410, C423).

C410 (found 2026-10-04 by C409's browser sweep): `GET /v2/device/<name>/persist` answered 500
(`InvalidToken`) for such a device. C410's sweep, every preview that opens a stored credential
(`decrypt_field(` on a preview's call path), found one more: retire's preview through
`breakglass_logged`, once the list has a logged break-glass export (C423), and the apply's
`breakglass_covers` beside it. All three now read the credential through
`device.open_stored()`, which names the device and the error instead of raising, as C384's
break-glass export does.

The unopenable value is REAL: a Fernet token made with another key, which this host's key
rejects with `InvalidToken`, exactly the host's case.
"""

import pytest
from cryptography.fernet import Fernet

from tests.test_persist_screen import lab  # noqa: F401 (the fixture)

FOREIGN = Fernet(Fernet.generate_key()).encrypt(b"a-password-another-key-sealed").decode()


def _unopenable(lab_dir_rows, device):
    return [dict(r, password=FOREIGN) if r["hostname"] == device else r for r in lab_dir_rows]


class TestTheReader:
    def test_an_unopenable_value_is_named_never_raised(self):
        from modules import device
        value, why = device.open_stored({"hostname": "r3", "password": FOREIGN})
        assert value == ""
        assert why == ("r3's stored password could not be opened with this host's key "
                       "(InvalidToken): enter it again for the device, or restore the key "
                       "that sealed it")

    def test_an_openable_value_opens(self):
        from modules import device
        sealed = device.fernet.encrypt(b"pw").decode()
        assert device.open_stored({"hostname": "r3", "password": sealed}) == ("pw", "")

    def test_an_empty_value_is_empty_and_not_a_failure(self):
        from modules import device
        assert device.open_stored({"hostname": "r3", "password": ""}) == ("", "")


class TestPersistsPreview:
    def _break(self, lab):  # noqa: F811
        import os

        from modules import device
        from modules.config import get_list_data_dir
        path = os.path.join(get_list_data_dir("Lab"), "devices.csv")
        device.write_devices_csv(_unopenable(device.load_saved_devices(path), "r2"), path)

    def test_the_card_answers_and_names_the_device(self, lab):  # noqa: F811
        self._break(lab)
        r = lab["client"].get("/v2/device/r2/persist?back=history")
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html[:400]
        assert "r2&#39;s stored password could not be opened with this host&#39;s key " \
               "(InvalidToken)" in html
        assert "op-confirm" not in html

    def test_the_plan_refuses_by_its_credential_check(self, lab):  # noqa: F811
        from modules.nsot import persist_op
        self._break(lab)
        p = persist_op.plan("Lab", "r2")
        assert p["ok"] is False
        assert p["refused_by"]["credential"].startswith(
            "r2's stored password could not be opened with this host's key (InvalidToken)")


class TestRetiresBreakglassChecks:
    ROW = {"hostname": "r3", "username": "admin", "password": FOREIGN}
    EXPORTS = {"by_list": {"Lab": {"at": 1790000000, "path": "/dev/shm/x.bg",
                                   "devices": {"r3": "0" * 16}}}}

    def test_the_preview_names_the_device(self):
        from modules.nsot import retire
        got = retire.breakglass_logged("Lab", self.ROW, exports=self.EXPORTS)
        assert got["ok"] is False
        assert got["why"].startswith("r3's stored password could not be opened with this "
                                     "host's key (InvalidToken)")

    def test_the_apply_names_the_device(self):
        from modules.nsot import retire
        why = retire.breakglass_covers({"devices": []}, "Lab", self.ROW)
        assert why.startswith("r3's stored password could not be opened with this host's key")

    @pytest.mark.parametrize("fn", ["breakglass_logged", "breakglass_covers"])
    def test_a_row_with_no_password_is_still_said_as_before(self, fn):
        from modules.nsot import retire
        row = dict(self.ROW, password="")
        got = (retire.breakglass_logged("Lab", row, exports=self.EXPORTS)["why"]
               if fn == "breakglass_logged" else retire.breakglass_covers({}, "Lab", row))
        assert got == "the CSV row holds no password to compare"
