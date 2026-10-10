# Adopt a device

Adoption brings a device the tool did NOT build under management. You supply a working
login; the tool uses it once, adds its own account, saves the device, records its first
golden, records it in NetBox and adds it to the inventory, and from then on uses only its
own account. The supplied account is not changed unless you choose to have it stored as a
hash.

![Adoption: the preview reads the device over the supplied login and sends nothing; the apply adds the tool's own account over a held session and proves it on a fresh login, sends the monitoring profile's missing lines, saves the device, commits its first golden, records NetBox (what existed as adopted) and adds the device to the inventory last.](diagrams/adopt.svg)

## How you start it {#start}

On **Devices**, press **Adopt a device…**. Its card asks for the device's name, management
address, platform and role, and the supplied login (and an enable secret, if the account
needs one); **Read it and preview** draws [the preview](#preview)
below in the same card. When nothing blocks, the card asks for the supplied password again
(no page ever holds it, so the confirm cannot carry it from the preview) and for why;
**Adopt <device>** starts the apply as a job, and the card follows its steps until it ends,
then draws each step's outcome. Adopting needs a verified person. A run that stops is run
again from the same card and resumes; its recovery has a host command as well,
`nmas-adopt-recover <device> --list <list>` (see [When a run stops](#stops)).

## The supplied credential is never written

It is somebody else's login. It is held in memory for the operation only, never in a file, a
log or a commit: every log line and every sentence in the result has it masked, for any
length. If adoption fails, its owner still has it, unchanged. The password the tool
generates for its OWN account is different: that one is staged (encrypted) before it is
sent, because losing it would lock the tool out.

## The preview (it reads, and sends nothing) {#preview}

You give the list, the device's name, its management address, its platform, its role and
the supplied login. Every reason to refuse is drawn at once, each by name.

1. **What can be refused without the device.** Read: the list's inventory, its manifest,
   the staged credentials, the NetBox write switch. Sent: nothing. Recorded: nothing. The
   role must be given (never guessed from the platform); the list must exist; the name and
   address must not already be managed or recorded in the manifest (an adoption in progress
   at that name and address resumes); no tool password may be staged from an earlier run
   that was never settled; and NetBox writes must be on, because adoption records the device
   there before it joins the inventory.
2. **The device, read with the supplied login.** Read: over SSH (Netmiko), as the supplied
   account, `show running-config`, `show startup-config`, the `aaa` lines and the
   `line vty` stanzas. Sent: nothing but those show commands. Recorded: nothing. A read
   shorter than ten lines is refused as a failed read, and the device must call itself by
   the name you gave.
3. **Can the tool's account work?** Read: the authentication lines just read. Sent:
   nothing. Recorded: nothing. A device whose SSH logins would never consult a local account
   (vty `login local` absent, or AAA with `local` not first in the lists the vty uses) is
   refused, naming why.
4. **Every credential the golden would carry in a reversible form.** Read: the running
   configuration. Sent: nothing. Recorded: nothing. A `username ... password 0` or
   `password 7`, or an `enable password`, is refused by name (its form, never its value),
   because the golden is stored verbatim and pushed to the remote. SNMP communities are the
   accepted exception. Only the SUPPLIED account may be converted, if you choose to store it
   as a secret (same password; the device hashes it); that works only when its line carries
   nothing but a privilege and a password and it is the account's only line.
5. **The tool's account.** Read: the running configuration and the credential store. Sent:
   nothing. Recorded: nothing. An account by the tool's name (`nmas` by default) that the
   tool did not record adding is somebody's, and refuses. One the tool recorded adding means
   an earlier run is resumed.
6. **What a save would make permanent.** Read: running against startup. Sent: nothing.
   Recorded: nothing. The preview lists the lines a save would make permanent and the lines
   it would lose at the next reload (or that the device has no startup configuration at
   all), and the read-write SNMP communities it keeps.
7. **The monitoring profile's program.** Read: the network's committed profile against this
   capture. Sent: nothing. Recorded: nothing. The lines the device lacks are shown, masked.
8. **What NetBox holds, and what the import would do.** Read: NetBox's device of that exact
   name, its interfaces and addresses (REST API), and the import's own dry run over the
   capture. Sent: nothing. Recorded: nothing. A NetBox that cannot be read refuses.

When nothing refuses, the preview carries a fingerprint of the list, device, address,
platform, role, tool account, the conversion choice, the profile's program and both
configurations. The apply is bound to it.

## The apply, in order

Holding the device (no other operation may touch it meanwhile), and refusing if anything
moved since the preview:

1. **Confirm** (`confirm`). Read: everything the preview read, again, over the supplied
   login and from NetBox. Sent: nothing. Recorded: nothing. A different fingerprint refuses
   with nothing sent, naming both.
2. **Add the tool's account** (`account`). Read: the device's authentication lines and its
   accounts, again. Sent: one line, `username <tool> privilege 15 algorithm-type scrypt
   secret <generated>`. Recorded: the new password staged encrypted before the push, then
   the tool's credential in the credential store, keyed on the address. Rotation's lockout
   defence, in this order:
   - the supplied login is opened and HELD for the whole step;
   - the generated password is staged, with a note of the address and account beside it;
   - the line is sent on the held session;
   - a FRESH login as the tool's account must succeed and the device must hold a type-9
     secret; if not, `no username <tool>` is sent on the held session and read back gone;
   - if you chose the conversion, it runs here, on the same held session (step 3 reports
     it);
   - the held session closes, the credential is recorded, and the staged copy is cleared;
   - on a resumed run, the recorded account is only proven on a fresh login, and nothing is
     sent.
3. **The supplied account** (`owner_account`). Read: a fresh login as the owner. Sent: only
   if you chose the conversion: the account re-sent as a secret with its SAME password
   (deleted and set in one round trip where it held a `password`). Recorded: nothing new.
   Not chosen, it reads "not changed". If the fresh login fails, its original line is put
   back on the held session (or, failing that, over a fresh session as the tool's account)
   and proven; if that cannot be proven, the result says DANGER first and names the line's
   form, and adoption stops.
4. **The monitoring profile** (`profile`). Read: the device's configuration afterwards, as
   the tool's account. Sent: the profile's lines the device lacks, on a new session as the
   tool's account, rejected lines read as a failure. Recorded: nothing. Skipped, saying why,
   where there is no profile or nothing to send. A line that did not land stops the run
   before the save.
5. **Save** (`persist`). Read: `show startup-config` and the running `username` lines.
   Sent: the device's save. Recorded: a row in the rotation record, which job health reads.
   The startup configuration must carry every `username` line the running configuration
   holds, verbatim; until it does, the tool's account would not survive a reload.
6. **The first golden** (`golden`). Read: `show running-config`, as the tool's account.
   Sent: nothing. Recorded: the device's identity in the manifest, marked adopted (never
   onboarded), and its first golden committed as you, `Source: adopt`; the commit is pushed
   to the remote by the post-commit hook. It comes after the account, the conversion, the
   profile and the save, so the first record is the device as it will be managed.
7. **NetBox** (`netbox`). Read: NetBox's objects for the device again (REST API). Sent:
   nothing. Recorded: in NetBox, the import from the golden (what it creates is tagged
   `nmas-managed` and recorded as created; what it updates is recorded as modified); in
   `data/netbox_adopted.json`, every object that EXISTED before, as adopted, with who, when,
   why and on what basis, so Remove can never delete it; and the NetBox id in the manifest.
   What existed is read before the import, so it is never mistaken for something created.
8. **Into the inventory** (`promote`). Read: the manifest. Sent: nothing. Recorded: the
   device's row in the list's inventory, with the tool's account and its password
   (encrypted). Last, because the row is the claim "this device is managed". On a
   NetBox-sourced list no row is written; the device arrives at the next refresh.

Adoption adds nothing to Oxidized: its step went with Oxidized's retirement (2026-10-08). The
first golden's commit is the device's backup.

Whatever happened, the run is recorded in the list's `onboarding_runs.jsonl` as an `adopt`
run. A finished adoption names its next step: export the break-glass record, which holds no
entry for the device until you do; then seed its intent from the golden on its Device page.

## When a run stops {#stops}

A stopped run names every step that did not run and why. Running adopt again resumes: the
account the tool added and recorded is proven, never added twice, and the save and the
import are safe to repeat. Two outcomes keep the staged password because it is the only
copy: the account was added and its record failed, or a failed verify's removal could not
be proven. Settle either on the host with `nmas-adopt-recover <device> --list <list>`,
which asks the device with the staged password on a fresh login: accepted, it is recorded
and only then cleared; refused, the file is kept and the result says what to check.

## What adopt does not do

- The supplied account is not changed, rotated or stored, unless you chose the conversion,
  which keeps its password.
- No read-write SNMP community is removed: onboarding removes one only because the tool put
  it there, and on this device something real may use it.
- Nothing else in the configuration is changed: only the tool's account and the profile's
  missing lines are sent, and nothing is removed.
- No intent is committed: seed it from the golden afterwards.
- No NetBox object that exists now is made deletable.
