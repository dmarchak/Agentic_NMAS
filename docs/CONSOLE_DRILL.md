# The console drill: proving the emergency path before the terminal goes (R39)

**Why:** the operator decided (2026-10-04) to remove the break-glass terminal now (R39, 7.8
brought forward), AFTER this drill proves the emergency path without it:
1. reach one lab device by its console, through containerlab;
2. sign in with a credential from the break-glass record;
3. run one read;
4. leave.

Run by the operator, once. The terminal is removed only after the result is recorded below.

**The device is r2** (IOS-XE, the lab's probe router for IOS-XE). Never s3: it carries the
fleet's management path (C93).

**When:** outside the nightly backup window, 08:30 to 09:00 UTC (02:30 to 03:00 the operator's
time).

**What it changes:** nothing. There is no `enable`, no `configure`, no reload, and no write.
Each step reads.

## What was measured before writing it (read-only, 2026-10-04)

- **The containers:** `clab-rcn-lab1-r2` (`vrnetlab/cisco_c8000v`) and `clab-rcn-lab1-s1`
  (`vrnetlab/cisco_vios`) run on the lab host. Each exposes `5000/tcp`, vrnetlab's serial
  console, inside the container.
- **The lab host's user** is in the `docker` group, so `docker exec` needs no sudo.
- **r2's console asks for no login.**
  - Its golden's `line con 0` holds only `logging synchronous` and `stopbits 1`: there is no
    `login` line.
  - There is no `aaa new-model` and no `enable secret`.
  - s1's golden has no `line con 0` lines at all.
  - **So the console opens a prompt without any credential (C455).** The record's credential is
    asked for where a login is configured: the vty lines (`login local`), over SSH.
  - The drill therefore proves the two halves separately: the console reaches the device
    without the tool (step 2), and the record's credential opens it (step 4).
- **The break-glass record's recovery text** already names the console command
  (`modules/breakglass.py`, `DEFAULT_RECOVERY`).

## Before you start

- The break-glass record file, where it is kept, and its passphrase.
- A terminal on the laptop with the repository, and SSH to the lab host
  (`ssh $(scripts/nmas-host clab --target)`, or its tunnel name).
- The record shows a password on screen at step 1. Clear the terminal's scrollback at the end.

## The drill

**1. Open the record, offline, on the laptop.**

```
python3 scripts/nmas-breakglass drill <record>              # names only; no credential printed
python3 scripts/nmas-breakglass reveal <record> --device r2  # r2's address, username, password
```

Expect `drill` to list r2 among the devices it recovers. Keep `reveal`'s address and username
for step 4. If either command fails, STOP: the record itself is the finding.

**2. Reach r2's console through containerlab, on the lab host.**

```
ssh <user>@<lab-host>
docker exec -it clab-rcn-lab1-r2 telnet localhost 5000
```

Press Enter once or twice. Expect `r2>` or `r2#` **with no login prompt** (measured above).
Note exactly what appeared. If it asks for `Username:`, sign in with the record's credential
from step 1, and note that it asked.

**3. One read, on the console.**

```
show version | include uptime
```

Expect one line, `r2 uptime is ...`. Then leave the console:

```
exit
```

Then the telnet escape, `Ctrl-]`, and `quit` at the `telnet>` prompt. That ends the
`docker exec`, and you are back on the lab host.

**4. Sign in with the record's credential, from the lab host or the NMAS host** (the drill of 2026-10-05 used the NMAS host).

```
ssh <username from step 1>@<r2's address from step 1>
```

Enter the password from step 1. Expect `r2#`. Then:

```
show clock
exit
```

- A refused password means the record is stale: its credential is not the one r2 holds
  (C182's currency check). STOP and report; the terminal stays until the record is current.
- A host-key warning names r2's key, which changes on a redeploy. Accept it only if the
  address is r2's, from step 1.

**5. Leave the lab host, and clear the laptop terminal's scrollback.**

## The result (the operator fills it in)

**PASSED, 2026-10-05, about 02:07 UTC (20:07 the operator's time), run by the operator.**

| | |
|---|---|
| When (UTC, and the operator's time) | 2026-10-05 about 02:07 UTC (20:07) |
| The path to the lab host (LAN or tunnel) | LAN |
| Step 1: the record opened, r2 listed | Yes: `nmas-breakglass-Default-20261003T195437Z.bg` opened offline with its passphrase; r2 listed; `reveal` gave its address and username |
| Step 2: what the console showed; asked for a login? | `docker exec … telnet localhost 5000` reached r2's console with NO login. **`enable` gave `r2#` with NO password either**: the console gives full privilege to anyone who reaches it (C455, and C457: no enable secret anywhere) |
| Step 3: the uptime line's first words | "r2 uptime is 3 days, 9 hours, 1 minute" |
| Step 4: the record's credential accepted over SSH? | Yes: `ssh <username>@<r2's address>` accepted the record's password; `show clock` 02:07:13 UTC. **Run from the NMAS host, not the lab host** (step 4 above now says either) |
| Anything unexpected | The console's missing enable password, above |

**Then:** the break-glass terminal was removed (R39), with docs/CUTOVER.md updated.


---

# C455: the console asks for a login, one device first (the operator, 2026-10-04)

**The order, each step done before the next:**
1. Confirm the break-glass record holds the current credential.
2. Add `login local` on `line con 0` to r2's intent, and deploy it.
3. The operator re-runs the console drill there (variant B below), signing in with the record's
   credential.
4. Only then, the rest of the fleet as one batch, with s3 last.

No enable secret changes in the same step.

## Step 1: the record is current

**Measured by the agent, read-only, via LAN, 2026-10-05 01:20 UTC (19:20 the operator's
time):**
- the record's state is **current**: "Every device's credential in use is in the record
  exported 2026-10-03T19:54:37Z";
- 9 devices, exported through the browser; the download arrived intact;
- job health judged it at 01:16:40 UTC;
- the checkout was unchanged before and after the read.

**The operator's half:** confirm the file you hold is that export.

```
python3 scripts/nmas-breakglass verify <record>
```

It prints the record's date, and must say 2026-10-03 19:54 UTC. An older file is not the
current one: export again (Credentials › The break-glass record), then verify.

## Step 2: r2's intent, then its deploy

The change is `deploy/intent-changes/c455-console-login-r2.json`.
- **Its `before`** is r2's committed `lines` exactly, read 2026-10-05: `con 0` (`logging
  synchronous`, `stopbits 1`), `aux 0`, and `vty 0 4` (`logging synchronous`, `login local`,
  `length 0`, `transport input all`).
- **Its `after`** adds `login local` to `con 0`, in IOS's own order.
- If r2's intent has moved since, the tool refuses and names both values: re-read it before
  going on.

```
scripts/nmas-bulk-intent --list Default --devices r2 --change deploy/intent-changes/c455-console-login-r2.json
```

**Expect** "1 device(s), 1 group(s)", with one render delta that adds `login local` under
`line con 0`. Anything else: stop.

```
scripts/nmas-bulk-intent --list Default --devices r2 --change deploy/intent-changes/c455-console-login-r2.json --apply <HASH> --actor <you>
```

**Then deploy r2 from its device page** (Deploy…). The preview's program must be exactly:

```
line con 0
 login local
```

Any other line: stop. It is merge-only, so nothing is removed, and verify reads r2 after.

**What this cannot lock you out of:**
- SSH (vty) is unchanged and already `login local`, with the same credential the record holds.
- If the console refused the record's credential, SSH still reaches r2, and the change can be
  read and undone from there.

**Not measured:** how vrnetlab's BOOT path meets a console login.
- vrnetlab replays some platforms' startup configuration over the console (`CONSOLE_REPLAYED`
  includes the vIOS switches), and the C8000V is configured at boot by CVAC.
- So **nothing in this step reloads or redeploys r2.**
- Before step 4 reaches the vIOS switches, the operator reads vrnetlab's vIOS launch script on
  the lab host for a console login prompt during the replay. If it would stall there, the
  switches' rollout waits for a decision.

## Step 3: the drill, variant B (the console now asks)

Steps 1, 3 and 5 as above. Steps 2 and 4 change:

**2B.** `docker exec -it clab-rcn-lab1-r2 telnet localhost 5000`, then Enter. **Expect
`Username:`.**
- Sign in with the username and password from `reveal` (step 1). Expect `r2>` or `r2#`.
- A refused login is the finding: STOP, leave the console, and report. SSH still reaches r2.

**4B.** Still sign in over SSH as in step 4, so both paths are proven on the same day.

**The result:** add a row for 2B: "asked for a login; the record's credential accepted (yes or
no)".

**DONE AND PROVEN on r2, 2026-10-05 (the operator):**
- **Step 2:**
  - the intent (`login local` under `line con 0`) committed;
  - deployed from r2's v2 page, the program exactly `line con 0` / ` login local` / `exit`;
  - the new golden `faa29a7cae` differs from the last by that one line.
- **Step 3, variant B, passed at 02:55 UTC (20:55 the operator's time):**
  - the console asked `Username:` and `Password:`;
  - the break-glass record's credential was accepted
    (`%SEC_LOGIN-5-LOGIN_SUCCESS … [Source: LOCAL]`);
  - it landed at `r2#`, privilege 15. So the console is closed to anyone without the
    record, and `enable` asks nothing past the login (C457).
- On desktop, the deploy still shows the vertical stepper. That is expected until K (the one
  stepper) is built in 7.4.

## Step 4: the fleet (written when step 3 passes)

**The ROUTERS are done (the operator, 2026-10-05):**
- r1, r3, r4 and r6 went as one batch, golden commit `6f5ebf26fc`.
- r3's console was checked by hand and asked for the login.
- All five routers now ask for a console login.
- The first confirmed batch (r1, r2, r4 and r6, r2 by mistake) was re-planned before the one
  that landed; what became of it is C461.

**Next:** the switches, once vrnetlab's vIOS launch script has been read.

**The operator's correction (2026-10-05): ROUTERS first.**
- **The routers:** one change file for r1, r3, r4 and r6 (the C8000Vs, configured at boot by
  CVAC), as one batch.
- **The vIOS switches come only after vrnetlab's vIOS launch script has been read.** It types
  their startup configuration through the console at deploy, so a console that asks for a
  login may stop that replay. They may need a recorded LAB EXCEPTION: consoles left open on
  the vIOS switches, with the reason, as a lab-specific decision in local configuration,
  never the product's default. s3 goes last whichever way that falls.
- **The enable secret** (C457) is its own decision and its own step, never in this one.
