# Lessons from W2 for W3's script

**This is not W3's script.** W3 (onboarding and recovery: docs/PHASE7_BURNDOWN.md section 1b)
is written later, after the fixes it must walk have landed and been deployed, from the code and
a read-only look at the host the day it is written. These notes are the rules that writing
follows. They come from the operator's W2 report of 2026-10-17 (its part 5, the walk-script
fixes), each already applied to [W2.md](W2.md), and from this folder's [README](README.md).

## The conventions every walk script keeps (from the README)

- **Each step names a page and an action, then gives its PASS.** The page is a v2 address,
  relative to the host; the action is the exact control or the exact text to type; the PASS is
  quoted from the templates or the code that draws it.
- **No terminal steps.** No step uses a device console, a host shell or one of today's (v1)
  pages. Every read of a device goes through Mercury (Show commands, Ask, a device tab).
- **A change names its target and its undo.** Never s3, never the management path. A step that
  changes a device says what to do if its PASS does not appear, a later step puts it back, and
  the last section checks every device is as it started.
- **A screen built from a board names the board** (canvas, file, and two to four things to
  compare), so its fidelity record (C650) comes out of the same sitting.
- **"Before you start" states the host as read**, the release, the time (clear of 08:30 to 09:10
  UTC), the times to write down and the screenshots to keep, by step.
- **Publication:** placeholders for anything installation-specific (`<you>`, `<home>`,
  `<account>`, `<repo>`), and no personal data.

## A filter that must match nothing uses a status guaranteed empty

W2's step 36 filtered a throwaway network's NetBox inventory on `decommissioning`, and it matched
r5, which sits in NetBox at that status on purpose (retired). A filter meant to read no device
uses a status no device holds (W2's sitting used `planned`, which held 0), and the step makes the
preview's count the check: read "NetBox holds 0 devices" before saving, and cancel otherwise.
Name the status's emptiness as measured on the day the script is written.

## Name the top bar's picker, never just "the picker"

The top bar's **Network ▾** (reading "Network <name> ▾") and the Settings page's scope bar
("Choose a network") look alike. A step that means the top bar says "the top bar's Network ▾";
a step that means the scope bar says "the Settings scope bar's Choose a network". Never
"Network" alone.

## Prove an ordering with an item that is not already first

W2's step 27 pinned a saved view that was already listed first, so the pin moved nothing and
proved nothing. A step that proves something reorders a list acts on an item that is not first
(or not where the change puts it), says the order before, and says the order to expect after.

## A device's telemetry is read through Show commands, with a command that exists

W2's step 58 had no telemetry check, and the walker's command, `show telemetry connection all`,
does not exist on the lab's IOS-XE release. A telemetry read is a step on Show commands
(`/v2/show-commands`), one device, with `show telemetry ietf subscription all`, which is a read on
Mercury's allowlist (`modules/readonly_commands.py`: its `refusal` returns nothing for it). Its
PASS names each subscription and its state (after r6's boot in W2: 101 and 102, "Configured" and
"Valid"). Before a script names any other command, check that the allowlist passes it and that
the device's release has it; if the allowlist refuses it, the step says so and the gap is
registered as a finding.

## An expected result that is absent today is named with its finding

W2's step 58 expected "Restarted as planned" in r6's History, and it was missing (W2's B4). W2's
step 57 expected "declared until <time>" while the reload ran, and it is drawn only after the run
ends (a known gap, registered as a C finding). A step writes the expected result as the PASS, and
beside it the finding that keeps it absent today and what the walker does meanwhile (note it and
go on, or read it at a later step). When the fix is deployed, the same step walks it.

## A reload expects the host key kept

C941 is measured: a C8000v keeps its SSH host key across a reload. In W2, r6 logged
%CRYPTO_ENGINE-5-KEY_ADDITION for its key at 00:15:25 UTC on 2026-10-17 while booting, and
`show ip ssh` read through Mercury at 00:17:58 UTC gave the same fingerprint as before. A W3 step
that reloads or restarts a C8000v expects its key row in History unchanged and the run verified
with no re-key; a changed key is a finding, handled through the "Re-key <device>" card as W2's
section M describes. A device of another kind (vIOS, or one onboarded fresh) is not covered by
this measurement: say so, and measure it.
