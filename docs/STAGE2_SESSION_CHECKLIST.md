# Redeploy checklist — rcn-lab1

**First run: 2026-09-22, the Stage 2 session that lifted the redeploy ban.
Every item passed.** This is not a record of that run — it is **the
verification for any future redeploy**, and it is meant to be re-run.

A checklist that is run once is a record. One that is re-run is a test.

> **Revision of 2026-10-16 (C948), between runs, on the operator's decision of that morning:**
> "rewrite the Stage 2 checklist's post-items as Mercury reads, as a dated new revision (its
> 'do not edit' means not edited to match a result; naming the retired Oxidized fails that
> already). Keep its section structure."
>
> What changed, and why: the checklist had fallen behind the rules it is run under. Its
> post-items read devices through terminal steps (a shell `nmas-check-credential`, a console
> `docker exec … telnet`), compared uptimes against a clock (a device's uptime never dates an
> event), and named Oxidized, retired 2026-10-08. Followed after C906, it would also have left
> eight unplanned-restart rows and eight refused-key rows, because it declared no planned
> window. Now:
> - every pre-item and post-item that reads a device is a Mercury read or a Mercury screen, each
>   named by its place, with what the screen will say when the item passes (1.3 to 1.5, 4.1 to
>   4.11, and the new 4.12 for the SSH host keys);
> - 3.2 declares the planned window before the redeploy, with the same command as
>   `lab/REDEPLOY.md` step 1, and runs the one redeploy command (`containerlab deploy …
>   --reconfigure`, without sudo, confirmed by the operator 2026-10-16); the device lists are
>   the eight Mercury manages, r1 to r4 and s1 to s4 (r5 is still in the topology and is rebuilt
>   with it, but Mercury retired it; r6 is a separate lab);
> - section 2 is withdrawn: its script and setting left the product with C663 step 2
>   (2026-10-11);
> - the two items no Mercury read covers (the launch script's own line in 4.4, the switches'
>   console replay in 4.6) say so, and are read on the lab host, never on a device.
>
> The numbering and the headings are the first run's. The 2026-09-22 result stands as it was
> recorded.

**Written for: the operator, at the machine** (a browser on Mercury, and a shell on the lab
host for section 3). Self-contained: everything you need is in this file. Nothing here is for
an agent to run.

**This file is not edited to match a result.** If an item fails, the redeploy is not called
good, and the failure is measured. A checklist edited afterwards to agree with what happened
is a description, not a test. It changes only between runs, as a dated revision that says what
changed and why.

---

## Before you start

| | expected |
|---|---|
| NMAS deployed at | `8328e69` or later, and carrying C906 (`lab/REDEPLOY.md` step 0) |
| Mercury holds every device's SSH host key | `lab/REDEPLOY.md` step 0 done: History (`/v2/history?kind=hostkeys`) shows "SSH host key kept on first contact" for each of r1 to r4 and s1 to s4 |
| `config_repo` | clean, and pushed (1.3) |
| rcn-lab1 | 14 containers healthy, ~3 days uptime |
| 2.1 launch patch | **done** — adopted, `smp="2"` + skip, backup kept |
| 2.2b break-glass | **done** — exported, verified on the NMAS **and on the laptop**, NMAS copy deleted, passphrase in the password manager |
| The time | not within 75 minutes before the nightly backup window (08:30 to 09:10 UTC), and not inside it: the planned window is 60 minutes, and Mercury accepts a restart or a new key up to 15 minutes after it |

**Item 0 is withdrawn** — its premise was false (see below). **Stage D is
not part of this session either.** It tests `crypto key generate
rsa` in the *generator's* output for r6. No harvested config contains that
line — `show running-config` never emits it — so the redeploy does not involve
it. Stage D is a **Stage 4** prerequisite.

---

## 0. D3 — WITHDRAWN before the session. The premise was false.

Kept rather than deleted, because how the premise was arrived at matters more
than the item did.

**The claim was:** nothing in s1–s4's startup files creates an RSA key, so a
redeploy would return four switches with no SSH server.

