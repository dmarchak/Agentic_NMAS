# Revert by reload: boot a device from a moment in its history (design)

The charter's roadmap, Phase 2 (the operator, 2026-10-07): the simple revert, a standard action
([MERCURY_CHARTER](MERCURY_CHARTER.md), "AI-assisted actions"). Status: **the design and its
mockup (canvas v76, page "Phase 2: Revert by reload", boards A to C) APPROVED in shape by the
operator, 2026-10-07, with the decisions in section 12 (board A redrawn for D2 in v77);
next, the measurements in section 9,
then the build.** Nothing here is built.
Register: C562 (SCP, the later secure transfer), C325 (a restore at HEAD cannot undo a hand change; this does), C531 (revert as one
action by measured removal: parked, the later no-reload option), C334 and C484 (what the
chooser offers), C396 (the write path carries its list). It builds P.14 (Reload, a gated
device-page operation, decided 2026-10-02 and not built) along the way: a plain Reload is this
operation with the running configuration as the boot file.

## 1. The shape, in one paragraph

A person chooses a moment from the device's history: its golden at a time, or a baseline.
Mercury builds the **boot file**: that moment's configuration with the device's CURRENT
credential lines, and `no shutdown` on every interface the moment has up. It previews the
difference between what the device runs now and what will boot, with a warning on every line
touching the path Mercury reaches the device on, and states the outage and the traffic it
interrupts. On a confirm bound to the file's hash, Mercury declares a planned-restart window,
keeps what the device runs now on its own flash, copies the boot file to startup-config, reads
startup back and compares it, reloads, waits for the device within a measured bound, and
verifies: it answers, what it runs is what was sent, its adjacencies return. Then it records a
new golden, sets intent back to the moment's (as Restore does), and writes a receipt. If the
device does not return, the result names the break-glass record, the console, and the file it
kept on flash.

## 2. Why a reload, and what it replaces

Merge-only cannot remove a line (Restore re-applies, it never removes), and removal by
measured shape (Mode B) covers only the shapes measured so far (C531's part 1). A reload from
a whole file takes the device to exactly that file, whatever lines it holds today: the hand
change C325 records is gone, as are lines with no measured removal shape. Its cost is the
outage, stated before the confirm. The no-reload revert (removal shapes, `configure replace`)
is parked as FUTURE (C531, C561) and returns in Stage 8 as an agent's proposal a person
confirms.

## 3. The boot file

A golden is a captured RUNNING configuration, and a running configuration is not a startup
configuration ([STARTUP_FROM_GOLDEN](STARTUP_FROM_GOLDEN.md), section 0). The boot file is
built by one product module, `modules/nsot/boot_file.py`, from three inputs:

1. **The moment's configuration**, read at its ref (`repo.RefSource(...).golden(host)`).
2. **The device's current credential lines**, from the running configuration read at the
   preview: every `username`, `enable` and `snmp-server community` block is the device's
   own, never the moment's ("never an old password", Restore's rule). The swap is
   `startup_source.compose`, which already does exactly this for the lab's startup files,
   given the running configuration in place of the current golden. A credential the moment
   holds and the device does not is not added: the preview lists it, as Restore does for a
   re-added secret, and a person may add it back only with a stated reason. **The running
   configuration's credential lines are compared with the credential Mercury holds for the
   device** (the operator, D2): if they differ, the credential was changed outside Mercury,
   and the preview refuses, saying so with both sides named (masked), before anything else
   is computed. Booting a credential Mercury does not hold would lock Mercury out. How each
   is compared, with nothing new to hold:
   - **The account Mercury signs in with, and `enable`:** the preview's own read signed in
     and entered enable with the credential Mercury holds, against the RUNNING
     configuration, and the line it matched is the line the boot file carries. Established
     only when the device authenticates that login locally; when `aaa authentication login`
     puts a server group first, the sign-in proves the server's answer, not the line, and
     the check reads "not established", which refuses.
   - **The SNMP community:** plaintext in the running configuration, compared with the one
     Mercury holds for the device.
   - **Any other account** (a break-glass account): compared with the break-glass record's
     currency (`breakglass_page.record`); an account Mercury holds nothing for is shown as
     "kept as the device has it, not compared", which is distinct from a difference.
3. **`no shutdown` on every interface the moment has up.** A running configuration records
   `shutdown` on a down interface and nothing on an up one, so a golden booted as-is brings
   every interface up in it back admin-down, the management interface included (it cost a
   full lab rebuild on 2026-08-30). The lab's sanitiser does the same, in shell, in lab tooling;
   the product cannot depend on it, so `boot_file.py` owns it, and Phase 3's rewritten lab
   sync uses `boot_file.py` instead of the shell.

