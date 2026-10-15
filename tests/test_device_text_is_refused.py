"""C570 (the operator, 2026-10-08, bucket A): text a request sends reaches a device only as a READ.

The device page's command route ran ANY exec command (reload, write erase, delete, copy): it
held the device for a non-read, so the session guard let it through. Bulk Operation's enable
mode did the same on every selected device and answered `reload`'s prompts itself. And the
file routes spliced form fields into commands (`delete {filesystem}{filename}`), where a line
break is a second command. Now:

- a free-form command passes the read-only allowlist whole, or nothing is sent (`/run_command`;
  today's `/bulk_execute`, which checked every `;`-separated part, left at 7.8, 2026-10-15);
- a field spliced into a command is one token of its shape (`modules/cli_tokens.py`);
- each refusal comes BEFORE any device is contacted: netmiko's connect is recorded here, and a
  refused request records none.

The population: every route in `app.py` and `routes/` whose body reads the request and calls a
device sender. Each is named below with its check; a new one fails until it is.
"""

import ast
import io
import os

import pytest

from tests.test_session_write_guard import IP, FakeConn, client  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITES = ["reload", "write erase", "write memory", "delete flash:x.bin",
          "copy running-config startup-config", "configure terminal", "clear counters",
          "show clock\nreload", "show running-config | redirect tftp://192.0.2.10/x"]


class Contacts(FakeConn):
    """netmiko's connect, recorded: a refused request makes none."""
    made = []

    def __init__(self, **params):
        Contacts.made.append(params.get("ip"))
        super().__init__(**params)


@pytest.fixture(autouse=True)
def contacts(monkeypatch):
    import netmiko

    from modules import connection as C
    Contacts.made = []
    FakeConn.sent = []
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    C._sessions.clear()
    monkeypatch.setattr(netmiko, "ConnectHandler", Contacts)
    return Contacts.made


AJAX = {"X-Requested-With": "XMLHttpRequest"}


class TestTheDevicePageCommand:
    @pytest.mark.parametrize("command", WRITES)
    def test_a_write_is_refused_before_any_device_is_contacted(self, client, contacts, command):
        r = client.post(f"/run_command/{IP}", data={"command": command}, headers=AJAX)
        assert r.status_code == 400, r.get_data(as_text=True)[:300]
        assert r.get_json()["error"].startswith("Not run on r2: REFUSED")
        assert contacts == [] and FakeConn.sent == []

    def test_a_read_runs(self, client, contacts):
        """The control: the route still reads."""
        r = client.post(f"/run_command/{IP}", data={"command": "show clock"}, headers=AJAX)
        assert r.status_code == 200 and contacts == [IP] and "show clock" in FakeConn.sent


class TestTheBulkRoutesAreGone:
    """Bulk file actions left at 7.8 (D16, 2026-10-13) and today's bulk commands
    (/bulk_execute, /bulk_status) on 2026-10-15: nothing reaches a device through them. Many
    devices' reads are Show commands', which refuses a write in any part before any device
    (tests/test_show_commands.py, TestARun)."""

    @pytest.mark.parametrize("route", ["/bulk_tftp_download", "/bulk_download_config",
                                       "/bulk_delete_file", "/bulk_tftp_upload",
                                       "/bulk_execute"])
    def test_the_bulk_routes_are_gone(self, client, contacts, route):
        r = client.post(route, data={"device_ips[]": [IP], "filename": "x.bin",
                                     "command": "show clock", "command_mode": "enable"})
        assert r.status_code in (404, 405) and contacts == [] and FakeConn.sent == []


class TestTheFileRoutesAreGone:
    """Device files left at 7.8 (D16, 2026-10-13): the routes that spliced a filename into a
    device command no longer exist, so nothing reaches a device through them."""

    @pytest.mark.parametrize("route", ["delete_file", "download_file", "upload",
                                       "refresh_files"])
    def test_the_route_is_gone(self, client, contacts, route):
        r = client.post(f"/device/{IP}/{route}", data={"filename": "x.bin"})
        assert r.status_code in (404, 405) and contacts == [] and FakeConn.sent == []


