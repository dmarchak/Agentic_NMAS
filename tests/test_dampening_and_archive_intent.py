"""Intent's interface `dampening` and its configuration archive, `archive.path` (H22;
docs/HEAL_TO_INTENT.md 19.4 and guard 13f).

**Dampening** (`interfaces[].dampening`, true for the bare `dampening`, the platform's defaults,
N19): the parser reads the line into the key and nothing into unmodelled, a line with
parameters stays unmodelled, the template sends it back, a round trip keeps it, a deploy adding
it sends exactly the interface, the line and `exit`, on an IOS-XE interface holding IPv4 and
IPv6 (r4 Gi4, the I5 port) and on an IOS interface holding IPv6 alone (s1 Vlan30). Its removal
shape, `interface.dampening`, is refused by name until the probe measures it on each dialect:
the dampening proposal's rollback (`removal.restore_program`) waits on that measurement.

**The archive** (`archive: {path: <url>}`): the parser models `archive` with exactly one child,
`path <url>`, and leaves any other shape unmodelled, whole (a second child, a URL carrying a
credential, which C477's reference takes out of intent). The template sends it nested, a round
trip keeps it, and bounce's 13f reads it. A document holding the archive twice, modelled AND
as the unmodelled block r4's and s1's intent held before H22 (C2700), is refused by the
authoring gates, naming both; which one a stored document keeps is the operator's.

The captures are tests/fixtures/configs/fleet/r4.cfg and s1.cfg, the real configurations; the
edits are the one line spliced in (` dampening` under the interface, after its own address
line: where IOS prints it is unmeasured, and the round trip compares an interface's body as a
set) and test_unmodelled_children_depth.py's archive block, read masked from the committed
goldens.
"""

import copy
import os

import pytest

from modules.nsot import deploy, hostvars, removal as RM, roundtrip, verify_scope
from modules.nsot.parsers import get_parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")

#: (device, platform, interface, the line it is spliced after, the family it carries)
PORTS = {
    "r4 Gi4 (IOS-XE, IPv4 and IPv6)": ("r4", "cisco_iosxe", "GigabitEthernet4",
                                       " ip address 10.255.2.15 255.255.255.254"),
    "s1 Vlan30 (IOS, IPv6 alone)": ("s1", "cisco_ios", "Vlan30",
                                    " ipv6 address 2001:DB8:30::2/64"),
}

#: Each device's archive block, as test_unmodelled_children_depth.py splices it.
ARCHIVE = {"r4": ("cisco_iosxe", "bootflash:mercury-arch", "diagnostic bootup level minimal\n"),
           "s1": ("cisco_ios", "flash0:mercury-arch", "ipv6 cef\n!\n")}


def _cfg(device):
    with open(os.path.join(FLEET, f"{device}.cfg"), encoding="utf-8") as fh:
        return fh.read()


def _parse(text, platform):
    return get_parser(platform).parse(text)


def _iface(hv, name):
    return next(i for i in hv["interfaces"] if i["name"] == name)


def _with_line(port, line=" dampening"):
    device, _platform, name, after = PORTS[port]
    text = _cfg(device)
    block = text.split(f"interface {name}\n", 1)
    assert len(block) == 2 and after + "\n" in block[1].split("!\n", 1)[0], \
        f"floor: {device}'s capture holds {name} with {after.strip()!r}"
    return block[0] + f"interface {name}\n" + block[1].replace(after + "\n",
                                                                after + "\n" + line + "\n", 1)


def _render(hv):
    return roundtrip.render(hv, hv["platform"])