**The measurement:** all four startup files contain
`crypto key generate rsa modulus 2048` — s1 at line 187, one occurrence each.
s1's key is timestamped 05:27:23 on 2026-09-19, four minutes after the 05:23
deploy. **It was generated at boot, by the file.** Nothing depends on NVRAM
surviving.

**How it went wrong:** the claim was reasoned from the *probe* configs —
stage A's and D2's, which legitimately lack the line because they are minimal
bootstraps — rather than read from `~/labs/lab/configs/s*.cfg`, the artifact
the redeploy actually uses. Correct reasoning about the wrong object. One
grep of the real file answered it.

That is the same shape as asserting GUI click-paths from the design documents
instead of the templates (Stage 1), and it reached a *more* alarming
conclusion than the truth, which is the direction that wastes a session.

**It also corrects a D2 conclusion:** "SSH needed a hand-typed key" was a
property of the probe's config, not of the platform. A vIOS booting a real
switch startup file gets SSH from the file.

---

## 1. Pre-items

- [ ] **1.1** Patch in place, on the lab host:
      `grep -c '_skip_users_defined_in_startup' ~/labs/lab/patches/c8000v-launch.py` → **2**
      `grep -n 'smp=' ~/labs/lab/patches/c8000v-launch.py` → `smp="2"`
- [ ] **1.2** Startup files still carry the rotated secrets, on the lab host:
      `grep -c 'secret 9' ~/labs/lab/configs/r*.cfg ~/labs/lab/configs/s*.cfg` → **1 each, 9 files**
- [ ] **1.3** Repo clean and published: **History**, the remote's sentence at the top. It
      reads **in sync**, "Everything is committed · and pushed to <the remote>", checked within
      the last few minutes. Anything else (paths not committed, commits not pushed, "could not
      be read") is fixed before going on.
- [ ] **1.4** **Save All now**, so the pre-redeploy goldens are the comparison point:
      **Devices › Actions › Save every device of Default (N)…**, then its confirm. Each device
      saves to startup, is read back and is recorded as golden, in one commit. The result names
      the commit; History holds it.
      Record the commit: `________________`
- [ ] **1.5** Record what Mercury already holds about restarts, to compare against after:
      **History**, Kind **Restarts** (`/v2/history?kind=restarts`), the last 7 days. Note any
      row for r1 to r4 or s1 to s4: `________________`
      And **Needs attention**: no "restarted unexpectedly" row for any of the eight. An earlier
      one is understood and acknowledged first, so that 4.2 reads only this redeploy's rows.
- [ ] **1.6** You have time to finish. Do not start this with 20 minutes. Section 4 runs inside
      the planned window (60 minutes from 3.2), and the boot alone took about 24 of them on
      2026-10-01 (`lab/REDEPLOY.md`, "The bound").

---

## 2. 2.2a — prove the applicability check, including that it can fail

> **WITHDRAWN 2026-10-16 (C948).** The check this section ran,
> `scripts/nmas-check-startup-applies`, and the setting it read, `clab_launch_patch`, were
> removed from the product by C663 step 2 (2026-10-11): containerlab is test infrastructure,
> and Mercury keeps no check of the lab's launch script (that commit's `Refused:` line). No
> Mercury read replaces it. Its commands are taken out, not left to run: 2.4 hid the skip's
> marker in the lab's launch script and relied on the removed script to show it and restore
> it, so following it now would leave the marker hidden before a redeploy, the hazard this
> stage exists to prevent. That the marker is in place is 1.1's read; that the skip worked is
> read after the redeploy, in 4.3 to 4.5 and 4.7.
>
> What it was for is kept, because the reasoning is what stops the next person rebuilding the
> mistake it corrected:

> **Corrected before the session.** This section previously said to run
> `nmas-rotate-credential` on s1 and r1 to watch `startup_applies` pass. That
> performs a **real rotation** — a new random password on a live device —
> minutes before a redeploy whose post-items verify exactly those
> credentials, invalidating 1.4's baseline and 1.5's snapshot taken moments
> earlier.
>
> Worse, the negative control used `nmas-persist-credential --dry-run`, which
> **returns before entering the persist chain** and so never runs this stage
> at all. It prints the same line whether the launch script carries the skip
> or not: a control that could not fail, guarding the one check whose purpose
> is to fail when the skip is absent.

