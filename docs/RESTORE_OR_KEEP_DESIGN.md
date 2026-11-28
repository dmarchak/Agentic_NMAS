# Restore or keep: one choice whenever a device departs from intent (design note)

The operator's order, 2026-11-27 (after r8's baseline was refused, "+4 -27", and r8's intent had
to be drafted by hand, as r6's and r7's were for Lab 9): "a 'Restore or keep' choice whenever a
device departs from intent. Show the diff, then two actions: 'Restore intent': a true config
replace (configure replace, or the startup-plus-reload revert where replace isn't supported),
previewed, approved, then verified; 'Keep device': update intent from the running config,
previewed and committed. Prerequisite: the comparison ignores each platform's known printed
defaults (IOS-XE: mop, mgcp, license level, spanning-tree extend system-id, and so on), so a
restored device can actually show 'at intent'." Charter: CORE (intent is the source of truth,
and a departure that cannot be ended either way leaves a device outside it). A plan item:
docs/plan/week-2026-11-23.md, Stage 6.

## The industry need

A network engineer finds a device that differs from what it should be, and has to decide one of
two things: the device is wrong (put it back), or the record is wrong (the change was right;
record it). Commercial tools offer both. Cisco NSO's `sync-to` pushes the model onto the device
and `sync-from` takes the device into the model, each previewed as a diff (`compare-config`).
Nautobot's and NetBox's golden-config compliance shows the difference per feature and offers a
remediation (intended lines rendered as commands) or a backup to re-baseline. Ansible's
`*_config` modules with `replace: config`, and IOS's own `configure replace`, make a device equal
to a file. Mercury meets the need when one screen shows the difference, offers both answers, and
each answer ends with the device at intent, verified, the way every Mercury operation does:
preview, confirm by hash, apply holding the device, verify, roll back on failure, record. It
improves on them in two ways: "Restore" is a real replace (exactly intent, nothing left over),
proven by the same comparison that found the departure; and "Keep" commits intent through the
Intent editor's own two diffs, so the person reads what changes in intent and what a deploy of it
would send.

## What exists today

| Piece | What it does | Why it is not enough |
|---|---|---|
| The departure | The drift check (every 30 minutes) and the heal's read find a device departing from its golden (`modules/drift_check.py`); the Intent row and the device Overview's "Intent against what it runs" compare committed intent with the committed golden (`nsot/intent_match.py`); Save All refuses a baseline on a difference | It is shown, but the only ends offered are a deploy (merge-only) or a person's hand edit of intent |
| Deploy and restore | `pipeline.py` and `nsot/restore.py`: preview the exact program, confirm by hash, apply, verify, roll back, record | **Merge-only** (`nsot/deploy.py`: "`configure replace` is a documented future option, not built"): lines on the device and absent from intent stay. r8's plan (2026-11-27) would send `line vty 0 4` and its three settings and remove none of 27 lines |
| Removal (Mode B) | A person ticks each line with a reason; only a shape measured to remove exactly itself is sent (`nsot/removal.py`) | Line by line, and refused for every shape not measured: r8's `mgcp`, `mop`, `license` and `spanning-tree` lines all read "no measured shape covers this line". Its vty words claim a merge that does not happen (C4305) |
| Reload | Boots the startup the device holds, gated (`nsot/reload_op.py`, P.14: running must equal startup, startup carries every account, the image exists, the SSH host key survives, the blast radius named) | Boots only what is saved. Its docstring names "revert by reload (booting a moment from history, the charter's Phase 2) … with a boot file" as not built |
| Seed intent | A device's first full intent parsed from its committed golden, previewed as a diff against intent, confirmed by hash, one commit (`nsot/seed.py`, C148) | Offered only when intent is absent or bootstrap-only (`seed.intent_state`), so a device with full intent cannot be re-seeded: Lab 9 rewrote r6's and r7's intent by hand (`lab/lab9/reseed_prepare.py`), and r8's was drafted by hand on 2026-11-27. It parses a saved configuration, which never prints `no shutdown`, so a re-seed would drop each `no_shutdown: true` |
| The comparison's noise | `normalize.strip_for_repo` drops what a stored configuration never holds (the NVRAM comment, `ntp clock-period`); `deploy.classify_diff` knows defaults a device holds (`held_defaults`); P2's rules (`nsot/differs.py`) explain some differences without clearing them | No per-platform table of lines the device prints by default, so an image's defaults read as a departure on every first boot (C1538: r6 and r7, 71 lines; C4300: r8, 27 lines) |

## What is missing

