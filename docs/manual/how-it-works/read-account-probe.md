# Probe the read-only account

The probe measures, on one device, what the AI's read-only account may and may not run: every
read the AI asks, expected answered, and five commands, expected refused. It configures
nothing. It is one operation with one home: **Probe…** on Credentials and the command line
`nmas-read-account-probe` run the same plan, the same run and the same record. Board R's R8,
provisional, operator review pending.

![Probing the read-only account (board R's R8). The preview sends nothing: the probe's own plan names the account it signs in as, every command in the order it is sent and what each is expected to answer, under one hash, which you confirm. The run holds the device and signs in as the read-only account, never escalating: it sends each AI read, expected answered, then show running-config, configure terminal, clear counters, debug ? and enable, each expected refused, answering nothing but end or n. Its verdict comes from the device's own answers, and its masked record is kept under the device's identity, read on History and in the coverage.](diagrams/read-account-probe.svg)

## Where it is {#where}

On **Credentials › Profiles**, the card **Read-only account on the devices**: **Probe…** on a
device's row, where its intent names the read-only account or its golden holds it. It opens
the preview in place; **Cancel** closes it with nothing changed.

## The preview {#preview}

1. `preview`. Read: the credential store's name of the account (never its password), the
   device's committed intent and golden, and the AI read set. Sent: nothing. Recorded:
   nothing. Whom it signs in as (the account and its profile), every command in the order it
   is sent and what each is expected to answer, each argument from what Mercury holds for the
   device, the shapes not measured (no argument to fill) or not asked (another platform's form,
   or a form the installation choice **Let the read-only account ping and traceroute** keeps
   off), each with why, and the program's hash. When a run would be refused now (inside one
   of the installation's no-change windows, Settings › Installation, such as a nightly
   backup's, or while another operation holds the device) the preview says so and the button
   is not offered.

## The run {#run}

2. `confirm`. **Probe <device>**, as a verified person, confirms the hash. The plan is made
   again; a program that moved (the account, a read's argument, what Mercury holds) is refused
   naming both hashes, and nothing connects. Inside a no-change window it is refused too.
   The command line (`nmas-read-account-probe`) refuses the lab's nightly backup window as
   well, its own tooling's.
3. `hold`. The device is held for the whole run: another operation on it refuses this by name,
   and this refuses any other meanwhile; it is never queued.
4. `reads`. Signed in AS the read-only account, never the deploy account and never escalating,
   each AI read is sent as the AI would send it, judged by the AI's own check. An answer is
   ANSWERED; the device's own refusal is FAIL; `% BGP not active` is an answer.
5. `refused`. `show running-config`, `configure terminal`, `clear counters`, `debug ?` and
   `enable`, each expected refused by the device's own refusal. A configuration prompt is
   answered `end` at once, a `[confirm]` with `n` typed without Enter, and a `Password:` prompt
   is never answered: each is the account doing what it must not, a FAIL.
6. `verdict`. PASS (every read answered and every refused command refused), INCOMPLETE (no
   argument for some shape), FAIL, UNREADABLE or SIGN-IN REFUSED, from the device's own
   answers alone. A read the account is refused names the next proposal: a custom level's
   `privilege exec` line for exactly that read.
7. `record`. The record, every answer masked and the account's password among the values
   masked, written owner-only under the device's network and identity: a new device of the
   same name inherits none of it, and retiring the device removes it. The card draws the
   verdict and each command's result in place; History draws it under **Read-only account
   probes**, and the coverage's **Last probe** reads it. A probe refused, or one this server
   has no record of, offers **Probe it again…**, a new preview.