Excluded, as every restore: nothing. A reload from a file is the whole file, so the
self-signed certificate lines, the licence UDI and the banners boot as the moment held them.
Measurement M3 (section 9) checks what the platforms do with them.

The file's hash (sha256 of its exact bytes) is what the person confirms. The preview shows it
masked; the confirm is bound to that hash, the moment, and the hash of the running
configuration read at the preview.

## 4. The preview

- **Choose the moment.** The device's goldens and the baselines that hold it, newest first,
  each with its credential state (`restore_points_for`, today's Restore chooser). Withdrawn
  baselines are not offered. A moment with no golden for this device is greyed with its
  reason (C484's rule). Its intent need not render: the boot file is the moment's golden, not
  a render, so a moment from before the device's intent was seeded is offered too, and section
  6 says what happens to intent then.
- **What will boot against what runs now**, by section (`roundtrip.configs_equivalent`): the
  lines that go, the lines that come, the lines that change. Masked on the way out.
- **The management path, first and in its own colour.** Every difference in: the interface
  carrying the address Mercury uses (`removal._management_interfaces`), the vty and console
  lines, `ip route` and `ip default-gateway`, `ip ssh`, `aaa`, `ip domain-name`, `crypto key`
  (`removal.MANAGEMENT_GLOBAL`), and the management families verify already knows
  (`verify_scope.MANAGEMENT`: logging, snmp, ntp). Each is named with what it means after the
  reload ("the route Mercury reaches r2 by goes"). A difference here is not refused; it needs
  a stated reason, in the hash and the receipt, like a dangerous line.
- **The outage, stated plainly.** "r2 restarts. It is unreachable for about N minutes" (N from
  measurement M2, per platform). "It carries traffic now: 3 OSPF adjacencies, 1 BGP session,
  6 interfaces up, all of which drop for the reload." The counts come from the read the
  preview already makes. Draining first is the drain runbook's (P.22), later; the preview
  names it as not built. **Blast radius** (P.14, gate 6): the devices whose management path
  crosses this one lose reachability too (rebooting s3 cuts off everything behind it), from
  the stored topology; a device with such dependants says so above the confirm.
- **What is lost.** The running configuration's unsaved changes (running against startup,
  P.14's gate 1) are listed: the reload discards them along with everything else the moment
  lacks. Nothing is lost without being shown.
- **Checks, by name:** a golden at this moment; the device's credential lines are the ones
  Mercury holds (D2: refused otherwise, "changed outside Mercury"); the boot file is printable
  ASCII; no credential changes; no secret re-added (or each has a reason); the management-path
  differences each have a reason; the boot image exists and the boot variable points at it
  (P.14, gate 4); at the confirm, no other operation holds the device, and the device is
  unchanged since the preview.
- **The confirm button names the work:** "Copy to startup and reload r2 (about 6 minutes
  out)".

## 5. The run (a job, holding the device)

1. **Declare the planned-restart window** (`restarts.record_planned`, before anything is
   sent): the device, the bound from M2, the reason, the person. Refused, nothing else runs.
2. **Read again and compare** with the preview's running hash (C78's rule: a device that
   changed since is not reverted over a diff nobody saw). Skipped as drifted, nothing sent.
3. **Keep what it runs now, on the device:** `copy running-config flash:mercury-before-<ts>.cfg`.
   The console recovery needs no path through the network: `copy flash:mercury-before-<ts>.cfg
   startup-config`, then `reload`. Also kept in the run's pre-change evidence on the host.
