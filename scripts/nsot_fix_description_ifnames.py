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


#: Why a description was not corrected. A skip is a FINDING, not a quiet
#: no-op: the mixed case -- expansion damage plus a real edit on the same
#: line -- looks exactly like "nothing to do" unless it is named.
SKIP_BEYOND = "differs beyond the expansion (pending intent?)"
SKIP_NO_DEVICE_TEXT = "the device has no description on this interface"
SKIP_NO_INTERFACE = "the device does not have this interface"


def golden_interfaces(config_text):
    """Canonical names of EVERY ``interface`` header in the config.

    Distinct from :func:`golden_descriptions`, which only knows the ones that
    carry a description. Conflating the two made "this interface has no
    description" indistinguishable from "this interface is not on the device",
    so every undescribed interface was reported as a loud skip -- ten of them
    on the fleet fixtures, all false.
    """
    from modules.nsot import ifnames

    names = set()
    for raw in (config_text or "").splitlines():
        if raw[:1] in (" ", "\t") or not raw.strip():
            continue
        if raw.strip().startswith("interface "):
            names.add(ifnames.canonical(raw.strip()[len("interface "):].strip()))
    return names


def _expanded(text):
    """What the OLD canonicaliser would have made of this text.

    Used to decide whether two strings differ *only* by the expansion this
    tool caused: expand both and see whether they land on the same value.
    """
    from modules.nsot import ifnames

    return ifnames._LINE_RE.sub(
        lambda m: ifnames.canonical(f"{m.group(1)}{m.group(2)}"), text or "")


