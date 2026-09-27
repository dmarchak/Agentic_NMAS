#!/usr/bin/env python3
"""P.6 measurement 1: make a C8000v launch script boot the VM with NO day-0 config.

Run this on the lab host, against a COPY of the adopted launch patch. It prints
a unified diff and writes nothing unless you pass --write.

    cp ~/labs/dhcp-a/patches/c8000v-launch-adopted.py patches/c8000v-launch-configless.py
    python3 patches/patch-configless.py patches/c8000v-launch-configless.py
    python3 patches/patch-configless.py patches/c8000v-launch-configless.py --write

WHY
---
vrnetlab always gives a C8000v a day-0 config: it writes one into
`config.iso` (`/iosxe_config.txt`, which IOS-XE's CVAC applies at first boot)
and attaches it with `-cdrom`. With no startup config it still builds its own
(`gen_bootstrap_config()`: vrnetlab's user and its Gi1 address). A device with
a startup config never runs AutoInstall, PnP or ZTP, so an unmodified node
cannot show whether it would ask for a config at all. Measured by reading the
adopted script (sha256 e483dd2475b505bd..., identical in all three probe
copies on the lab host, 2026-09-26) before anything booted.

WHAT IT CHANGES, and why each is needed
---------------------------------------
0. THE DISK. Removing the ISO is not enough, found by reading before the
   first boot: the image carries the Cisco base disk AND an overlay the
   image's install step wrote into, ending with `do wr`, so a startup config
   is saved in that overlay's NVRAM. The launch script takes the first
   `.qcow2` in sorted order, which is that overlay, and vrnetlab reuses an
   existing `<disk>-overlay.qcow2` as the run-time overlay. So the variant
   (a) chooses the base and (b) removes the install overlay from this
   container's own layer before the VM starts. Evidence the saved config is
   real: r6's first golden carries `platform console serial` and `license
   boot level ...`, which neither vrnetlab's run-time bootstrap nor the tool's
   generator emits.
1. `-cdrom` is attached only in install mode. At run time the VM boots with
   no config ISO, so IOS-XE has no startup config.
2. The autonomous-mode console wait also accepts IOS-XE's own prompt
   (`Press RETURN to get started`, or the initial configuration dialog). The
   script otherwise marks a node running only on `CVAC-4-CONFIG_DONE`, which a
   configless boot never prints.
3. Those two prompts mark the VM running, and close the script's own console
   session so the operator can attach to it.
4. The 300-quiet-spins watchdog NO LONGER RESTARTS the VM. A configless node
   can be quiet while it discovers, and a silent restart would interrupt the
   very attempt this probe exists to observe, while looking like a normal boot.

Each edit is anchored on text that must occur EXACTLY once, so the patch is
refused rather than applied to a script that differs from the one measured.
"""

import argparse
import difflib
import os
import sys

MARK = "CONFIGLESS (P.6 M1)"