4. **Copy the boot file to startup-config** (decision D1: a one-shot transfer), sending,
   reading and deciding on every prompt (C153's rule).
5. **Read startup back and compare it with the boot file.** Different, or unreadable: the
   reload is refused, startup is restored from the flash copy, and the result says what
   differed. Prove a copy where it landed.
6. **Reload** (`device_reload.reload_device`: send, read, decide; a `Save?` prompt is
   answered no, since startup is the boot file).
7. **Wait for the device**, bounded by M2's measurement times 2.5, polling its management
   address and SSH; each attempt's time is drawn on the stepper. The restart reader sees the
   restart inside the declared window.
8. **Verify:** it answers on SSH with the credential Mercury holds; what it runs is the boot
   file (`roundtrip.stored_is_device`, which leaves out the self-signed certificate it
   regenerates); its routing adjacencies return within verify's settle windows and BGP's hold
   time (`pipeline._capture_operational_snapshot`, `_await_neighbour_convergence`). An
   unreadable read neither passes nor fails.
9. **Record:** the running configuration as the device's new golden, source `reload_revert`
   (a new slug); intent set back to the moment's in the same commit (section 6); a receipt
   naming the moment, the file hash, the reasons, who, and the window.

## 6. Intent

The device now runs the moment's configuration, so intent is set back to the moment's, by a
forward commit, in the same record as the golden (Restore's rule; `restore.intent_at`). When
the moment predates the device's intent (onboarding's stub, or nothing), the choice is
Restore's (signed off 2026-10-03, board 9): leave the device as it is, or un-onboard it too.
Decision D3 asks whether reload follows Restore here.

## 7. When it goes wrong

- **The copy or its read-back fails:** nothing reloads; startup is put back from the flash
  copy; red, with what differed.
- **It does not come back within the bound:** red, "r2 has not answered for 15 minutes".
  The ways out, in order: the console (the break-glass record for r2, with its last export,
  `breakglass_page.record`); on the console, the kept file (`copy
  flash:mercury-before-<ts>.cfg startup-config`, `reload`). The window stays open until a
  person closes it with what they found, so the restart does not read as unplanned.
- **It comes back, but what it runs is not the boot file** (a line the platform rejected at
  boot is silently dropped): red, never green over a partial, with the lines that did not
  take. What it runs is recorded as its golden (the record is what the device holds), marked
  not verified; intent is NOT set back, since it would claim the lines that did not take. The
  device is up and reachable, so the ways out are a deploy of those lines, or another revert.
- **It comes back, but its adjacencies do not return:** red, with which ones, after the
  settle windows.
- **There is no automatic rollback.** Rolling back a reload is a second reload, a second
  outage; Mercury never takes one on its own. The result offers it as one action, previewed
  like any other: "Revert by reload to what r2 ran before (mercury-before-<ts>)" (decision D4).

The lifecycle (CLAUDE.md, "Every device-changing operation"): preview, confirm by hash as a
verified person, apply holding the device, verify, **rollback: offered, never automatic, with
its reason declared** in `operation_stages.STAGES`, record.

## 8. Never let a wrong thing look like a working thing

| Wrong, looking right | What makes it visible |
|---|---|
| The device answers after the reload, but booted with lines rejected | Verify compares what it runs with the boot file, line by line; the result is red, naming them |
| The copy reported success, but startup is not the file | Startup is read back and compared before the reload; the reload is refused |
| It booted a different file (a boot variable, `boot config`) | The same comparison: running against the boot file |
| An interface comes back admin-down | `no shutdown` is in the file (section 3); verify's interface comparison names any interface down that the moment has up |
| The restart reads as unplanned on Needs attention | The window is declared before step 1 sends anything, and kept open while the device is away |
| An old password boots | The credential lines are the device's current ones; "no credential changes" is a check, and the receipt says so |

## 9. To measure first (the operator's runs on r2 and s1, at a quiet time; never s3)

There is no throwaway now (the operator, 2026-10-07), so the runs are on r2 (IOS-XE) and s1
(IOS), outside the backup window, with their short outages accepted: s1 cuts h1 and h2 while
it boots, and r2 makes RIP reconverge. In order, the two with no reload first:

- **M1, the transfer path (no reload, nothing written on the device):** the device asks the
  host's existing TFTP responder (the ZTP one, bound to the lab-facing interface) for a file
  it will refuse. The device's error proves the round trip; the responder's audit row records
  the requesting address. It answers whether the device reaches the host on UDP 69, and
  whether TFTP leaves from the address Mercury knows the device by: the devices source
  logging and traps from `Loopback0` and carry no `ip tftp source-interface`, so TFTP leaves
  from the egress interface. If the recorded address is not the device's management address,
  the boot file and intent need `ip tftp source-interface Loopback0` (a line, delivered
  through intent before the first revert), or the transfer accepts any address the device's
  golden holds; decided on the result.
- **M4, the prompts (no reload, startup untouched):** `copy tftp://… startup-config` asked of
  the same refusing responder (it fails on opening the source, before startup is written; the
  NVRAM timestamp is read before and after to prove it), `copy running-config flash:…`,
  `verify /md5` on a flash file and on `nvram:startup-config` (the read-back), `delete`, and
  the boot image (`show boot`, `show version`). Each prompt's exact text, so the run sends,
  reads and decides.
- **M3, a golden booted as startup (one reload each):** a boot file built by
  `boot_file.py` from the device's current golden (built and tested before this run, with the
  one-shot transfer M1 decides), copied to startup, read back by `verify /md5`, then a reload
  under a declared window. The comparison is the freshness reader's on the next copy of the
  running configuration (the golden against what it runs: `match` is M3 passing), and the
  device's interfaces. It proves `no shutdown`, and shows what each platform does with the
  self-signed certificate, the RSA key, the licence and the banners. A difference becomes a
  rule in `boot_file.py` before the build. The break-glass record is ready before it runs.
