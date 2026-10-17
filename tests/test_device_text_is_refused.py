"""C570 (the operator, 2026-10-08, bucket A): text a request sends reaches a device only as a READ.

The device page's command route ran ANY exec command (reload, write erase, delete, copy): it
held the device for a non-read, so the session guard let it through. Bulk Operation's enable
mode did the same on every selected device and answered `reload`'s prompts itself. And the
file routes spliced form fields into commands (`delete {filesystem}{filename}`), where a line
break is a second command. Now:

- a free-form command passes the read-only allowlist whole, or nothing is sent (v2's Ask tab,
  through the reads engine; today's `/run_command` did the same until it left at 7.8 with
  today's device page, 2026-10-17, and today's `/bulk_execute`, which checked every
  `;`-separated part, left on 2026-10-15);
- a field spliced into a command is one token of its shape (`modules/cli_tokens.py`);
- each refusal comes BEFORE any device is contacted: netmiko's connect is recorded here, and a
  refused request records none.

The population: every route in `app.py` and `routes/` whose body reads the request and calls a
device sender. Each is named below with its check; a new one fails until it is. Since today's
device page left there is none: every route that reaches a device hands the request to a
module (the reads engine, a job), and the planted route below is what shows the scan can still
find one.
"""

import ast
import os
import re

import pytest

from tests.test_ask_the_device import ask  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture under `ask`)
from tests.test_session_write_guard import IP, FakeConn

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


@pytest.fixture
def client():
    import app as A
    return A.app.test_client()


class TestTheDevicePageCommand:
    """v2's Ask tab, the one place a person types a command for one device (today's
    /run_command until 7.8), on test_device_v2's lab: every write in WRITES is refused, the
    refusal recorded, and nothing reaches r3 or netmiko."""

    def _post(self, lab, command):
        from modules.nsot import capture_job
        r = lab["client"].post("/v2/device/r3/ask", data={"list": "Lab", "command": command},
                               headers={"HX-Request": "true"})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        body = r.get_data(as_text=True)
        job = re.search(r"job=([0-9a-f]{32})", body)
        if job:
            assert capture_job.wait(job.group(1), 30)
        return body

    def test_a_write_is_refused_before_any_device_is_contacted(self, ask, contacts):  # noqa: F811
        from modules.nsot import reads
        for command in WRITES:
            self._post(ask, command)
        assert ask["device"].sent == [] and contacts == [] and FakeConn.sent == []
        runs = reads.runs("Lab")["runs"]
        assert sorted(r["state"] for r in runs) == ["refused"] * len(WRITES), runs

    def test_a_read_runs(self, ask, contacts):  # noqa: F811
        """The control: the tab still reads."""
        self._post(ask, "show running-config")
        assert ask["device"].sent == ["show running-config"]


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


#: Every route whose body reads the request and calls a device sender, with its check. Empty
#: since today's /run_command left at 7.8 (2026-10-17, P7-22); its entry was
#: "readonly_commands.refusal, before any device", which v2's Ask keeps through the reads engine.
CHECKED = {}
SENDERS = {"run_device_command", "send_command", "send_command_timing", "send_config_set",
           "with_temp_connection", "get_persistent_connection"}


def _route_files():
    return [os.path.join(ROOT, "app.py")] + [
        os.path.join(ROOT, "routes", f) for f in os.listdir(os.path.join(ROOT, "routes"))
        if f.endswith(".py")]


def _routes_that_send_request_text(files=None):
    """``(found, routed)``: ``{function: file}`` for each routed function that reads the request
    and calls a device sender, and how many routed functions the walk read."""
    found, routed = {}, 0
    for path in files or _route_files():
        tree = ast.parse(open(path, encoding="utf-8").read())
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            if not any("route" in ast.unparse(d) for d in fn.decorator_list):
                continue
            routed += 1
            src = ast.unparse(fn)
            reads = "request.form" in src or "request.files" in src or "request.args" in src \
                or "request.get_json" in src or "request.json" in src
            calls = {getattr(c.func, "attr", getattr(c.func, "id", "")) for c in ast.walk(fn)
                     if isinstance(c, ast.Call)}
            if reads and calls & SENDERS:
                found[fn.name] = os.path.relpath(path, ROOT)
    return found, routed


def test_every_route_sending_request_text_is_checked():
    found, routed = _routes_that_send_request_text()
    # The floor is on the routes read, not on the offenders: measured 2026-10-17, 348 routed
    # functions (the offenders fell from 16 on 2026-10-08 to 0 when today's device page left).
    # 299 measured 2026-10-17 once today's deploy wizard and onboarding routes left (P7-25);
    # a floor on the route table this scan reads.
    assert routed >= 290, routed
    unchecked = sorted(set(found) - set(CHECKED) - set(NOT_REQUEST_TEXT))
    assert not unchecked, (
        "a route reads the request and sends to a device with no declared check: "
        f"{[(n, found[n]) for n in unchecked]}")


#: Routes the scan finds whose request fields choose a DEVICE or a fixed command, never text
#: sent to it: each named with what it reads. Empty since today's device page (manage_device,
#: its `active_tab`) left at 7.8, 2026-10-17.
NOT_REQUEST_TEXT = {}


def test_the_scan_finds_a_planted_route(tmp_path):
    """The control: the walk itself names a routed function, in a file beside the real ones,
    that reads the form and sends to a device."""
    planted = tmp_path / "planted.py"
    planted.write_text("@app.route('/x', methods=['POST'])\n"
                       "def planted():\n"
                       "    c = request.form.get('c')\n"
                       "    return run_device_command(conn, c)\n", encoding="utf-8")
    found, _routed = _routes_that_send_request_text(_route_files() + [str(planted)])
    assert list(found) == ["planted"] and "planted" not in CHECKED
