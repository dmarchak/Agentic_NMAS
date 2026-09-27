#!/usr/bin/env python3
"""P.6 measurement 5: does a reservation survive a reload AND a restart?

Talks to kea-dhcp4's own control socket (not the Control Agent), so it needs
no API credential and no netcat. The socket is `_kea`-owned and connecting to
a unix socket needs write permission, so run it with sudo:

    sudo python3 kea-m5.py show
    sudo python3 kea-m5.py reload
    sudo python3 kea-m5.py control-set aa:bb:cc:00:02:51 10.255.0.51

`show` prints subnet 255's reservations and option data as the RUNNING server
holds them. `reload` asks Kea to re-read its config file (and therefore the
include). `control-set` is the CONTROL: it adds one reservation to the
running config through `config-set` alone, which changes memory and no file,
so it is predicted to be gone after a restart.

It never writes a file, and never calls config-write.
"""

import argparse
import json
import socket
import sys

SOCKET = "/run/kea/kea4-ctrl-socket"
SUBNET_ID = 255


class Refused(Exception):
    pass


def request(command, arguments=None, path=None, timeout=10.0):
    """One command, one response, from Kea's unix control socket."""
    path = path or SOCKET
    body = {"command": command}
    if arguments is not None:
        body["arguments"] = arguments
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(path)
        s.sendall(json.dumps(body).encode())
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf)
            except ValueError:
                continue
    if not buf:
        raise Refused(f"{command}: Kea closed the socket without answering")
    return json.loads(buf)


def subnet(config_args, subnet_id=SUBNET_ID):
    """The subnet entry from config-get's arguments. Refuses if it is absent."""
    found = [s for s in (config_args.get("Dhcp4") or {}).get("subnet4", [])
             if s.get("id") == subnet_id]
    if len(found) != 1:
        raise Refused(f"subnet {subnet_id}: expected exactly one, found {len(found)}")
    return found[0]


def reservations_of(config_args, subnet_id=SUBNET_ID):
    return [(r.get("hw-address"), r.get("ip-address"))
            for r in subnet(config_args, subnet_id).get("reservations") or []]


def with_reservation(config_args, mac, ip, subnet_id=SUBNET_ID):
    """A copy of config-get's arguments with one reservation added to one
    subnet, ready for config-set. Refuses a MAC or an address already
    reserved there, and drops config-get's `hash`, which is a read-only
    fingerprint and not part of a configuration."""
    new = json.loads(json.dumps(config_args))
    new.pop("hash", None)
    target = subnet(new, subnet_id)
    for have_mac, have_ip in reservations_of(new, subnet_id):
        if (have_mac or "").lower() == mac.lower():
            raise Refused(f"{mac} is already reserved in subnet {subnet_id} (-> {have_ip})")
        if have_ip == ip:
            raise Refused(f"{ip} is already reserved in subnet {subnet_id} (for {have_mac})")
    target.setdefault("reservations", []).append({"hw-address": mac, "ip-address": ip})
    return new


def _ok(resp, command):
    if resp.get("result") != 0:
        raise Refused(f"{command}: result {resp.get('result')}: {resp.get('text')}")
    return resp


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("show")
    sub.add_parser("reload")
    ctl = sub.add_parser("control-set")
    ctl.add_argument("mac")
    ctl.add_argument("ip")
    args = parser.parse_args(argv)
    try:
        if args.action == "reload":
            resp = _ok(request("config-reload"), "config-reload")
            print(f"config-reload: result 0: {resp.get('text')}")
            return 0
        got = _ok(request("config-get"), "config-get")["arguments"]
        if args.action == "show":
            s = subnet(got)
            print(f"subnet {SUBNET_ID} {s.get('subnet')} as the RUNNING server holds it:")
            rows = reservations_of(got)
            for mac, ip in rows:
                print(f"  reservation {mac} -> {ip}")
            print(f"  {len(rows)} reservation(s); option-data: "
                  f"{[o.get('name') or o.get('code') for o in s.get('option-data') or []]}")
            return 0
        new = with_reservation(got, args.mac, args.ip)
        resp = _ok(request("config-set", new), "config-set")
        print(f"config-set: result 0: {resp.get('text')}")
        print("in MEMORY only: no file was written, and config-write was not called")
        return 0
    except (Refused, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