- **2.1** (withdrawn) The setting pointed at the patched file.
- **2.2** (withdrawn) Every device, one command: APPLIES for all eight; the switches because
  nothing is injected on vIOS, the routers because the launch script carries the skip.
- **2.3** (withdrawn) A router's pass named the skip, so it was not vacuous.
- **2.4** (withdrawn) The negative control: with the marker hidden, the routers refused and
  the switches did not. **A check that only ever passes has not been shown to work.**
- **2.5** (withdrawn) The marker restored before going near the redeploy: 1.1's read.

**No rotation happens in this session.** The credentials on the devices at
3.2 are the ones 1.4 recorded, and the ones 4.7 verifies.

---

## 3. The redeploy

- [ ] **3.1** Last look, on the lab host: `docker ps --format '{{.Names}}\t{{.Status}}' | grep clab-rcn`
- [ ] **3.2** First the planned window, **before anything restarts**: on the NMAS host, as the
      user the app runs as (never with sudo), the same command as `lab/REDEPLOY.md` step 1:
      ```bash
      <home>/python/Agentic_NMAS/scripts/nmas-planned-restart Default r1 r2 r3 r4 s1 s2 s3 s4 \
          --minutes 60 --new-host-keys \
          --why "lab redeploy: rcn-lab1 rebuilt from its startup files" --by <operator>
      ```
      It passed when it exits 0 and prints `recorded: r1, r2, r3, r4, s1, s2, s3, s4 in Default
      may restart from <from> until <until> (and up to 15 min after), …` and `expecting new SSH
      host keys: …`. Anything else is `refused: <why>`, exit 1: stop, and do not redeploy. The
      window names the eight, never `*`, which would also cover r6.

      Then at once, on the lab host, the one redeploy command:
      ```bash
      cd ~/labs/lab
      containerlab deploy -t rcn-lab1.clab.yml --reconfigure
      ```
      `--reconfigure` regenerates the lab's artifacts, so every node boots from its startup
      file, as `destroy --cleanup` then `deploy` did, in one command. No `sudo`: the lab
      host's user is in `clab_admins` (if it refuses on permissions, the same command with
      `sudo` is the fallback; say so in the result). Never `docker restart` or `docker start` a
      node (C478).
- [ ] **3.3** Start time recorded: `________________`
      The window's `<until>`, from 3.2's output: `________________`

---

## 4. Post-items — all of them, in order

Every item reads Mercury. Start once the **Devices** page shows all eight **Answering** (expect
about 24 minutes after 3.3). **4.1's read must be made inside the window**, by `<until>` plus 15
minutes: it is each device's first session after the rebuild, and Mercury keeps a device's new
SSH host key only inside a window declared before it. Every read below is recorded in History
as yours, so the result stays readable after the session.

- [ ] **4.1 All eight boot and answer Mercury.** **Show commands**: Devices, Name
      `r1, r2, r3, r4, s1, s2, s3, s4` (the card says **8 devices**); Commands
      `show running-config | include ^username` and, with **Add a command**,
      `show logging | include CVAC`; then **Run on 8 devices**. Items 4.3 to 4.7 read this
      run's answers; reopen it from **Recent runs**.
      → the summary says, for each command, **Answered 8**, **Failed 0**, **Skipped 0**.
      "Answering" on the Devices page is a ping or a TCP connection to port 22, not a sign-in,
      so a run made early may fail on a device still booting: run it again. A device that has not answered this read by the window's end (`<until>`) is a
      **failure**, not slowness: the eight took 23.8 minutes together on 2026-10-01, and the
      window is 2.5 times that.