1. **The prerequisite: known printed defaults, per platform.** A table in `modules/nsot/platform.py`
   (the one platform table, C4275), per platform the exact lines its image prints by default when
   nothing sets them, measured on a real device, each with where it was read: for `cisco_iosxe`
   (C8000v 17.6) `no mop enabled` and `no mop sysid` under an interface, the five `mgcp behavior …`
   and `mgcp profile default` lines, `license boot level network-premier addon dna-premier`,
   `spanning-tree extend system-id`. Every comparison (the Intent row, Save All's baseline, the
   drift check, the heal's departure) leaves out a table line present on the device and absent
   from intent, and only that: a changed line (`mop enabled`) is not in the table and still
   differs, and a line intent declares is compared as today. The table is code, not a setting
   (no new setting: a measured fact). Not in it: the device-owned `license udi` serial (already
   left out by Seed), and the terminal lines' grouping (`line vty 0`, `1` with `length 0`,
   `2 4`), which is a real setting (`length 0`), not a default: Restore removes it (a replace),
   Keep records it.

   **Measured 2026-11-28** (read masked through `scripts/nmas-config-read` from the Default
   network's goldens of r6, r7 and r8, the three C8000v, after each one's first boot from a
   startup file; identical on all three):

   | Section | Line, exactly | Depth |
   |---|---|---|
   | (global) | `license boot level network-premier addon dna-premier` | 0 |
   | (global) | `spanning-tree extend system-id` | 0 |
   | (global) | `mgcp behavior rsip-range tgcp-only` | 0 |
   | (global) | `mgcp behavior comedia-role none` | 0 |
   | (global) | `mgcp behavior comedia-check-media-src disable` | 0 |
   | (global) | `mgcp behavior comedia-sdp-force disable` | 0 |
   | (global) | `mgcp profile default` (no children) | 0 |
   | `interface GigabitEthernet<n>` | `no mop enabled` | 1 |
   | `interface GigabitEthernet<n>` | `no mop sysid` | 1 |

   `license boot level …` names the image's licence level, which a person may change: it joins
   the table only as the line this image prints when nothing sets it, so another level differs.

   **Where it applies (read 2026-11-28 for the build):** not in `platform_defaults.HIDDEN`.
   That table is the opposite direction (a target line the device holds without printing), and
   `deploy.classify_diff` treats a HIDDEN target line as satisfied and never sends it, so a
   printed default added there would keep intent's `no mop enabled` from ever reaching a device
   printing `mop enabled`: a deploy that never converges. The printed defaults are left out of
   the device's side only, where a comparison reads it and intent lacks the line:
   `roundtrip.canonical_lines` (through `change_rows` and `canonical_diff`), `roundtrip.compare`'s
   running side (Intent-Match, so the Intent row and Save All's baseline), and the drift check's
   residue; never in the program the deploy builds or in verify's read-back.

   **Built 2026-11-28, its first slice:** `platform_defaults.PRINTED` (the nine lines) and
   `roundtrip.compare`'s running side. That is Intent-Match, so it covers the device page's
   Intent row, Save All's baseline refusal, Reload's gate, the deploy and revert previews' words
   and the heal's departure (`heal/decide.py` asks `intent_match`). The drift check needs nothing:
   it compares a device with its golden, which holds what it prints. Left: the Intent editor's
   "how the device departs" rows (`intent_edit.diffs`'s `departs`, through `change_rows`), which
   still list them.
2. **Restore intent: a true replace.** Where the platform has `configure replace` (IOS-XE; IOS
   15.x with an archive), the rendered intent is sent as a file to the device's own flash and
   replaced onto running: preview (the exact file, masked, and the diff it will make, both
   directions), confirm by hash, apply holding the device, verify by the same comparison (at
   intent, with the defaults table), roll back by replacing the pre-change running (read and
   kept before the replace), record. Where it has none, the startup-plus-reload revert: the file
   written to startup, then the Reload operation with its gates (its first gate changes for this
   operation alone: running differs from startup on purpose, and the preview says so), the
   planned-restart window declared first. Unknowns, each a measurement on a real device before
   building (a device-facing feature starts from what a real device does): the file transfer (SCP into flash, or
   Mercury's TFTP), `configure replace`'s behaviour on vIOS-L2, and whether a replace keeps the
   SSH host key and the management path (it is a change to the path the tool reaches the device
   on, so it needs the independent repair route that rule names, or the reload revert's own).
3. **Keep device: intent from the running configuration.** Seed's parse, offered for a device
   with full intent: the capture parsed through the platform parser and merged into committed
   intent section by section, keeping what a saved configuration cannot show (`no_shutdown`,
   secret refs, keys the parser does not model), previewed by the Intent editor's own two diffs
   (what the edit changes; what a deploy would send, which must be empty), confirmed by hash, one
   commit as the person, `Source: keep`. It replaces the hand edits of Lab 9 and of r8.
4. **The screen.** On the device's Overview ("Intent against what it runs") and on a departure's
   incident card: the diff (masked, one level down, both directions, the defaults table's lines
   named as left out), then the two actions side by side, "Restore intent" and "Keep device",
   each opening its preview; a board drawn first (CLAUDE.md, "No new screen or tab without a
   mockup"), and the manual's pages for both operations. A device whose difference is only table
   lines reads "at intent" and offers neither.

## Order

The defaults table and its use in the comparison first (it alone ends C1538's and C4300's kind of
departure, and Restore cannot show "at intent" without it); then Keep (Seed's parse exists; the
merge and its tests are the work); then Restore, after its measurements. Each operation gets the
independent review that device-writing code gets before its deploy.
