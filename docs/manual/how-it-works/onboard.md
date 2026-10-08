# Onboard a device

Onboarding brings a NEW device into the tool in two phases. Create sends nothing to any device: it stages a one-time credential, commits the device's bootstrap intent and makes a bootstrap configuration to boot it with. Verify then reaches the device, replaces that credential, cleans it up, saves it, records its first golden and adds it to the inventory. A device the tool did not build is adopted instead (see [Adopt a device](adopt)).

![The onboarding flow: Create stages a credential and commits a bootstrap with nothing sent; the device boots on that bootstrap config (static, DHCP, or served by the tool through ZTP); Verify reaches it, rotates its credential, saves it and records its first golden, then promotes it; seeding and deploys follow.](diagrams/onboard.svg)

Only IOS-XE can be onboarded today. Classic IOS is listed and refused at the plan, because whether its bootstrap configuration stalls while the device generates its SSH key has not been measured.

## Phase one: Create (nothing is sent to any device)

You choose the list, the device's name, platform and role, the interface the tool will reach it on, and how it gets its address: static, a DHCP reservation, or ZTP (the tool writes the reservation and serves the configuration on first boot). The review screen shows the plan and the bootstrap configuration with a placeholder password in place of the real one; the plan refuses at once anything that would fail later, every reason together. Create builds the plan again from the form and refuses if it no longer passes. It needs a verified person. Then, in order:

1. **Credentials** (`credentials`). Read: nothing. Sent: nothing. Recorded: a generated 24-character one-time password, staged encrypted in the list's repository folder (never committed), and then stored as the device's credential override in the credential store, keyed on its management address (the reserved address, for DHCP and ZTP), for the account `admin`. Staged first, so a crash between the two leaves something that can be recovered.
2. **Commit** (`commit`). Read: nothing. Sent: nothing. Recorded: the device in the list's manifest, marked PENDING (its name, platform, role, address source, MAC and reserved address), and its initial intent: the bootstrap parameters (address, mask, interface, gateway, domain, platform, address source, MAC) and the network's syslog block, committed as you with `Source: onboarding`. The device is now known to the tool and not in the inventory, so nothing polls it, backs it up or offers it in bulk actions.
3. **Reserve** (`reserve`, ZTP only). Read: Kea's running configuration and leases, to check again that the MAC and address are free and that no route or resolver option would reach the device. Sent: nothing to the device. Recorded: the DHCP reservation, in the fragment file the tool owns in Kea's configuration: the file is written as a candidate, tested with Kea's own configuration test, swapped in, Kea is told to reload, and the reservation is read back from the running server. It is last among the steps that can fail, because it is what the device will see.
4. **Render** (`render`). Read: nothing. Sent: nothing. Recorded: nothing: the bootstrap configuration is never stored. It is rendered again whenever it is needed, from the committed intent and the staged credential, so it exists exactly while that credential does.

A failure stops the run, says which step and why, and leaves only what the tool wrote; Abandon removes it.

## Between the phases: the device boots

The device must boot with its bootstrap configuration. That configuration is the minimum that makes the device reachable: its hostname, the `admin` account with the one-time password (privilege 15), the domain name, the management interface's address (or `ip address dhcp`) and SSH-only login on the vty lines. How it gets onto the device depends on the address method, and only ZTP does it without a person.

A pending device can be abandoned at any time: nothing the tool did has reached it, so abandoning removes only what the tool wrote (the reservation first, for ZTP, then the intent, the staged credential and the name). The pending row is flagged overdue after a day and stale after a week; one boot takes minutes.

### Static: a person applies it {#static-a-person-applies-it}

![Static address: the tool renders the bootstrap config on request and records the download as a reveal; a person carries the file to the device and applies it; the device boots with its address; Verify reaches it.](diagrams/onboard-static.svg)

What the tool does: it renders the configuration when asked, and nothing else. What you do: everything that gets it onto the device.

1. **Download it.** On the pending row, press Config (it calls `GET /onboard/bootstrap/<device>`). It is a reveal: it needs a verified person, it is recorded in the reveal record with who and when, and a refusal returns no configuration at all. The file is saved as `<device>.cfg`. The review screen's copy is not usable: its password is a placeholder.
2. **Apply it.** Either paste it at the device's console in configuration mode (`configure terminal`, then the file's lines; it ends with `end`), or place it where the device loads its startup configuration from and boot the device. Nothing in the onboarding code reads or expects a particular startup path; where the file goes is yours.
3. **On IOS-XE, give the device an SSH key yourself.** For static and DHCP the IOS-XE bootstrap carries no `crypto key generate rsa` line, because the lab's emulated IOS-XE image generates one in its own day-0 configuration (lab integration). On any other IOS-XE device, generate a key at the console (`crypto key generate rsa modulus 2048`), or Verify finds the SSH port refused. Likewise the account line uses the `password 0` form on IOS-XE, because that image injects its own user ahead of a startup file and would refuse a `secret` for the same account; Verify's rotation replaces it with a hashed secret.