- [ ] **4.2 Each device restarted once, for this redeploy, and not again.**
      On the D2 probe a vIOS took a CPU exception (PnP Agent Discovery,
      SIGBUS) and **silently reloaded** — container healthy, `docker logs`
      empty, only uptime revealed it. `Startup complete` had been printed by
      the *first* boot, so anything keyed on that line was reading about a
      boot whose result no longer existed.
      Mercury finds a restart where the device's uptime counter fell (SNMP, read each minute),
      never by subtracting an uptime from the clock.
      **History**, Kind **Restarts** (`/v2/history?kind=restarts`):
      → for each of r1 to r4 and s1 to s4, exactly **one** row after 3.3 beyond those 1.5 noted,
      **"Restarted as planned"**, its detail ending "planned: lab redeploy: rcn-lab1 rebuilt
      from its startup files". **Needs attention**: no "restarted unexpectedly" row for any of
      the eight. Read History again after 4.11: still one each. **A second row for any device,
      planned or not, is the failure this item exists for.**
- [ ] **4.3 No `%CVAC-4-CLI_FAILURE` for a username line**, any router: 4.1's run, the answers
      to `show logging | include CVAC`.
      → each router's answer holds its `%CVAC-4-CONFIG_DONE` line (CVAC's own line for the
      day-0 configuration it applied: `docs/P6_ZTP_PROBE.md`) and **no** `%CVAC-4-CLI_FAILURE`;
      each switch's says "No output (empty answer)" (vIOS runs no CVAC).
      **The CONFIG_DONE line is the control:** an answer without it shows the device's log
      buffer no longer holds the boot, so the missing failure line proves nothing, and the item
      is not passed. Then the boot's record is the lab's own, on the lab host:
      `docker logs clab-rcn-lab1-<router> 2>&1 | grep CVAC` → no `CLI_FAILURE`.
      (Whether the buffer holds CONFIG_DONE after a full boot was not measured before this
      revision: the first run under it measures it.)
- [ ] **4.4 The skip fired** on each router.
      **No Mercury read sees this line**: it is the lab's launch script's own, printed to the
      container's log on the lab host, which Mercury does not read (C663 took the lab out of
      Mercury). It is read there, on the lab host:
      `for n in r1 r2 r3 r4; do echo -n "$n "; docker logs clab-rcn-lab1-$n 2>&1 | grep -ci "not injecting"; done`
      → 1 each.
      What the skip prevents is read in Mercury, in 4.1's run: no CVAC failure (4.3), and no
      account in the `password` form (4.5).
- [ ] **4.5 Each router's running config shows `secret 9`**, not `password 0`: 4.1's run,
      the answers to `show running-config | include ^username`, r1 to r4.
      → every line reads `username <account> … secret 9 <redacted:…>` (Mercury masks the value
      and keeps its form); **no** line in the `password` form, which is the form vrnetlab's
      injected `admin` account takes. The routers whose accounts are the same form one group.
- [ ] **4.6 Each switch's too**, s1 to s4, in the same answers, with the same expectation.
      Nothing is injected on vIOS, so a failure here means the **hash form or the console
      replay**, not coexistence — stage C's fix would not apply. Check the boot log as well as
      the config: the console's replay is kept only in the container's log on the lab host
      (`docker logs clab-rcn-lab1-<switch>`), and no Mercury read sees it.
- [ ] **4.7 THE ITEM THE STAGE EXISTS FOR.** Each device answers with the
      credential NMAS holds, and the old `admin`/`admin` is refused on the
      routers.

      **Do not use `ssh`/`sshpass`.** On the D2 probe that check passed because
      the connection died at *key exchange* — it would pass with the device
      powered off, and here it would pass while every router sat on
      `admin/admin` and unreachable.

      **The credential Mercury holds:** 4.1's run signed in to each device with the credential
      its inventory holds, the way every Mercury operation does; the device page's header names
      the account ("signs in as <account>").
      → **Answered 8**, **Failed 0**. A failed device names why: a refused login is the wrong
      verdict, and a timeout or a closed connection establishes nothing either way, which is
      **not** a pass.

      **`admin`/`admin` refused:** Mercury has no read that signs in with a credential it does
      not hold, so this half is read from the configuration instead: 4.5's answers hold no
      account in the `password` form, so vrnetlab's injected `admin`/`admin` line is not on any
      router. That shows the injected line absent; it does not try the login.