class TestTheShapes:
    @pytest.mark.parametrize("value, kind", [("flash:", "filesystem"), ("bootflash:", "filesystem"),
                                             ("c8000v-17.06.bin", "filename"),
                                             ("192.0.2.10", "server"), ("tftp.example", "server")])
    def test_a_token_of_its_shape_passes(self, value, kind):
        from modules.cli_tokens import refusal
        assert refusal(value, kind) == ""

    @pytest.mark.parametrize("value, kind", [("x\nreload", "filename"), ("a b", "filename"),
                                             ("../x", "filename"), ("..", "filename"),
                                             ("", "filename"), (None, "server"),
                                             ("flash", "filesystem"), ("flash:/x", "filesystem"),
                                             ("192.0.2.1 x", "server"), ("x\r", "server")])
    def test_anything_else_is_refused_naming_it(self, value, kind):
        from modules.cli_tokens import refusal
        why = refusal(value, kind, "the field")
        assert why.startswith("Refused: the field"), why
        assert "\n" not in why and "\r" not in why          # the refusal never echoes a break


#: Every route whose body reads the request and calls a device sender, with its check.
CHECKED = {
    "run_command": "readonly_commands.refusal, before any device",
}
SENDERS = {"run_device_command", "send_command", "send_command_timing", "send_config_set",
           "with_temp_connection", "get_persistent_connection",
           "get_device_context"}


def _routes_that_send_request_text():
    found = {}
    files = [os.path.join(ROOT, "app.py")] + [
        os.path.join(ROOT, "routes", f) for f in os.listdir(os.path.join(ROOT, "routes"))
        if f.endswith(".py")]
    for path in files:
        tree = ast.parse(open(path, encoding="utf-8").read())
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            routed = any("route" in ast.unparse(d) for d in fn.decorator_list)
            if not routed:
                continue
            src = ast.unparse(fn)
            reads = "request.form" in src or "request.files" in src or "request.args" in src \
                or "request.get_json" in src or "request.json" in src
            calls = {getattr(c.func, "attr", getattr(c.func, "id", "")) for c in ast.walk(fn)
                     if isinstance(c, ast.Call)}
            if reads and calls & SENDERS:
                found[fn.name] = os.path.relpath(path, ROOT)
    return found


def test_every_route_sending_request_text_is_checked():
    found = _routes_that_send_request_text()
    assert len(found) >= 2, found                # a floor; measured 2026-10-08: 16; 15 since 7.8 removed /bulk_reload, 13 since Configure, 12 since Topology (2026-10-12), 8 since Device files, 4 since Bulk file actions (2026-10-13), 3 since Backups (2026-10-14), 2 since today's bulk commands (2026-10-15)
    unchecked = sorted(set(found) - set(CHECKED) - set(NOT_REQUEST_TEXT))
    assert not unchecked, (
        "a route reads the request and sends to a device with no declared check: "
        f"{[(n, found[n]) for n in unchecked]}")


#: Routes the scan finds whose request fields choose a DEVICE or a fixed command, never text
#: sent to it: each named with what it reads.
NOT_REQUEST_TEXT = {
    "manage_device": "active_tab picks a tab; get_device_context with no filesystem",
}


def test_the_scan_finds_a_planted_route(tmp_path):
    """The control: the population check names a routed function that reads the form and
    sends to a device."""
    planted = ("@app.route('/x', methods=['POST'])\n"
               "def planted():\n"
               "    c = request.form.get('c')\n"
               "    return run_device_command(conn, c)\n")
    tree = ast.parse(planted)
    fn = tree.body[0]
    src = ast.unparse(fn)
    calls = {getattr(c.func, "attr", getattr(c.func, "id", "")) for c in ast.walk(fn)
             if isinstance(c, ast.Call)}
    assert "request.form" in src and calls & SENDERS and "planted" not in CHECKED