Where the credential travels: from the tool to your browser in the download, then however you move the file. It is in the clear in that file and at the console. What limits it: it is one-time, it is replaced by Verify's rotation (after which the file no longer signs in and Config refuses, because the staged credential is gone), and every download is a recorded reveal. Keep the file as you would a password until Verify has run.

Timing, measured in the lab: an emulated IOS-XE router takes about six and a half minutes to finish booting. If Verify says the device did not answer, the pending row names the likely causes in order, with the console command that settles each.

### DHCP reservation: an address, not a configuration {#dhcp-reservation-an-address-not-a-configuration}

![DHCP reservation: a person adds a reservation in Kea and carries the bootstrap config to the device, exactly as for static; Kea gives the device its address when it boots; Verify asks Kea for the lease to find it.](diagrams/onboard-dhcp.svg)

What the tool does: at the plan, it asks Kea whether the MAC you gave has a host reservation and refuses without one (a dynamic lease would move at a renewal and the record would not). At Verify, it asks Kea for the device's LEASE and uses that address, refusing if the lease and the reservation disagree. It writes nothing to Kea on this path.

What you do: add the reservation in Kea's own configuration before the plan, and then deliver the bootstrap configuration exactly as for static (download it from Config, a recorded reveal; paste it or place it as the startup configuration; on IOS-XE generate an SSH key unless the lab image does it). The bootstrap configures the management interface with `ip address dhcp`.

The reservation gives the device an address on its reserved MAC, and nothing more: no configuration file and no server option. On this path the configuration still arrives by your hand. The credential travels and is protected as for static. If Verify cannot find the device, it says whether Kea has no lease for the MAC yet (the device has not booted or not asked) or a lease that differs from the reservation, naming both.

### ZTP on IOS-XE: the tool serves it {#ztp-on-ios-xe-the-tool-serves-it}

![ZTP on IOS-XE: Create writes a Kea reservation carrying the server's address (option 66) and the file name (option 67); the configless device takes its address, asks the tool's TFTP responder for that file, and the responder renders it on request, records a reveal row, and serves it only to the reserved address; Verify then reaches the device.](diagrams/onboard-ztp-iosxe.svg)

What the tool does, all of it:

1. **The reservation** (Create's `reserve` step). Kea gives the reserved MAC its address, its hostname (option 12), the TFTP server's address (option 66: the tool's own address on that subnet, derived from the host's interfaces, never configured) and the file to fetch (option 67: `<device>.cfg`). Both server options are always sent. No route, resolver or static-route option (3, 6, 33, 121) may reach the device, at any level of Kea's configuration, and the plan also checks that nothing on the segment answers DNS: a configless IOS-XE device that can resolve names calls Cisco's servers before it looks for anything local.
2. **The responder.** A small TFTP server in the tool, started by a systemd socket on UDP port 69 bound to the ZTP interface, so it holds no privilege. Read requests only, octet mode, 512-byte blocks. For each request it decides, from what it reads at that moment: the requester must hold a reservation the tool wrote; the file asked for must be the one that reservation names; the device must be pending and onboarded as ZTP. It then renders the configuration from committed intent and the staged credential, writes a reveal row (the requester, the device and the hash of what it serves, never the text) and only then sends it. Anything else is refused with a TFTP error, and the refusal is recorded too. Nothing is written to disk but those rows. HTTP is not used anywhere on this path.
3. **The bootstrap** for ZTP generates the device's SSH key and uses the `secret 0` account form, because no day-0 configuration from anywhere else will.

What a person does: cable and power the device with no startup configuration, and touch nothing at its console. Any input there (even `enable`) stops discovery. With no startup configuration, IOS-XE runs AutoInstall: it takes the lease, asks the server in option 66 for the file in option 67, and applies it. It does not save it; Verify's persist step does.

In the lab, the emulated IOS-XE image always boots a day-0 configuration of its own, so a lab node only asks after its launch script is patched to boot configless (lab integration). A real IOS-XE device with no configuration asks by itself.

Where the credential travels: over TFTP, which is cleartext, on the ZTP segment, inside the configuration. What limits it: only the reserved address is served, only the named file, only while the device is pending; every fetch is a reveal row written before anything is sent; the configuration is rendered per request and never stored; and the credential is one-time, replaced by Verify's rotation, after which the responder has nothing to serve (the device is no longer pending and the staged credential is gone).

Timing, measured in the lab on IOS-XE 17.6: the fetch is a few blocks and takes seconds; AutoInstall retries roughly every 8 seconds and gives up after about 2.5 minutes and nine unanswered requests, after which the device needs a reload to ask again. So a responder that is down or refusing during that window fails the onboarding rather than delaying it.

How to tell where it is: the pending row on the device list shows its ZTP stage, each from its own source (Kea's running configuration, Kea's lease table, the responder's reveal rows):

- `reservation_missing`: the reservation is not in Kea's running configuration; abandon and re-create;
- `reserved_not_leased`: no lease yet: the device has not booted or not asked;
- `leased_not_fetched`: it has an address and has not asked for its file;
- `asked_not_served`: it asked and was refused, with how many times and the last reason; act within AutoInstall's window or reload it;
- `fetched_not_reached`: it fetched its file; Verify must now reach it over SSH.

The responder has its own row on Needs attention (`nmas-ztp-responder`): its socket down, not installed, or failing since it last started.

### ZTP on classic IOS: not built {#ztp-on-classic-ios-not-built}

There is no code for it. Classic IOS cannot be onboarded at all today: the plan refuses the platform (its bootstrap's SSH key generation during a console replay is unmeasured). The responder serves only the file the reservation names, so AutoInstall's default file names (such as `network-confg`, `router-confg` or `<hostname>-confg`) are never served.

## Phase two: Verify

Verify reaches the device, which is the only proof its address and management interface are right. It is a preview and a confirm, because it sends a program, and it needs a verified person.

**The preview** reaches the device and sends nothing. Read: the device's address (for DHCP and ZTP, the lease Kea holds for its MAC), a check that it answers ICMP or TCP port 22, an SSH login with the staged credential, and its running configuration. It then shows what Verify will send: the removal of any read-write SNMP community the device arrived with (and the read-only ones kept), and the network's monitoring profile lines the device lacks, masked. You confirm its fingerprint, which binds the configuration read, the profile program and the removal lines.

**The confirm** holds the device for the whole phase and runs, in order:

1. **Verify** (`verify`). Read: the address as in the preview (a DHCP or ZTP lease that disagrees with the reservation is refused, naming both), the ICMP or TCP check, and an SSH login with the credential the tool holds for that address. Sent: nothing. Recorded: for DHCP and ZTP, the discovered address and its prefix on the manifest. Three outcomes, each said: it answered; it answered and refused the credential (so the address and interface are right); it did not answer (with the likely causes, most worth checking first).
2. **Capture** (`capture`). Read: the running configuration, over SSH with the staged credential. Sent: nothing. Recorded: nothing yet: held in memory. If the device or the profile moved since the preview, the fingerprint no longer matches and nothing at all is sent.
3. **Rotate** (`rotate`). Read, Sent and Recorded: as [Rotate a credential](rotate) describes, with three differences: there is no separate confirmation (the step records that it skipped the fingerprint check because there is no window between plan and apply), the new password is recorded in the credential override for the device's address rather than an inventory row (it has none yet), and no golden is written. Its commit carries the intent's secret reference and the manifest entry. On success the staged bootstrap credential is removed.
4. **Remove RW** (`remove_rw`). Read: the capture from step 2. Sent: `no <the line>` for each `snmp-server community … RW` line, verbatim, so the access list or view on it still matches. Recorded: nothing. Nothing to remove is a success.
5. **Profile** (`profile`). Read: the running configuration again, after sending. Sent: the monitoring profile's lines the device lacks, once, with errors read by the deploy's pattern. Recorded: nothing. A line that did not land fails the step. With no preview confirmed, or no profile, nothing is sent and the step says why.
6. **Persist** (`persist`). Read: `show startup-config` and the running `username` lines. Sent: `write memory`. Recorded: a persist row where job health reads it. The device's own save only (see [Persist](persist)); it does not touch the lab's startup files. A read-back that does not carry the rotated credential stops the run: the running configuration holds the only working credential, so do not reload the device.
7. **Golden** (`golden`). Read: the running configuration once more. Sent: nothing. Recorded: the device's FIRST golden, one commit as you with `Source: onboarding`. It is read after the cleanup and the rotation, so the repository's first record holds neither the read-write community nor the bootstrap credential.
8. **NetBox** (`netbox`). Read: NetBox, through the import. Sent: nothing to the device. Recorded: the device's objects in NetBox, imported from the first golden, with this Verify as the authority, and its NetBox id on the manifest. The step fails, and the device stays pending, when NetBox is not configured, when its writes are switched off, or when the import reports the device failed; writes that did not land are named.
9. **Promote** (`promote`). Read: the credential override, which now holds the rotated password. Sent: nothing. Recorded: the device's inventory row (address, driver, account, the rotated password encrypted, its identity, platform and role; on a NetBox-sourced list the row arrives with the next refresh instead), and the manifest marks it verified. It refuses to store the bootstrap credential as the device's password. Only now is the device onboarded.

Onboarding adds nothing to Oxidized: its step went with Oxidized's retirement (2026-10-08). The first golden's commit is the device's backup.

A step that fails stops the run and names every step that did not run; the device stays pending, and Verify can run again. Every Verify and Abandon is recorded beside the list's repository and read back on the pending row.

## Then

The device has bootstrap intent only. Seed its intent (see [Seed intent](seed)), and from then on change it by deploys.