- [ ] **4.8 Mercury reads every device's running configuration, after 3.3.** (This was
      "Oxidized fetches all nine"; Oxidized is retired, and the drift check reads every device
      of the network.) **Settings › Installation › Diagnostics › Drift checks**, the
      **Default** row's **Check now**, inside the window, as `lab/REDEPLOY.md` step 3 says.
      → the card redraws when the run is recorded: **Last** is after 3.3; hover it for the
      run's summary, which ends "(checked M of M.)", M the number of devices on the Devices
      page for Default (nine on 2026-10-16: r1 to r4, r6, s1 to s4), and names no device
      "Unreachable" or "Not checked".
- [ ] **4.9 A Save All produces no unexpected diff** against 1.4's commit.
      Uptime and counters aside, a difference means a node did not come back
      as itself. **Devices › Actions › Save every device of Default (N)…**, then its confirm.
      → each device reads "saved; its golden already matched". A golden that changed is read in
      **History**, the commit's **Show the change** (masked): a regenerated self-signed
      certificate is named as such and is not a node coming back as something else; any other
      line is.
- [ ] **4.10 Drift check runs clean**: 4.8's run.
      → its summary reads "All M checked device(s) clean — no config drift detected.
      (checked M of M.)" (a regenerated self-signed certificate is named after it, "not
      drift"); **Needs attention** has no drift row for any device of Default; each device's
      page, **Overview**, reads **Drift** "clean at the last run".
- [ ] **4.11 The remote** shows the post-redeploy Save All pushed: **History**, the remote's
      sentence at the top.
      → **in sync**, "Everything is committed · and pushed to <the remote>", checked after
      4.9's commit, which the History timeline lists, today, as yours.
- [ ] **4.12 The new SSH host keys** (new in this revision: a rebuilt node has a new key, and
      Mercury refuses a changed key unless a window declared before it says to expect one).
      While the window is open: **History**, Kind **SSH host keys**
      (`/v2/history?kind=hostkeys`)
      → one row per device, "SSH host key kept under a planned window", reading
      `SHA256:<new> (ssh-rsa), replacing SHA256:<old>, during 'lab redeploy: rcn-lab1 rebuilt
      from its startup files'`; and **Needs attention** has no "answered with a different SSH
      host key" row (one means a device was met with a new key outside the window: the row's
      action opens Re-key on the device's page, where the new key is reviewed).
      After the window closes (`<until>` plus 15 minutes; the reader runs each minute):
      → **Needs attention** shows ONE row, **"8 new host keys accepted during 'lab redeploy:
      rcn-lab1 rebuilt from its startup files'"**. Review the keys in History, then
      **Acknowledge…** with what you found. The row goes; the keys and the summary stay in
      History.

---

## If any item fails

**Stop. Measure before changing anything,** through Mercury: the device's own log
(**Show commands**, or the device page's **Ask the device**: `show logging | include <what>`),
its running config (4.1's read),
which credential it answers on (4.7), and its restarts (**History**, Kind **Restarts**). Each
read is recorded with its answer.

A device Mercury cannot sign in to is itself the measurement: record what the read's failure
said, and stop. Reaching it another way is a repair, outside this checklist, and the
operator's; the break-glass record on the laptop holds its credentials.

**Do not redeploy again to "try it clean".** A second redeploy destroys the
evidence of why the first failed.

---

## Only when every item passes

On the first run (2026-09-22) this updated the three ban notices — `CLAUDE.md`,
`docs/bootstrap-probe/README.md`, `docs/NSOT_PHASE4_ONBOARDING.md` — to
**"lifted on <date>, and here is what proved it"**, with the checklist result. That is done.
On a later run, the result is the records above: 4.1's Show commands run, the restarts, the
drift run, the Save All's commit and the host keys, each in History.

Not deleted. The reasoning is what stops the next person recreating the
hazard.
