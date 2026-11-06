# Manual steps: every step an operator performs, DECISION or LABOUR

**The rule** (the operator, 2026-10-20; CLAUDE.md, "Mercury automates labour; people make
decisions"): every step an operator performs is either a **DECISION** only a person should
make, or **LABOUR**. Decisions include approving a change by hash, giving a reason, declaring a
window, and the break-glass passphrase. Each LABOUR row carries a written justification for
why Mercury cannot do it yet, and the finding that removes it. Labour includes typing data
Mercury could derive, copying files, running host scripts, pressing a button whose outcome is
already approved, and cleaning up after Mercury's own operations.

**Scope:** every operator step named in the walks (docs/LAB8_MORNING_WALK.md, the W walks), the
host steps (`scripts/host-steps/`), the runbooks (lab/REDEPLOY.md, docs/UPDATE.md,
docs/DEPLOY_LINUX.md) and the manual (`docs/manual/`). **Seeded 2026-10-20 from Lab 8's walk and
today's host steps; the rest of the scope is surveyed into it at the usability review (C1438),
of which this register is a criterion.** That a walk, host-step script or manual page names no
step missing from here is not mechanised yet (C1461).

**Kinds.** DECISION: stays a person's. LABOUR: Mercury should do it; *justified* says why it
cannot yet, *finding* removes it. LAB: lab tooling outside the product (containerlab, the lab
host), kept out of the product by the lab-specifics rule; listed so the walk's count is whole.

## The register

| # | Step | Where named | Kind | Justification (why a person does it today) | Finding |
|---|---|---|---|---|---|
| M1 | Confirm a preview by its hash (deploy, Mode B, Retire, Add device, Add a subnet, Abandon, Save All) | every operation's manual page; the walk throughout | DECISION | approving a change is a person's | — |
| M2 | Give a reason (Mode B removal, an authorised line, Retire, a window, an acknowledgement) | the same | DECISION | the reason is the record of why | — |
| M3 | Declare a planned-restart window before a restart | lab/REDEPLOY.md step 1; walk D5 | DECISION | which devices may restart, when, is a person's | — |
| M4 | Break-glass: type the passphrase, export, carry the file off the host, delete the copy | walk (before Retire); Credentials page | DECISION (passphrase) and LABOUR (carry), justified | the record must live where Mercury is not; Mercury never holds the passphrase | — (justified by design) |
| M5 | Acknowledge a Needs attention row | the manual's Needs attention page | DECISION | the person says it is understood | — |
| M6 | Choose to add a device, and which network, role and platform | walk A5, A8; Add device | DECISION | what joins the network is a person's | — |
| M7 | Choose to retire a device | walk A6; Retire | DECISION | what leaves the network is a person's | — |
| M8 | Type a ZTP device's address, MAC, management interface and route option at Add device | walk A5, A8; section 2 | LABOUR | the address is the far end of the parent's relayed link and is derivable; the MAC comes from the device (at scale, a vendor manifest or the first DISCOVER) | C1460 (the link derived), C1412 |
| M9 | DHCP › Add a subnet for each ZTP link | walk A3; section 2 | LABOUR | Add device does not yet create its link's subnet | C1460, C1412, C1413 |
| M10 | Run the firewall host step after a relayed subnet (`c1346-ztp-relayed-firewall.sh`, sudo) | walk A4; the host step | LABOUR | ufw is root's; a covering admission removes the per-subnet run | C1460 (covering admission), C1462 |
| M11 | Run the alert-rules install step after an onboarding or a retirement (`c1419-install-alert-rules.sh`, sudo) | walk A7, R3; Retire's result | LABOUR | Grafana's provisioning files are root's and need a restart | C1463, C1462 |
| M12 | Re-measure the heartbeat population after a device's intent is deployed | walk R3; Monitoring › Heartbeat | LABOUR | a button whose outcome is already decided by committed intent | C1463 |
| M13 | Run `nmas-telemetry-rules` on the host after a golden gains subscriptions | walk R3 | LABOUR | the generator is not run by the commit that changes its input | C1463 |
| M14 | Press Verify after a ZTP device fetched its bootstrap | walk R1; the pending page | LABOUR | no policy says an approved pending device may be promoted unattended | C1464 |
| M15 | Seed intent…, then hand-edit the device's intent (links, addresses, protocols) | walk R2 (section 4); Intent tab | LABOUR | the actions framework is not built: a link, its addresses and its protocol are typed | C1438, docs/INTENT_AUTHORING_DESIGN.md A1, A4 |
| M16 | Acknowledge unmodelled lines the seed captured itself (`unmodeled_ack`) | Intent tab | LABOUR | the seed records what it could not model and then asks the person to acknowledge its own capture | C1465 |
| M17 | Type Show commands after a deploy to read the adjacency and routes the change was for | walk R2's after-reads, step 7 | LABOUR | Verify checks counts, not the declared facts the change exists for | C1466 |
| M18 | Save All before a redeploy, so a baseline holds today's goldens | walk B1 | LABOUR | a scoped verified deploy earns no baseline | C1454 parts 1 and 2 |
| M19 | `chmod 600` the lab's startup files on the lab host | walk B4 | LAB | lab tooling writes them with the default umask | C1453 |
| M20 | Commit a manifest entry an operation left uncommitted (here: Abandon and re-Create) | walk A6's block, 2026-10-20 | LABOUR (cleaning up after Mercury) | Create left its pending entry uncommitted | C1468 (fixed for Create and Abandon) |
| M21 | Delete a retired device's NetBox record, and sites, regions and VRFs nothing uses | walk A6; section 7 | LABOUR (cleaning up) | Retire leaves the record Decommissioning; nothing removes unused objects | C1446, C1445 |
| M22 | Plan a device in NetBox; create a host VLAN's group, VLAN and prefix; a host's cable | section 7; step 10 | LABOUR | no Mercury action does them | C1447, C1448, C1449 |
| M23 | Remove a retired device's pre-change file (`c1423-retired-pre-change.sh`, sudo) | the host step | LABOUR (cleaning up) | Retire does not remove it | C1423 |
| M24 | Run the redeploy command; destroy or add a lab; console `write erase` and `reload` for a rehearsal | lab/REDEPLOY.md; walk D5, C3, Friday | LAB | containerlab is test infrastructure, outside the product | — (lab) |
| M25 | Read the host's measurements before a redeploy (memory, swap, the hypervisor) | walk D2, D3 | LAB | the lab host's capacity is the lab's | — (lab) |
| M26 | Out-of-band ZTP: type the kick-start's parameters other than the hostname (a switch's access port and VLAN) | manual: onboard#console-kick-start | LABOUR | NetBox holds the device's interfaces and the planned address, but nothing yet reads which port leads to the relay or which VLAN the address is in; the hostname is derived | C1574 |
| M27 | Out-of-band ZTP: press Use <MAC> in the plan after the survey, then Create | manual: onboard#out-of-band-ztp | DECISION | the MAC changes the reviewed plan, and Create binds what a person reviewed | — |
| M28 | Out-of-band ZTP: type each console-server port's record (driver, host, container or TCP port, key name) | manual: installation-settings#console-servers | LABOUR, justified | how a console server is reached is in no source Mercury reads (the operator's design keeps it out of NetBox); a NetBox port with no record is listed with Set up… | — (justified by design) |
| M29 | Out-of-band ZTP: install a console key's authorized_keys line, and the bridge wrapper by its host step, on the console host | manual: installation-settings#console-server-keys | LABOUR, justified | the console host is another machine, and Mercury holds no access to it until the line is installed: the trust is granted from the host's side | — (justified by design) |
| M30 | Out-of-band ZTP: make the console server's device and ports, and the device's console port and cable, in NetBox | the Console servers tab ("made in NetBox first") | LABOUR | `console_path.ensure_console_path` builds the device's side behind the write gate, but no screen offers it, and the console server's device must exist first | C1576, C1555 |
| M31 | Out-of-band onboarding in one decision: confirm "Onboard <device> through its console" with a reason | manual: onboard#out-of-band-onboarding | DECISION | it types on a device and creates it; everything else (the address, mask, VLAN, interface, gateway, config server, Create, the kick-start, the read-back, the copy, the wait for SSH) is the run's | — |
| M32 | Out-of-band onboarding: type the uplink when NetBox cables none of the device's interfaces to the relay | manual: onboard#out-of-band-onboarding | LABOUR | derived from NetBox's cable when there is one; Mercury keeps no LLDP table to read it from otherwise | C1612 |
| M33 | Set a secret reference's value: type it twice with a reason, per device (Intent tab, Set value…) | manual: set-secret-value | DECISION | the value is a secret only a person chooses (an account's password); the device's own form is then captured by Mercury, not typed | — |
| M34 | Set the installation's no-change windows by a host step (`scripts/host-steps/c2613-no-change-windows.sh`, through `write_settings()`), and set them again when a window kept in local time changes season | the host step; docs/OPEN_FINDINGS.md C2613 (run on the NMAS host by the operator, 2026-11-06: PASS, 08:30 to 09:10 to 08:30 to 10:30 UTC, read back, the actor recorded; with it, local CI's quiet window set to 02:30-03:30@America/Denver, its self-test passed) | LABOUR | `no_change_windows` has no screen (C2611), so only a host step can set it through the one write path; and it holds UTC only (C2614), so a window kept in local time is set as both seasons' union (this lab's 08:30 to 10:30 UTC for 02:30 to 03:30 America/Denver), or set twice a year | C2611 (the screen), C2614 (a zone per window) |
| M35 | Lab 9's sessions S1 and S2: record each reboot test's planned-restart window first, with `nmas-planned-restart <network> <device> --minutes 20 --why … --by <operator>` (an OVS host, the controller, an Arista, the HP) | the SDN platform design (revision 4), section 16b; decision 17 | LABOUR | the window itself is a decision (M3), but v2 has no control that declares one except a device's own Reload, so it is typed at the host's CLI; from S3 on controller management declares its own | C1361 |
| M36 | Lab 9: mark the router and the 2960 observe-only in NetBox (each device's local config context data, `mercury.management: observe`) | docs/LAB9_NETBOX_STEPS.md steps 1 and 2; the design's section 9a | LABOUR | which devices Mercury may change is a decision, but typing it is NetBox UI work: no Mercury screen writes a device's config context, and Mercury's NetBox token does not edit it | C2617 |
| M37 | Lab 9: widen `mercury_kind`'s validation to `host`, add the `linux` platform, give the controller's role the kind `host` and the controller the platform | docs/LAB9_NETBOX_STEPS.md steps 3 to 6; decision 5 | LABOUR | one-time NetBox schema and record edits with the operator's admin login: Mercury's role-kind migration (`role_kind.apply`) creates the field but does not widen an existing one's validation, and its token may not edit roles (2026-10-11) | C2618 |
| M38 | Lab 9 S1: type each platform's credential profile on Credentials › Profiles (`platform:<slug>`) | the design's section 16b, S1 goal 1; docs/LAB9_NETBOX_STEPS.md step 7 | DECISION | the login values are secrets only a person types | — |
| M39 | Lab 9 S1 and S2: create `mercury-auto` on the network devices and `mercury` with its one sudoers line on the controller, at each device's console | the design's section 16b, "The operator's device changes"; S1 goal 6, S2 goal 1 | LABOUR, justified | no Mercury operation creates an account on a device it does not manage yet (the router and the 2960 are observe-only, the Aristas and the HP discovery-only, the controller a host); a deploy may add an account, never change one, so this ends when Mercury manages the device; an exception to the no-terminal-steps rule for hand-built lab devices, named in the design | C2619 |
| M40 | Lab 9 S1: read each reboot test's reconnect times from the controller's REST (`/stats/switches`, `/v1.0/topology/links`) and write them down | the design's section 16b, S1 goal 5 | LABOUR | Mercury reads the controller's switches but does not yet time a reconnect after a planned restart; P6's post-check is bounded from these numbers | P6 (controller management's post-checks), C2593 |

## Candidates to automate, sized where known (none built now; Lab 8's build first)

- **The per-link ZTP subnet** (M8 to M10): C1460, M to L; C1412 and C1413 (B).
- **Intent hand-edits** (M15): the actions framework, C1438 and INTENT_AUTHORING_DESIGN.
- **NetBox cleanup, cables, VLANs, prefixes** (M21, M22): the one-interface findings,
  C1445 to C1449.
- **Verify after a ZTP fetch** (M14): an "auto-onboard approved devices" policy, default on and
  switchable, C1464.
- **Unmodelled lines the seed captured itself** (M16): C1465.
- **Sudo host steps** (M10, M11, M23) through a narrowly scoped privileged helper that runs only
  named, signed steps: C1462, its security sized there.
- **Monitoring rules on onboarding and retirement** (M11 to M13): C1463.
- **After-reads** (M17): C1466.

**Justified, staying with a person:** the break-glass passphrase and carrying the record (M4);
confirm by hash (M1); reasons (M2); windows (M3); acknowledgements (M5); what joins or leaves
the network (M6, M7).
