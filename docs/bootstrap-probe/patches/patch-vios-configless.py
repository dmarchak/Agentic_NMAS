#!/usr/bin/env python3
"""C1349, Lab 9: make a vIOS-L2 launch script boot the VM with NO configuration, untouched.

Run this on the lab host, against a COPY of the image's own launch script. It prints a unified
diff and writes nothing unless you pass --write.

    docker exec clab-rcn-lab1-s1 cat /launch.py > ~/labs/lab/patches/vios-launch-configless.py
    python3 patch-vios-configless.py ~/labs/lab/patches/vios-launch-configless.py
    python3 patch-vios-configless.py ~/labs/lab/patches/vios-launch-configless.py --write

WHY
---
vrnetlab's vIOS launcher (`vrnetlab/cisco_vios:L2-20180619`, sha256 794788bcada997da...,
read from s1's container 2026-10-22) types on the console of every node it starts:
- `no` at "Would you like to enter the initial configuration dialog? [yes/no]:";
- three RETURNs at "Press RETURN to get started!";
- at the `Switch>` prompt, the startup file through scrapli, then `write memory`.

With no startup file it does NOT stop (C1349's "fatal" is a log line only): it still answers
the dialog, presses RETURN, logs "Failed to find startup configuration file" and marks the node
running. On classic IOS, AutoInstall runs while that dialog waits, and an answer at it can end
AutoInstall, so an unmodified node cannot show whether a switch would fetch a configuration.
Its watchdog also stops and restarts a VM after 300 quiet console spins, which would cut a
discovery short while looking like a normal boot.

Unlike the C8000v (patch-configless.py, P.6), the image carries ONLY its base disk: the
`-overlay.qcow2` is created at first start (read 2026-10-22 from the image itself), so no disk
edit is needed. Management passthrough is the base class's own `CLAB_MGMT_PASSTHROUGH`, set in
the lab file, not here.

WHAT IT CHANGES, and why each is needed
---------------------------------------
1. A startup file is NAMED in the log and never applied. It was first refused, on the reading
   that containerlab writes none for a node naming none (r6's config folder was empty), but
   that holds for the C8000v kind only: for `cisco_vios` containerlab writes a default, and the
   refusal stopped Lab 9's s5 at its first boot (C1534, 2026-10-22). Only apply_config reads the
   file, and this launch never calls it.
2. The console is left alone. At the dialog, at "Press RETURN", or at a prompt, the script
   types nothing, marks the VM running and closes its own console session, so AutoInstall runs
   uninterrupted and the operator can attach to the console (Lab 9's fallback types the minimal
   configuration there by hand).
3. The 300-quiet-spins watchdog NO LONGER RESTARTS the VM.

Each edit is anchored on text that must occur EXACTLY once, so the patch is refused rather than
applied to a script that differs from the one read.
"""

import argparse
import difflib
import os
import sys

MARK = "CONFIGLESS (C1349)"

EDITS = (
    (
        "a startup file named, never applied",
        "        self.hostname = hostname\n"
        "        self.conn_mode = conn_mode\n"
        "        self.device_type = device_type\n",
        "        # CONFIGLESS (C1349): this launch types no configuration. containerlab writes a\n"
        "        # default startup file for this kind even when the node names none (C1534: Lab 9's\n"
        "        # s5, 2026-10-22), and only apply_config reads it, which this launch never calls.\n"
        "        # So a startup file is NAMED in the log, never applied and never silently ignored.\n"
        "        if os.path.exists(STARTUP_CONFIG_FILE):\n"
        "            self.logger.warning(\"CONFIGLESS: %s exists (containerlab's default for this \"\n"
        "                                \"kind); it is never applied\", STARTUP_CONFIG_FILE)\n"
        "        else:\n"
        "            self.logger.warning(\"CONFIGLESS: no startup file\")\n"
        "        self.logger.warning(\"CONFIGLESS: the console is left to AutoInstall\")\n"
        "        self.hostname = hostname\n"
        "        self.conn_mode = conn_mode\n"
        "        self.device_type = device_type\n",
    ),
    (
        "the restart watchdog",
        "        if self.spins > 300:\n"
        "            # too many spins with no result -> give up\n"
        "            self.stop()\n"
        "            self.start()\n"
        "            return\n",
        "        if self.spins > 300:\n"
        "            # CONFIGLESS (C1349): NEVER restart. A configless switch can be quiet while it\n"
        "            # discovers, and a restart would cut AutoInstall short while looking like a boot.\n"
        "            self.logger.warning(\"CONFIGLESS: 300 quiet spins; NOT restarting the VM\")\n"
        "            self.spins = 0\n"
        "            return\n",
    ),
    (
        "nothing typed on the console",
        "        if match:\n"
        "            if ridx == 0:\n"
        "                self.logger.info(\"Skipping initial configuration dialog\")\n"
        "                self.wait_write(\"no\", wait=None)\n"
        "            elif ridx == 1:\n"
        "                self.logger.info(\"Entering user EXEC mode\")\n"
        "                for _ in range(3):\n"
        "                    self.wait_write(\"\\r\", wait=None)\n"
        "            elif ridx == 2:\n"
        "                self.apply_config()\n"
        "\n"
        "                # startup time\n"
        "                startup_time = datetime.datetime.now() - self.start_time\n"
        "                self.logger.info(f\"Startup complete in: {startup_time}\")\n"
        "                # mark as running\n"
        "                self.running = True\n"
        "                return\n",
        "        if match:\n"
        "            # CONFIGLESS (C1349): the dialog, \"Press RETURN\" or a prompt: the VM is up. Type\n"
        "            # NOTHING (an answer at the dialog can end AutoInstall), mark it running, and\n"
        "            # release the console so the operator can attach to it.\n"
        "            startup_time = datetime.datetime.now() - self.start_time\n"
        "            self.logger.warning(\"CONFIGLESS: console state %d after %s with no \"\n"
        "                                \"configuration; typing nothing, console released\",\n"
        "                                ridx, startup_time)\n"
        "            self.scrapli_tn.close()\n"
        "            self.running = True\n"
        "            return\n",
    ),
)


class Refused(Exception):
    pass


def patch(text):
    """The patched script. Raises Refused unless every anchor occurs exactly once."""
    if MARK in text:
        raise Refused("already patched: the file carries the configless mark")
    for name, anchor, replacement in EDITS:
        count = text.count(anchor)
        if count != 1:
            raise Refused(f"{name}: expected its anchor exactly once, found {count}. "
                          "This is not the vIOS launch script that was read.")
        text = text.replace(anchor, replacement, 1)
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", help="a COPY of the image's launch script")
    parser.add_argument("--write", action="store_true",
                        help="apply the change; without it, print the diff only")
    args = parser.parse_args(argv)
    if os.path.realpath(args.path) == "/launch.py":
        sys.exit("refusing to edit a container's own /launch.py. Copy it out first.")
    with open(args.path, encoding="utf-8") as fh:
        before = fh.read()
    try:
        after = patch(before)
    except Refused as exc:
        sys.exit(f"REFUSED: {exc}")
    compile(after, args.path, "exec")           # a patch that does not parse is refused too
    sys.stdout.writelines(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), args.path, args.path + " (configless)"))
    if not args.write:
        print("\n-- diff only. Re-run with --write to apply.")
        return 0
    with open(args.path, "w", encoding="utf-8") as fh:
        fh.write(after)
    print(f"\nwritten: {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