EDITS = (
    (
        "the base disk",
        '        for e in sorted(os.listdir("/")):\n'
        '            if not disk_image and re.search(".qcow2$", e):\n'
        '                disk_image = "/" + e\n',
        '        for e in sorted(os.listdir("/")):\n'
        '            # CONFIGLESS (P.6 M1): the BASE disk, never an overlay. The\n'
        '            # image\'s install step saved its startup config ("do wr") into\n'
        '            # <base>-overlay.qcow2, and that name sorts first, so an\n'
        '            # unpatched script boots from NVRAM that already has a config.\n'
        '            if not disk_image and re.search(".qcow2$", e) and "-overlay" not in e:\n'
        '                disk_image = "/" + e\n',
    ),
    (
        "the install overlay",
        '        super().__init__(username, password, disk_image=disk_image, ram=4096, smp="2")\n',
        '        if not install_mode and disk_image:\n'
        '            # CONFIGLESS (P.6 M1): vrnetlab names the run-time overlay\n'
        '            # <disk>-overlay.qcow2 and REUSES it when it exists, and that is\n'
        '            # the install overlay. Remove it from THIS container\'s writable\n'
        '            # layer (the image is untouched), so the overlay is created\n'
        '            # fresh from the pristine base.\n'
        '            # Said in EVERY case: a line that appears only when something\n'
        '            # is removed cannot tell "patch absent" from "nothing to remove".\n'
        '            logger.warning("CONFIGLESS: booting the base disk %s", disk_image)\n'
        '            install_overlay = re.sub(r"(\\.qcow2)$", r"-overlay\\1", disk_image)\n'
        '            if os.path.exists(install_overlay):\n'
        '                logger.warning("CONFIGLESS: removing %s so the node boots from the pristine base",\n'
        '                               install_overlay)\n'
        '                os.remove(install_overlay)\n'
        '            else:\n'
        '                logger.warning("CONFIGLESS: no install overlay at %s; nothing to remove",\n'
        '                               install_overlay)\n'
        '        super().__init__(username, password, disk_image=disk_image, ram=4096, smp="2")\n',
    ),
    (
        "the config ISO",
        '        self.qemu_args.extend(["-cdrom", "/" + self.image_name])\n',
        '        # CONFIGLESS (P.6 M1): no day-0 config ISO at run time, so IOS-XE\n'
        '        # boots with no startup config and whatever it does to find one\n'
        '        # can be observed. Install mode (image build) still needs it.\n'
        '        if self.install_mode:\n'
        '            self.qemu_args.extend(["-cdrom", "/" + self.image_name])\n',
    ),
    (
        "the console wait",
        '                [b"CVAC-4-CONFIG_DONE", b"IOSXEBOOT-4-FACTORY_RESET"]\n',
        '                [b"CVAC-4-CONFIG_DONE", b"IOSXEBOOT-4-FACTORY_RESET",\n'
        '                 # CONFIGLESS (P.6 M1): IOS-XE\'s own prompt, since a\n'
        '                 # configless boot never prints CONFIG_DONE.\n'
        '                 b"Press RETURN to get started",\n'
        '                 b"initial configuration dialog"]\n',
    ),
    (
        "running without CVAC",
        '        if match:  # got a match!\n',
        '        if match:  # got a match!\n'
        '            if ridx in (2, 3) and self.mode != "controller" and not self.install_mode:\n'
        '                # CONFIGLESS (P.6 M1): the console reached IOS-XE\'s own\n'
        '                # prompt with no day-0 config. Mark running, and release\n'
        '                # the console so the operator can attach to it.\n'
        '                self.logger.info("CONFIGLESS: console ready without a day-0 config (%s)", match)\n'
        '                self.scrapli_tn.close()\n'
        '                self.running = True\n'
        '                return\n',
    ),
    (
        "the restart watchdog",
        '        if self.spins > 300:\n'
        '            # too many spins with no result ->  give up\n'
        '            self.stop()\n'
        '            self.start()\n'
        '            return\n',
        '        if self.spins > 300:\n'
        '            # CONFIGLESS (P.6 M1): NEVER restart. A configless node can be\n'
        '            # quiet while it discovers, and a restart would silently\n'
        '            # interrupt the attempt this probe exists to observe.\n'
        '            self.logger.warning("CONFIGLESS: 300 quiet spins; NOT restarting the VM")\n'
        '            self.spins = 0\n'
        '            return\n',
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
                          "This is not the launch script P.6 measured.")
        text = text.replace(anchor, replacement, 1)
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", help="a COPY of the adopted launch script")
    parser.add_argument("--write", action="store_true",
                        help="apply the change; without it, print the diff only")
    args = parser.parse_args(argv)

    real = os.path.realpath(args.path)
    if "/labs/lab/" in real or "/labs/r6/" in real:
        sys.exit("refusing to edit a production lab's own launch patch. Copy it into the probe first.")
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