def classify(committed, config_text):
    """Sort every committed description into fix / skip / already correct.

    One pass and one producer. An earlier version returned only the fixable
    ones, which made "nothing was skipped" and "something was skipped
    silently" the same output -- and the silent case is precisely the
    dangerous one, because a description carrying BOTH expansion damage and a
    real edit looks like nothing to do.
    """
    from modules.nsot import ifnames

    device = golden_descriptions(config_text)
    # Keyed on the canonical interface NAME: the header was expanded
    # legitimately, so both sides must agree on which interface is which.
    device_canonical = {ifnames.canonical(name): text
                        for name, text in device.items()}
    interfaces = golden_interfaces(config_text)

    fix, skip, correct = [], [], 0
    for entry in (committed.get("interfaces") or []):
        name = entry.get("name") or ""
        have = entry.get("description")
        if not name or have is None:
            continue
        key = ifnames.canonical(name)
        want = device_canonical.get(key)

        if want is None:
            if key not in interfaces:
                skip.append((name, have, "", SKIP_NO_INTERFACE))
            elif not have:
                # Both sides say nothing. The parser writes `description: ''`
                # for an undescribed interface, which agrees with a device
                # that has no description line -- there is nothing here.
                correct += 1
            else:
                # Committed intent wants a description this device does not
                # have. That is drift to deploy, not damage to repair.
                skip.append((name, have, "", SKIP_NO_DEVICE_TEXT))
            continue
        if have == want:
            correct += 1
            continue
        if _expanded(have) == _expanded(want):
            fix.append((name, have, want))
        else:
            # Real drift -- a pending change waiting to be deployed. Repairing
            # it would discard somebody's work while claiming to fix
            # formatting, so it is reported and left alone.
            skip.append((name, have, want, SKIP_BEYOND))
    return {"fix": fix, "skip": skip, "correct": correct}


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

    touched, total_fixed, total_correct = [], 0, 0
    skipped = []
    for hostname in sorted(devices):
        committed = hostvars.read_committed(repo_dir, hostname)
        if not committed:
            continue
        config_text = _repo.golden_at(repo_dir, hostname, "HEAD") or ""
        found = classify(committed, config_text)
        total_correct += found["correct"]

        if not found["fix"] and not found["skip"]:
            # Reported even when there is nothing to do, so "this device was
            # examined and was clean" is distinguishable from "this device
            # was never reached".
            print(f"--- {hostname}: nothing to change "
                  f"({found['correct']} already correct)")
            continue

        print(f"--- {hostname}: {len(found['fix'])} to fix, "
              f"{len(found['skip'])} SKIPPED, "
              f"{found['correct']} already correct")

        for name, have, want in found["fix"]:
            print(f"      {name}")
            print(f"        committed: {have!r}")
            print(f"        device   : {want!r}")

        for name, have, want, reason in found["skip"]:
            skipped.append((hostname, name, have, want, reason))
            print(f"  !!  SKIPPED {name} — {reason}")
            print(f"        committed: {have!r}")
            print(f"        device   : {want!r}")

        if not found["fix"]:
            print()
            continue

        before = yaml.safe_dump(committed, sort_keys=False, width=100)
        for name, _have, want in found["fix"]:
            for entry in committed["interfaces"]:
                if entry.get("name") == name:
                    entry["description"] = want
        after = yaml.safe_dump(committed, sort_keys=False, width=100)
        sys.stdout.writelines(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True),
            fromfile=f"{hostname} (committed)", tofile=f"{hostname} (corrected)"))
        print()
        total_fixed += len(found["fix"])
        touched.append((hostname, committed))

    print(f"{total_fixed} description(s) to fix across {len(touched)} device(s); "
          f"{total_correct} already correct; {len(skipped)} SKIPPED.")

    if skipped:
        # Loud, last, and non-zero. A skip scrolled past is the mixed case --
        # expansion damage plus a real edit -- going unnoticed, which is the
        # one outcome this report exists to prevent.
        print("\n" + "=" * 70)
        print(f"WARNING: {len(skipped)} description(s) were NOT corrected.")
        print("Each differs from the device by more than the expansion, so it")
        print("may be pending intent waiting to be deployed. Review each one:")
        for hostname, name, have, want, reason in skipped:
            print(f"  {hostname} {name} — {reason}")
            print(f"      committed: {have!r}")
            print(f"      device   : {want!r}")
        print("=" * 70)

    if not touched:
        print("\nnothing to correct.")
        return 2 if skipped else 0

    if not args.write:
        print("\n-- dry run. Re-run with --write to commit.")
        return 2 if skipped else 0

    # write_committed(repo, host_vars) -- TWO arguments. It takes the
    # hostname from the document itself, so a document missing that field
    # would be written as `unknown.yml`. Checked rather than assumed.
    missing = [h for h, d in touched if not d.get("hostname")]
    if missing:
        print(f"\nREFUSED: no `hostname` field in committed intent for "
              f"{', '.join(missing)}. write_committed() names the file from "
              f"that field; without it the repair would write unknown.yml.")
        return 1

    # ATOMIC. Validate every document before writing any, then keep the
    # original bytes so a failure part-way through restores what was there.
    # A repair that leaves four of nine devices rewritten is worse than one
    # that does nothing: the next run reads a half-corrected repository as
    # its starting point.
    for hostname, document in touched:
        text = hostvars.to_yaml(document)
        try:
            hostvars.assert_no_secret_values(text, hostname)
            hostvars.assert_printable(text, hostname)
        except Exception as exc:                # noqa: BLE001
            print(f"\nREFUSED: {hostname} would not pass the committed-intent "
                  f"guards: {type(exc).__name__}: {exc}")
            return 1

    originals = {}
    for hostname, _document in touched:
        path = hostvars.committed_path(repo_dir, hostname)
        try:
            with open(path, "rb") as handle:
                originals[path] = handle.read()
        except OSError:
            originals[path] = None

    try:
        for _hostname, document in touched:
            hostvars.write_committed(repo_dir, document)
    except Exception as exc:                    # noqa: BLE001
        for path, blob in originals.items():
            if blob is None:
                if os.path.exists(path):
                    os.remove(path)
            else:
                with open(path, "wb") as handle:
                    handle.write(blob)
        print(f"\nFAILED while writing: {type(exc).__name__}: {exc}")
        print("every file was restored to its previous contents; "
              "nothing was committed.")
        return 1

    # save_host_vars() makes ONE commit over the whole host_vars path. Not one
    # commit per device: this is a single repair, and nine commits would make
    # the history describe nine decisions that nobody took separately.
    result = _repo.save_host_vars(
        list_name, [h for h, _ in touched], actor="description-repair",
        message="host_vars: restore description text (ifname expansion, 1.4)")
    print(f"\n{result}")
    if not result.get("ok"):
        return 1
    return 2 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
