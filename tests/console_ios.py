"""What an IOS console answers the static kick-start's read-back and copy with, for the fake
console (tests/console_fakes.py): out-of-band ZTP's C1592 to C1594
(modules/nsot/console_kickstart.py).

Built in the shape of the captured session (tests/fixtures/console/: the echo, a line break,
the answer, the next prompt). The reads' answers follow IOS's documented `show running-config`
normalisation, which the read-back compares against: a section's header, its settings indented
one space, ``end``; ``no shutdown`` printed as nothing, ``switchport access vlan 1`` (the
default) left out, and the lines IOS adds on its own (``media-type rj45``, ``negotiation auto``
on a vIOS-L2 port). The copy's answer is IOS's documented wording: NOT captured on vIOS-L2 yet
(no copy has been run on s5); its first run is the measurement.

A helper, not a test module."""

import os

from modules.nsot import console_kickstart as K


def echo(line: str, prompt: str) -> bytes:
    """The console's answer to *line*: its echo, a line break, and *prompt*."""
    return f"{line}\r\n{prompt}".encode()


def _crlf(lines) -> str:
    return "".join(f"{line}\r\n" for line in lines)


def running(lines) -> dict:
    """The running configuration a device that took every one of *lines* holds, as IOS prints
    it: ``{"hostname", "globals": [line], "sections": {header: [body line]}}``."""
    out = {"hostname": "", "globals": [], "sections": {}}
    header = ""
    for raw in lines:
        text = raw.strip()
        if text in K.CONTROL:
            header = ""
            continue
        if raw[:1] != " ":
            header = ""
            if text.startswith("interface ") or text == K.CONSOLE_LINE:
                header = text
                out["sections"].setdefault(header, [])
            elif text.startswith("hostname "):
                out["hostname"] = text.split()[1]
                out["globals"].append(text)
            elif not text.startswith("vlan "):
                out["globals"].append(text)
            continue
        body = out["sections"].setdefault(header, [])
        if text == "no shutdown" or text == "switchport access vlan 1":
            continue                       # IOS prints nothing for either
        body.append(" " + text)
    for header, body in out["sections"].items():
        if header.startswith("interface Gi"):
            body += [" media-type rj45", " negotiation auto"]
    return out


#: s1's real `show interfaces Vlan10` (tests/fixtures/console/vios_l2_show_interfaces_vlan10.txt,
#: read 2026-10-23 through Mercury's Show commands): the MAC read's answer, its interface name
#: and address substituted for the device read.
SHOW_INTERFACE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "console",
                              "vios_l2_show_interfaces_vlan10.txt")
FIXTURE_MAC = "0c00.6ce9.800a"


def show_interface(name: str, mac: str = FIXTURE_MAC) -> str:
    """The real capture, as *name*'s, carrying *mac*."""
    with open(SHOW_INTERFACE, encoding="ascii") as fh:
        text = fh.read()
    return text.replace("Vlan10", name).replace(FIXTURE_MAC, mac)


def read_answer(command: str, config: dict, prompt: str) -> bytes:
    """IOS's answer to one read-back *command* on *config* (`running`'s), echo to *prompt*."""
    if command.startswith("show interfaces "):
        text = show_interface(command.split()[-1], config.get("mac", FIXTURE_MAC)).splitlines()
    elif command.startswith("show running-config interface "):
        header = "interface " + command.split()[-1]
        body = config["sections"].get(header)
        text = (["Building configuration...", "", "Current configuration : 99 bytes", "!"]
                + ([header] + body if body is not None else []) + ["end", ""])
    elif command.startswith(K.READ_SECTION.format(header="")):
        header = command.split("| section ", 1)[1]
        text = [header] + config["sections"].get(header, [])
    else:
        keys = command.split("| include ", 1)[1].split("|")
        text = [g for g in config["globals"]
                if any(g.startswith(k.lstrip("^") + " ") for k in keys)]
    return f"{command}\r\n{_crlf(text)}{prompt}".encode()


def readback_answers(lines, prompt: str, config: dict = None) -> list:
    """The answers to every read the kick-start of *lines* makes, in order, from *config*
    (default: a device that took every line)."""
    config = config or running(lines)
    return [read_answer(cmd, config, prompt) for cmd in K.readback_plan(lines)["reads"]]


def copy_answers(line: str, prompt: str, *, size: int = 1203, via: str = "Vlan10",
                 transfer: str = None) -> list:
    """IOS's two answers to the copy *line*: its destination question, then (after RETURN) the
    transfer, by IOS's documented wording, ending at *prompt*; *transfer* replaces the
    transfer's lines (a failure, a refusal inside the copied file)."""
    url = line.split()[1]
    server, name = url[len("tftp://"):].split("/", 1)
    if transfer is None:
        transfer = _crlf([f"Accessing {url}...", f"Loading {name} from {server} (via {via}): !",
                          f"[OK - {size} bytes]", "",
                          f"{size} bytes copied in 0.123 secs (9780 bytes/sec)"])
    return [f"{line}\r\nDestination filename [running-config]? ".encode(),
            f"\r\n{transfer}{prompt}".encode()]