@pytest.mark.parametrize("port", sorted(PORTS))
class TestDampening:

    def test_the_parser_reads_the_bare_line_into_the_key_and_nothing_into_unmodelled(self, port):
        _d, platform, name, _a = PORTS[port]
        gi = _iface(_parse(_with_line(port), platform), name)
        assert gi["dampening"] is True
        assert not [l for l in gi["unmodeled"] if "dampening" in l], gi["unmodeled"]

    def test_an_interface_without_it_holds_false(self, port):
        device, platform, name, _a = PORTS[port]
        assert _iface(_parse(_cfg(device), platform), name)["dampening"] is False

    def test_a_line_with_parameters_is_not_the_bare_line_and_stays_unmodelled(self, port):
        _d, platform, name, _a = PORTS[port]
        gi = _iface(_parse(_with_line(port, " dampening 5 1000 2000 20"), platform), name)
        assert gi["dampening"] is False
        assert "dampening 5 1000 2000 20" in gi["unmodeled"]

    def test_the_template_sends_it_back_and_a_round_trip_keeps_it(self, port):
        _d, platform, name, _a = PORTS[port]
        capture = _with_line(port)
        hv = _parse(capture, platform)
        rendered = _render(hv)
        body = rendered.split(f"interface {name}\n", 1)[1].split("\n!", 1)[0].splitlines()
        assert body.count(" dampening") == 1, body
        assert _iface(_parse(rendered, platform), name)["dampening"] is True
        report = roundtrip.compare(capture, rendered, hv)
        moved = [str(x) for k in ("missing", "extra", "reordered") for x in report["details"][k]]
        assert not [m for m in moved if "dampening" in m], moved

    def test_a_deploy_adds_exactly_the_line_under_its_interface(self, port):
        device, platform, name, _a = PORTS[port]
        hv = _parse(_cfg(device), platform)
        want = copy.deepcopy(hv)
        _iface(want, name)["dampening"] = True
        program = deploy.merge_commands(_render(want), _render(hv))
        assert program == [f"interface {name}", " dampening", "exit"], program
        assert verify_scope.read_back(program, _with_line(port))["missing"] == []

    @pytest.mark.parametrize("dialect", ("cisco_ios", "cisco_iosxe"))
    def test_its_removal_is_refused_by_name_until_the_probe_measures_it(self, port, dialect):
        _d, _p, name, _a = PORTS[port]
        chain = [f"interface {name}"]
        assert RM.shape_for(chain, " dampening", "leaf").key == "interface.dampening"
        out = RM.removal_program(_with_line(port), [{"chain": chain, "line": " dampening"}],
                                 mgmt_ip="192.0.2.1", dialect=dialect)
        assert out["commands"] == [], out
        assert (f"`interface.dampening` has not been measured on {dialect}"
                in out["refused"][0]["reason"]), out
        assert "scripts/nmas-removal-probe --shape interface.dampening" in \
            out["refused"][0]["reason"]


def _with_archive(device, children=None):
    _platform, path, after = ARCHIVE[device]
    text = _cfg(device)
    assert text.count(after) == 1, f"{device}: the splice point is not unique"
    lines = children if children is not None else [f" path {path}"]
    block = "archive\n" + "".join(c + "\n" for c in lines) + ("!\n" if device == "s1" else "")
    return text.replace(after, after + block)


def _stanza(text):
    lines = text.splitlines()
    out = []
    for n, line in enumerate(lines):
        if line == "archive":
            out.append([line] + [l for l in _children(lines[n + 1:])])
    return out


def _children(rest):
    for line in rest:
        if not line.startswith(" "):
            return
        yield line