- **M2, how long a reload takes:** M3's reload is the first run; two plain reloads follow,
  each under its own window. From the reload to SSH answering, and to adjacencies settled,
  timed by the syslog's receive times (never the device's clock). The wait's bound is 2.5
  times the longest, written beside it.

## 10. Decisions for the operator (as put, 2026-10-07; decided in section 12)

- **D1, the transfer.** No device has `ip scp server enable` or an `archive` stanza (the nine
  goldens, read masked through `nmas-config-read`, 2026-10-07 19:50 UTC), so pushing over SCP
  would first need a device change. The host's only TFTP server is ZTP's, read-only and
  serving ZTP-reserved devices only. Options:
  - **(a) Recommended: a one-shot TFTP pull.** The ZTP responder's pattern (socket-activated,
    read-only): Mercury writes the one file under a random name, serves it only to this
    device's management address and only for the run's window, then deletes it. TFTP is
    plaintext on the management network, which already carries SNMP in plaintext; the file
    holds hashes, not passwords, except for any type-7 or plaintext line the moment holds.
  - (b) An HTTP pull from Mercury. Mercury sits behind the access proxy, and an
    unauthenticated route for devices would be a new kind of exemption. Not recommended.
  - (c) SCP push. Needs `ip scp server enable` and exec authorisation on every device first:
    a device change before the revert.
- **D2, where the current credential lines come from:** the running configuration read at
  the preview (recommended: it is what the device holds now), or today's golden.
- **D3, intent:** set back to the moment's, as Restore does (recommended), or left as it is
  and the device shown departing from intent.
- **D4, rollback:** offered as one action ("revert by reload to what it ran before"), never
  automatic (recommended), or automatic on a verify failure (a second outage nobody
  confirmed).
- **D5, the management path:** a difference there needs a stated reason (recommended), or is
  refused outright until a repair route exists (the rule "a change to the path the tool
  reaches a device on needs a repair route independent of that path": here the console and
  the kept file are that route).
- **D6, scope:** one device at a time in Phase 2 (recommended); several devices, in order,
  with the breaker, after the drain runbook can take traffic off first.

## 11. Screens (drawn in the mockup for sign-off)

- **A.** The Actions menu's new row, "Revert by reload…", and the card: choose the moment,
  then the preview (what will boot against what runs now, the management path first, the
  outage and the traffic, the credentials, the checks, the confirm naming the work).
- **B.** The run as a job on the one stepper: window declared, kept on flash, copied, read
  back, reloading, waiting (with each attempt's time), verifying; then the result, verified.
- **C.** The ways it ends red: it did not come back (the console, the break-glass record, the
  kept file, and closing the held-open window with what was found); it came back but did not
  take every line (the lines named, the ways out); the copy did not land (no reload, startup
  put back); and the offered "revert by reload to what it ran before".

Timings in the boards are placeholders named `[M2]` until M2 is measured.

The manual gets a How it works page, `revert-reload`, naming each step the code declares,
with its diagram, and the Actions menu's "How does this work?" opens it.

## 12. Decisions (the operator, 2026-10-07: the design and mockup v76 approved in shape)

- **D1:** the one-shot TFTP pull (served once, to that device's address only, for the run),
  for now. SCP, with `ip scp server enable` delivered through intent, is recorded as the
  later secure option (C562).
- **D2:** credentials from the running configuration read at the preview, AND compared with
  the credential Mercury holds; a difference (changed outside Mercury) refuses, saying so
  (section 3 says how each is compared). Board A's credentials row draws this check.
- **D3:** intent set back to the moment's.
- **D4:** rollback offered as one previewed action, never automatic.
- **D5:** each management-path difference needs a stated reason.
- **D6:** one device at a time.
- **The measurements** run on r2 and s1 at a quiet time (no throwaway now), M1 and M4 first,
  then M3 and M2 (section 9); M1 says whether a TFTP source-interface is needed. The operator
  has the break-glass record ready before M3.
