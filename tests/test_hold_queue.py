"""An interface's hold queues as a modelled intent key, `hold_queue` (C1485, the operator,
2026-10-21: s3's Gi1/1 toward the manager printed "Output queue: 0/0 (size/max)" and dropped
5.65% of its output, 5.5 packets a second, every burst of the routers' telemetry; the change
goes through intent like any other, never as an acknowledged unmodelled line).

On s3's REAL configuration (tests/fixtures/configs/fleet/s3.cfg): the parser reads
`hold-queue <n> in|out` into the interface's `hold_queue` list, the template sends it back where
the macro writes an interface's own lines, a round trip keeps it, and a deploy program adding it
to Gi1/1 sends exactly the interface and the one line, merge-only."""

import copy
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S3 = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "s3.cfg")


def _s3():
    with open(S3, encoding="utf-8") as fh:
        return fh.read()


def _parse(text):
    from modules.nsot.parsers import get_parser
    return get_parser("cisco_ios").parse(text)


def _iface(hv, name):
    return next(i for i in hv["interfaces"] if i["name"] == name)


def _with_hold_queue(text, line=" hold-queue 256 out"):
    """s3's configuration with *line* under Gi1/1, as IOS prints an interface's own lines."""
    out, inside = [], False
    for l in text.splitlines():
        if inside and not l.startswith(" "):
            out.append(line)
            inside = False
        out.append(l)
        if l == "interface GigabitEthernet1/1":
            inside = True
    assert any(l == line for l in out), "floor: s3's capture has its Gi1/1"
    return "\n".join(out) + "\n"


def test_the_parser_reads_each_direction_into_the_key_and_nothing_into_unmodeled():
    hv = _parse(_with_hold_queue(_with_hold_queue(_s3()), " hold-queue 150 in"))
    gi = _iface(hv, "GigabitEthernet1/1")
    assert sorted(gi["hold_queue"]) == ["150 in", "256 out"]
    assert not [l for l in gi.get("unmodeled") or [] if "hold-queue" in l]


def test_an_interface_without_one_holds_an_empty_list():
    assert _iface(_parse(_s3()), "GigabitEthernet1/1")["hold_queue"] == []


def test_the_template_sends_it_back_and_a_round_trip_keeps_it():
    from modules.nsot import roundtrip
    hv = _parse(_with_hold_queue(_s3()))
    rendered = roundtrip.render(hv, "cisco_ios")
    block = rendered.split("interface GigabitEthernet1/1\n", 1)[1].split("\n!", 1)[0]
    assert " hold-queue 256 out" in block.splitlines()
    assert _iface(_parse(rendered), "GigabitEthernet1/1")["hold_queue"] == ["256 out"]


def test_a_deploy_adds_exactly_the_line_under_its_interface():
    from modules.nsot import deploy, roundtrip
    hv = _parse(_s3())
    want = copy.deepcopy(hv)
    _iface(want, "GigabitEthernet1/1")["hold_queue"] = ["256 out"]
    program = deploy.merge_commands(roundtrip.render(want, "cisco_ios"),
                                    roundtrip.render(hv, "cisco_ios"))
    assert program == ["interface GigabitEthernet1/1", " hold-queue 256 out", "exit"], program
