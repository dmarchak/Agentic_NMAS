#!/usr/bin/env python3
"""Undo interface-name expansion inside committed descriptions.

`canonicalise_line()` used to expand every interface reference in a line,
including inside a `description`. A description reading `P2P to r1 Gi3` became
`P2P to r1 GigabitEthernet3` in `host_vars`, so committed intent said the
device should be configured to say something it does not say.

**It hid itself.** Both sides of every comparison went through the same
function, so the expanded text matched the expanded text and the diff came
back clean. Fixing the parser stops new damage and, by making the two sides
disagree again, reveals what is already committed.

This corrects that committed data. It is deliberately narrow:

* **descriptions only** — no other field is read or written;
* a description is corrected **only** when it matches the device's own text
  after canonicalisation, i.e. the difference is exactly the expansion this
  tool caused. A description that genuinely differs from the device is drift,
  which is work to deploy, not damage to repair — and rewriting it here would
  silently discard a pending change;
* **dry run by default.** It prints a unified diff and writes nothing without
  `--write`.

    python3 scripts/nsot_fix_description_ifnames.py --list Default
    python3 scripts/nsot_fix_description_ifnames.py --list Default --write

The source of truth for the correct text is `golden/<device>.cfg` at HEAD —
the device's own captured config, not a re-derivation.
"""

import argparse
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def golden_descriptions(config_text):
    """``{interface name: description}`` exactly as the device wrote it.

    Read from the raw config rather than through the parser: the parser is
    the thing that was corrupting this text, and reading back through it
    would compare a value against itself.
    """
    out, current = {}, ""
    for raw in (config_text or "").splitlines():
        if raw[:1] not in (" ", "\t") and raw.strip():
            current = raw.strip()
            continue
        stripped = raw.strip()
        if current.startswith("interface ") and stripped.startswith("description "):
            out[current[len("interface "):].strip()] = stripped[len("description "):]
    return out


def corrections(committed, config_text):
    """``[(interface, committed_text, device_text)]`` worth correcting."""
    from modules.nsot import ifnames

    device = golden_descriptions(config_text)
    # Keyed on the canonical interface NAME, because the header was expanded
    # legitimately and both sides must agree on which interface is which.
    device_canonical = {ifnames.canonical(name): text
                        for name, text in device.items()}

    found = []
    for entry in (committed.get("interfaces") or []):
        name = entry.get("name") or ""
        have = entry.get("description")
        want = device_canonical.get(ifnames.canonical(name))
        if not name or have is None or want is None or have == want:
            continue
        # ONLY the expansion. If they still differ once both are expanded,
        # this is real drift and belongs in a deploy, not in a repair.
        if ifnames.canonicalise_line(f"description {have}") != \
           ifnames.canonicalise_line(f"description {want}"):
            expanded_have = ifnames._LINE_RE.sub(
                lambda m: ifnames.canonical(f"{m.group(1)}{m.group(2)}"), have)
            expanded_want = ifnames._LINE_RE.sub(
                lambda m: ifnames.canonical(f"{m.group(1)}{m.group(2)}"), want)
            if expanded_have != expanded_want:
                continue
        found.append((name, have, want))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", dest="list_name", default="")
    parser.add_argument("--write", action="store_true",
                        help="commit the correction (default: show the diff)")
    args = parser.parse_args()

    import yaml

    from modules.config import get_current_list_name, get_list_data_dir
    from modules.nsot import hostvars, repo as _repo

    list_name = args.list_name or get_current_list_name()
    repo_dir = os.path.join(get_list_data_dir(list_name), "config_repo")
    if not os.path.isdir(repo_dir):
        print(f"REFUSED: no config_repo for list {list_name!r}")
        return 1

    devices = _repo.devices_at(repo_dir, "HEAD")
    print(f"list    : {list_name}")
    print(f"devices : {len(devices)}\n")

    touched, total = [], 0
    for hostname in sorted(devices):
        committed = hostvars.read_committed(repo_dir, hostname)
        if not committed:
            continue
        config_text = _repo.golden_at(repo_dir, hostname, "HEAD") or ""
        found = corrections(committed, config_text)
        if not found:
            continue

        before = yaml.safe_dump(committed, sort_keys=False, width=100)
        for name, _have, want in found:
            for entry in committed["interfaces"]:
                if entry.get("name") == name:
                    entry["description"] = want
        after = yaml.safe_dump(committed, sort_keys=False, width=100)

        print(f"--- {hostname}: {len(found)} description(s)")
        for name, have, want in found:
            print(f"      {name}")
            print(f"        committed: {have!r}")
            print(f"        device   : {want!r}")
        sys.stdout.writelines(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True),
            fromfile=f"{hostname} (committed)", tofile=f"{hostname} (corrected)"))
        print()
        total += len(found)
        touched.append((hostname, committed))

    if not touched:
        print("nothing to correct.")
        return 0

    print(f"{total} description(s) across {len(touched)} device(s).")
    if not args.write:
        print("\n-- dry run. Re-run with --write to commit.")
        return 0

    for hostname, document in touched:
        hostvars.write_committed(repo_dir, hostname, document)
    result = _repo.save_host_vars(
        list_name, [h for h, _ in touched], actor="description-repair",
        message=("host_vars: restore device's own description text\n\n"
                 "Interface references inside descriptions had been expanded "
                 "by canonicalise_line(), so committed intent said the device "
                 "should say something it does not say. Descriptions only; "
                 "each one restored from golden/<device>.cfg at HEAD."))
    print(f"\n{result}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