@pytest.mark.parametrize("device", sorted(ARCHIVE))
class TestTheArchive:

    def test_the_parser_models_its_path_and_leaves_nothing_unmodelled(self, device):
        platform, path, _a = ARCHIVE[device]
        hv = _parse(_with_archive(device), platform)
        assert hv["archive"] == {"path": path}
        assert not [e for e in hv["unmodeled"] if e["line"] == "archive"], hv["unmodeled"]

    def test_a_config_without_one_holds_no_archive_key(self, device):
        assert "archive" not in _parse(_cfg(device), ARCHIVE[device][0])

    @pytest.mark.parametrize("children", (
        [" path {path}", " maximum 14"],
        [" path ftp://mercury:Pa55word@192.0.2.10/mercury-arch"],
        [" path ftp://mercury:Pa55word@[2001:DB8::10]/mercury-arch"],
        [" log config", "  logging enable"],
    ), ids=("a second child", "an IPv4 URL with a credential",
            "an IPv6 URL with a credential", "no path at all"))
    def test_any_other_shape_stays_unmodelled_whole(self, device, children):
        platform, path, _a = ARCHIVE[device]
        children = [c.format(path=path) for c in children]
        hv = _parse(_with_archive(device, children), platform)
        assert "archive" not in hv, hv.get("archive")
        blocks = [e for e in hv["unmodeled"] if e["line"] == "archive"]
        assert len(blocks) == 1 and len(blocks[0]["children"]) == len(children), blocks
        assert "Pa55word" not in str(blocks), "C477: a URL's password becomes a reference"

    @pytest.mark.parametrize("url", ("tftp://192.0.2.10/mercury-arch",
                                     "tftp://[2001:DB8::10]/mercury-arch"))
    def test_a_network_path_on_either_family_is_modelled(self, device, url):
        hv = _parse(_with_archive(device, [f" path {url}"]), ARCHIVE[device][0])
        assert hv["archive"] == {"path": url}

    def test_the_template_sends_it_once_nested_and_a_round_trip_keeps_it(self, device):
        platform, path, _a = ARCHIVE[device]
        capture = _with_archive(device)
        hv = _parse(capture, platform)
        stored = hostvars.from_yaml(hostvars.to_yaml(hv))
        stored["secrets"] = hv["secrets"]
        rendered = _render(stored)
        assert _stanza(rendered) == [["archive", f" path {path}"]]
        assert _parse(rendered, platform)["archive"] == {"path": path}
        report = roundtrip.compare(capture, rendered, stored)
        moved = [str(x) for k in ("missing", "extra", "reordered") for x in report["details"][k]]
        assert not [m for m in moved if "archive" in m or "mercury-arch" in m], moved

    def test_a_deploy_adding_it_sends_it_nested_and_verify_reads_it_back(self, device):
        platform, path, _a = ARCHIVE[device]
        hv = _parse(_cfg(device), platform)
        program = deploy.merge_commands(_render(dict(hv, archive={"path": path})), _cfg(device))
        assert program[program.index("archive") + 1] == f" path {path}", program
        assert verify_scope.read_back(program, _with_archive(device))["missing"] == []

    def test_bounces_13f_reads_the_modelled_path(self, device):
        from modules.heal import bounce
        platform, path, _a = ARCHIVE[device]
        assert bounce.archive_path(_parse(_with_archive(device), platform)) == path
        assert bounce.archive_path({"archive": {"path": path}, "unmodeled": []}) == path
        assert bounce.archive_path(_parse(_cfg(device), platform)) == ""


class TestTheArchiveHeldTwice:
    """The case H22 makes possible: a document whose archive is the unmodelled block (r4's and
    s1's committed intent, C2700) given `archive.path` as well. Both would render."""

    DOC = {"hostname": "r4", "archive": {"path": "bootflash:mercury-arch"},
           "unmodeled": [{"line": "archive", "children": [" path bootflash:mercury-arch"]}]}

    def test_it_is_named_with_both_operands(self):
        problems = hostvars.archive_problems(self.DOC)
        assert len(problems) == 1
        assert "'bootflash:mercury-arch'" in problems[0] and "path bootflash:mercury-arch" in \
            problems[0].split("unmodelled `archive` block holds", 1)[1]

    def test_either_one_alone_is_no_problem(self):
        modelled = dict(self.DOC, unmodeled=[])
        unmodelled = {k: v for k, v in self.DOC.items() if k != "archive"}
        assert hostvars.archive_problems(modelled) == []
        assert hostvars.archive_problems(unmodelled) == []
        assert hostvars.archive_problems(dict(self.DOC, archive={"path": ""})) == []

    def test_the_editor_refuses_it(self):
        from modules.nsot import intent_edit
        got = intent_edit.validate("r4", hostvars.to_yaml(self.DOC))
        assert got["ok"] is False and got["stage"] == "schema", got
        assert "the configuration archive is held twice" in got["error"]

    def test_the_editor_reads_the_modelled_key_and_refuses_a_misspelled_one(self):
        assert not hostvars.unknown_keys({"archive": {"path": "bootflash:a"}})
        assert hostvars.unknown_keys({"archive": {"pth": "bootflash:a"}}) == \
            [(("archive",), "pth", [])]
