#!/usr/bin/env python3
"""Lab 9 (docs/LAB9_PLAN.md step 4): the lab repository's two changes, anchored.

LAB TOOLING, not the product. Run on the lab host against the lab repository; it prints a
unified diff of each file and writes nothing unless you pass --write:

    python3 patch-lab9.py ~/labs/lab
    python3 patch-lab9.py ~/labs/lab --write

1. `rcn-lab1.clab.yml` (decided by the operator, 2026-10-22: D2, D6):
   - the routers' and hosts' CPU set goes from 0-19 to 0-18, so CPU 19 is s5's alone;
   - R8's `wait-for` stage goes (C1475: a stage holds every node's management link until the
     held node exists); option (b) removes R6's and R7's, so no stage is left;
   - s5, Lab 9's switch, joins configless under the vIOS configless launcher
     (`patches/vios-launch-configless.py`, made by docs/bootstrap-probe/patches/
     patch-vios-configless.py), with management passthrough so the emulator's own DHCP never
     answers AutoInstall first (the switches' kind sets it false for `ip address dhcp`);
   - h6 and h7, the hosts on s5's VLAN 10, run the Labs 8 and 9 host script;
   - the three links the file's own comment planned: R8 Gi3 to s5 Gi0/1 (10.255.4.12/30),
     s5 Gi0/2 to h6 and s5 Gi0/3 to h7, with the MACs that comment pinned.
2. `configs/host-net-lab89.sh`: once the first lease is in, a DHCP client that STAYS and renews
   (`udhcpc -q` above it quits once it has a lease and never renews: Lab 8's H5 had its client
   started again by hand).

Each edit is anchored on text that must occur EXACTLY once in its file, so a file that differs
from the one read (the lab file at sha256 c23c5d4014d5..., the lab repository's 33916b7 and
da1c954) is refused rather than edited.
"""

import argparse
import difflib
import os
import sys

MARK = "Lab 9 (LAB9_PLAN step 4)"

LABFILE_EDITS = (
    (
        "the routers' CPU set",
        "      image: vrnetlab/cisco_c8000v:17.06.01a\n"
        "      cpu-set: \"0-19\"\n",
        "      image: vrnetlab/cisco_c8000v:17.06.01a\n"
        "      cpu-set: \"0-18\"                    # Lab 9 (LAB9_PLAN step 4): CPU 19 is s5's\n",
    ),
    (
        "the hosts' CPU set",
        "      image: ghcr.io/hellt/network-multitool\n"
        "      cpu-set: \"0-19\"\n",
        "      image: ghcr.io/hellt/network-multitool\n"
        "      cpu-set: \"0-18\"\n",
    ),
    (
        "the CPU sets' comment",
        "    # host stays off CPUs 20-23; each switch takes one of them (below). A node's own cpu-set\n",
        "    # host stays off CPUs 19-23 (19 since Lab 9, for s5); each switch takes one of them\n"
        "    # (below). A node's own cpu-set\n",
    ),
    (
        "r8's stage (C1475)",
        "      stages:\n"
        "        create:\n"
        "          wait-for:\n"
        "            - {node: r2, stage: healthy}\n",
        "      # No stage (C1475: a stage holds EVERY node's management link until the held node\n"
        "      # exists, s3's to br-mgmt among them). R8 is reloaded after its Add device, as R6 was.\n",
    ),
    (
        "s5",
        "    # s5 (Lab 9's switch, 172.20.20.25), h6 and h7 join at the next declared full redeploy,\n"
        "    # after Lab 9's 0a measures the vIOS configless boot (the operator, 2026-10-20: option 1).\n",
        "    s5:\n"
        "      kind: cisco_vios\n"
        "      mgmt-ipv4: 172.20.20.25              # Lab 9's switch behind R8, configless until ZTP\n"
        "      cpu-set: \"19\"                        # a CPU of its own (LAB9_PLAN D6)\n"
        "      env:\n"
        "        # Lab 9 (LAB9_PLAN step 4): no emulator DHCP may answer AutoInstall first.\n"
        "        CLAB_MGMT_PASSTHROUGH: \"true\"\n"
        "      binds:\n"
        "        # Types nothing on the console, never restarts a quiet VM, refuses a startup file.\n"
        "        - patches/vios-launch-configless.py:/launch.py\n",
    ),
    (
        "h6 and h7",
        "        - sh -c \"nohup /etc/host-net-lab89.sh h5 > /tmp/host-net.log 2>&1 &\"\n",
        "        - sh -c \"nohup /etc/host-net-lab89.sh h5 > /tmp/host-net.log 2>&1 &\"\n"
        "    h6:\n"
        "      kind: linux\n"
        "      mgmt-ipv4: 172.20.20.36              # VLAN 10 access on s5, behind R8\n"
        "      binds:\n"
        "        - configs/host-net-lab89.sh:/etc/host-net-lab89.sh\n"
        "      exec:\n"
        "        - sh -c \"nohup /etc/host-net-lab89.sh h6 > /tmp/host-net.log 2>&1 &\"\n"
        "    h7:\n"
        "      kind: linux\n"
        "      mgmt-ipv4: 172.20.20.37              # VLAN 10 access on s5, behind R8 (the handout's \"H1\")\n"
        "      binds:\n"
        "        - configs/host-net-lab89.sh:/etc/host-net-lab89.sh\n"
        "      exec:\n"
        "        - sh -c \"nohup /etc/host-net-lab89.sh h7 > /tmp/host-net.log 2>&1 &\"\n",
    ),
    (
        "the three links",
        "    # At the next redeploy (option 1): r8 Gi3 (aa:bb:cc:00:04:18) - s5 Gi0 (CLI Gi0/1,\n"
        "    # aa:bb:cc:00:04:25), 10.255.4.12/30; s5 Gi1 - h6 eth1 (aa:bb:cc:00:80:06) and s5 Gi2 - h7\n"
        "    # eth1 (aa:bb:cc:00:80:07), VLAN 10 access, 10.80.10.0/24.\n",
        "    - type: veth                            # 10.255.4.12/30: R8 .13 (relay), s5 VLAN 1 .14; VLAN 10 tagged\n"
        "      endpoints:\n"
        "        - {node: r8, interface: Gi3, mac: \"aa:bb:cc:00:04:18\"}\n"
        "        - {node: s5, interface: Gi0, mac: \"aa:bb:cc:00:04:25\"}   # s5 CLI Gi0/1\n"
        "    - type: veth                            # s5 CLI Gi0/2, VLAN 10 access: H6 by DHCP (10.80.10.0/24)\n"
        "      endpoints:\n"
        "        - {node: h6, interface: eth1, mac: \"aa:bb:cc:00:80:06\"}\n"
        "        - {node: s5, interface: Gi1}\n"
        "    - type: veth                            # s5 CLI Gi0/3, VLAN 10 access: H7 by DHCP (10.80.10.0/24)\n"
        "      endpoints:\n"
        "        - {node: h7, interface: eth1, mac: \"aa:bb:cc:00:80:07\"}\n"
        "        - {node: s5, interface: Gi2}\n",
    ),
)

