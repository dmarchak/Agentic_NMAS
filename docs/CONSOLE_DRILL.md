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

**4. Sign in with the record's credential, from the lab host.**

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

| | |
|---|---|
| When (UTC, and the operator's time) | |
| The path to the lab host (LAN or tunnel) | |
| Step 1: the record opened, r2 listed | |
| Step 2: what the console showed; asked for a login? | |
| Step 3: the uptime line's first words | |
| Step 4: the record's credential accepted over SSH? | |
| Anything unexpected | |

**Then:** the terminal is removed (R39), with docs/CUTOVER.md updated.
