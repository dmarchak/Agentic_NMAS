"""C152 (R1, 2026-09-28): the row onboarding writes must be a row the tool can USE.

`promote_device()` wrote `secret: ""` whenever the device had no separate
enable secret, which after B14 is always: phase 2 passes the credential
store's secret, and the store holds one copy. Every reader decrypts that
column (`stored_connection_params()`), and decrypting "" raises
`InvalidToken`, whose message is EMPTY. So on the host probe-r1a's GUI reload
was held and released within a millisecond, recorded `failed` with error "",
logged nothing, and the screen said "sent". The existing promotion tests
passed `secret="s3cret"`, the pre-B14 shape the real caller never sends.
"""

import os

from tests.test_onboard_pending import _pending, repo  # noqa: F401  (the fixture)


def _row(repo, **creds):
    from modules.config import get_list_data_dir
    from modules.device import load_saved_devices
    from modules.nsot.onboard import promote_device

    _pending(repo)
    out = promote_device(repo, "bp1", "probe", username="admin", **creds)
    assert out.get("ok"), out
    return load_saved_devices(os.path.join(get_list_data_dir("probe"), "devices.csv"))[0]


def test_the_row_phase_two_writes_opens_through_the_real_reader(repo):
    """The seam that failed: the REAL writer, with what the REAL caller
    passes (no separate secret), driven into the REAL reader."""
    from modules.connection import stored_connection_params
    from modules.device import decrypt_field

    row = _row(repo, password="R0tatedValue99", secret="")
    assert decrypt_field(row["secret"]) == "", "an empty secret is an encrypted empty"
    params = stored_connection_params(row)
    assert params["ip"] == "203.0.113.31" and params.get("password") == "R0tatedValue99"


def test_the_row_carries_the_plans_platform_and_its_driver(repo):
    """C495's question (the operator, 2026-10-05: "promotion wrote the row without platform or
    device_type"): it writes both, from the onboarding record, and the tool resolves the row to
    that dialect. Measured on the host the same evening: tw-ztp-a's row in throwaway holds
    `cisco_iosxe` and `cisco_xe`; the refusal came from reading the ACTIVE list's inventory."""
    from modules.nsot.platform import platform_for_device

    row = _row(repo)
    assert row["platform"] == "cisco_iosxe" and row["device_type"] == "cisco_xe", row
    assert platform_for_device(row) == "cisco_iosxe"


def test_a_row_with_a_secret_still_carries_it(repo):
    """The floor: a real secret is still encrypted and still read back."""
    from modules.device import decrypt_field

    row = _row(repo, password="R0tatedValue99", secret="En4bleSecret")
    assert row["secret"] != "En4bleSecret"
    assert decrypt_field(row["secret"]) == "En4bleSecret"


def test_a_failure_is_never_recorded_as_an_empty_sentence():
    """InvalidToken's own message is empty; the recorded error names it."""
    from cryptography.fernet import InvalidToken

    from modules.utils import error_text

    assert error_text(InvalidToken()) == "InvalidToken"
    assert error_text(ValueError("bad value")) == "ValueError: bad value"
    assert error_text(RuntimeError("RuntimeError while x")) == "RuntimeError while x"


def test_the_per_device_recorders_use_it():
    """The two per-device failure recorders the bulk paths have (the
    reload's and the bulk loop's). A bare `str(exc)` put back is found."""
    import re

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bare = re.compile(r'result\["error"\]\s*=\s*str\((exc|e)\)')
    found = {}
    for rel in ("app.py", "modules/bulk_ops.py"):
        text = open(os.path.join(root, rel), encoding="utf-8").read()
        found[rel] = (len(re.findall(r'result\["error"\]\s*=', text)), bare.findall(text))
    assert all(n >= 1 for n, _ in found.values()), found
    assert all(not b for _, b in found.values()), found


def test_the_reload_screen_draws_each_device_s_result_not_a_sent_toast():
    """The screen half. `/bulk_reload` answers before any device is
    contacted, and the handler drew that answer ("Reload sent to 1
    device(s)") as the result. It now opens the per-device poller bulk
    execute already uses. Read from the handler's own body (comments
    stripped), anchored on its definition, never a phrase in prose."""
    import re

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "static", "js", "gen", "index.1.js"), encoding="utf-8").read()
    start = src.index("window.reloadSelectedDevices = function()")
    end = src.index("window.refreshHostnames = function()", start)
    body = re.sub(r"//[^\n]*", "", src[start:end])
    assert "showBulkResults(data.operation_id)" in body, body[-600:]
    assert "showToast(data.message, 'warning')" not in body