HOSTNET_EDITS = (
    (
        "a client that renews",
        "log \"done after $i tries: $(ip -4 addr show dev \"$IF\" | grep -o 'inet [0-9.]*') "
        "$(ip -6 addr show dev \"$IF\" scope global | grep -o 'inet6 [0-9a-f:]*')\"\n",
        "log \"done after $i tries: $(ip -4 addr show dev \"$IF\" | grep -o 'inet [0-9.]*') "
        "$(ip -6 addr show dev \"$IF\" scope global | grep -o 'inet6 [0-9a-f:]*')\"\n"
        "# 4. Lab 9 (LAB9_PLAN step 4): keep the lease. `udhcpc -q` above quits once it has one and\n"
        "#    never renews (Lab 8's H5 had its client started again by hand). This client stays,\n"
        "#    renews at T1, and retries for ever if the server goes away (-t 0, 5 s apart).\n"
        "udhcpc -i \"$IF\" -b -t 0 -T 3 -A 5 >/dev/null 2>&1\n"
        "log \"renewing client started on $IF\"\n",
    ),
)

FILES = (("rcn-lab1.clab.yml", LABFILE_EDITS), ("configs/host-net-lab89.sh", HOSTNET_EDITS))


class Refused(Exception):
    pass


def patch(text, edits, name):
    """The patched file. Raises Refused unless every anchor occurs exactly once."""
    if MARK in text:
        raise Refused(f"{name}: already patched (it carries the Lab 9 mark)")
    for what, anchor, replacement in edits:
        count = text.count(anchor)
        if count != 1:
            raise Refused(f"{name}: {what}: expected its anchor exactly once, found {count}. "
                          "This is not the file that was read.")
        text = text.replace(anchor, replacement, 1)
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("labdir", help="the lab repository (the folder holding rcn-lab1.clab.yml)")
    parser.add_argument("--write", action="store_true",
                        help="apply the changes; without it, print the diffs only")
    args = parser.parse_args(argv)
    out = []
    for rel, edits in FILES:
        path = os.path.join(args.labdir, rel)
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        try:
            after = patch(before, edits, rel)
        except Refused as exc:
            sys.exit(f"REFUSED: {exc}")
        out.append((path, before, after))
    import yaml  # the lab host's python3 has PyYAML (containerlab's helpers use it)
    yaml.safe_load(out[0][2])  # a lab file that does not parse is refused too
    for path, before, after in out:
        sys.stdout.writelines(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), path, path + " (Lab 9)"))
    if not args.write:
        print("\n-- diffs only. Re-run with --write to apply.")
        return 0
    for path, _before, after in out:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(after)
        print(f"written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
