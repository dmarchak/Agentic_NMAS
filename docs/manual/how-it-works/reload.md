# Reload a device

On a device's page, **Actions › Reload…** restarts the device so it boots the startup configuration it holds. It is offered as an operation, never a command: the preview reads the device and judges six gates, a verified person confirms with a reason, and the run declares its planned-restart window before anything is sent, then waits for the device and checks it came back as it was. Nothing is configured: a reload sends no configuration, so the startup configuration must already be what the device runs.

![Reloading a device: the preview reads it and judges six gates; you confirm with a reason; the run reads it again and sends nothing if it moved, declares the planned-restart window before anything is sent, reloads, waits for SSH within the bound, verifies it runs what it ran, and records the run. A reload cannot be undone.](diagrams/reload.svg)

## The preview

The card reads the device once, in a job, holding nothing: `show running-config`, `show startup-config`, `show version`, `show boot` (a platform without it says so), `dir` of each image named, and `dir nvram:` when startup keeps a certificate as a file there. Sent: nothing that changes the device. Recorded: nothing. Each gate is drawn by name with what it found:

1. **Running against startup.** They must be the same configuration (compared section by section, the self-signed certificate the device regenerates left out, and the `Using … bytes` line `show startup-config` prints above it). Unsaved changes refuse the reload, because a reload boots startup and would lose them; **Persist…** beside it saves them first, previewed. An IOS-XE device keeps the certificates of its own certificate chains as files in nvram:, so startup holds a pointer (`certificate ca 01 nvram:CiscoLicensi#1CA.cer`) where running prints the same certificate inline. That is the same certificate (the same chain, type and serial) when `dir nvram:` lists the file, and the gate says so: "startup keeps r6's 2 certificates as files in nvram: (both present), running shows them inline". A pointer whose file `dir nvram:` does not list refuses the reload, naming the certificate and the file, and a different certificate is a difference like any other line.
2. **Its golden and its intent.** A device departing from its golden or its committed intent is shown, and your reason is recorded as acknowledging it.
3. **Startup carries Mercury's credential.** Every `username` line the running configuration holds must be in startup, the startup check's own judgement: a reload booting without it would lock Mercury out.
4. **The boot image.** The image `show version` says it booted must exist (`dir`), and the boot variable, where the platform has one, must name a file that exists.
5. **No other operation holds it.** Checked again when the run takes the device.
6. **What else goes down**, shown first and in its own colour: every device Mercury loses reach to while this one restarts. It is worked out from records, never a probe: committed intent gives each device's subnets, this host's interfaces give the subnets Mercury is on, and the devices still joined to Mercury without this one are the ones it keeps. A switch's VLAN subnets are taken down with it. What it cannot see is said with it: a path the routing does not use still counts as reach, and a switch carrying a subnet at layer 2 with no address in it is not seen.

The card also says how long the device is out: the run waits up to 2.5 times the platform's measured boot time (an emulated IOS-XE router, about 6.5 minutes), or, on a platform not yet measured, a placeholder it names as one.

## The run

The confirm needs a verified person and a reason in the shape of one. It is bound to the preview's fingerprint (the two configurations, the image, and whether the device departs). The run is a job holding the device, drawn on the one stepper:

1. `read`: the device is read again and judged again. Read: as the preview. Sent: nothing. Recorded: nothing. A device whose fingerprint moved since the preview, or whose gate now fails, is not reloaded, and the result says which.
2. `window`: the planned-restart window is declared, from now until the wait's bound plus five minutes, with you and your reason. Read: the restart record. Sent to the device: nothing. Recorded: the window. A window that cannot be recorded stops the run before anything is sent. Where the network's Grafana is configured, the window also sets a **Grafana silence** on the device's alerts (those naming it by its `device` label, as telemetry, the heartbeat and the syslog rule do, and those naming its management address as `instance`, as the SNMP rule does), as you, with your reason, until the window's end plus a settle margin of 19 minutes: the alerts outlast the device's return (on the lab's first reload the telemetry alerts were still firing two minutes after it answered). The step says what Grafana did: "silenced until …" with the silence's id, or "Grafana's alerts are NOT silenced: …" naming why (a credential that may not create silences, Grafana not answering). The silence's id is kept on the window, and the window is declared either way.
3. `reload`: `reload` is sent; the device's `[confirm]` is answered, and success is the session dropping. A `Save?` prompt is refused (startup is already what it runs), as is any other prompt, named. Sent: `reload` and its confirmation. Recorded: the drop time.
4. `wait`: the device's management address is asked on SSH's port every 10 seconds until it accepts, within the bound. Read: whether the port answers. Sent: nothing to the device's configuration. Once it answers, **the window ends** there, not at its declared end, so the device going down again is raised at once; the window's Grafana silence is moved to end the settle margin after now. Recorded: the window's end (`planned_restart_ends.jsonl`).
5. `verify`: Mercury signs in with the credential it holds and reads the running configuration, which must be what it ran before the reload. Read: the running configuration. Sent: nothing. The session compares the device's SSH host key with the one Mercury holds before it signs in, as every session does ([Re-key](rekey#every-session)): a reload keeps the key the device saved, so the same key passes; a device that comes back with a different key is refused with nothing sent, and verify fails naming both keys. The reload's window declares no new keys; if the device really did make a new key (it booted from a fresh disk), review it with Re-key on its page.
6. `record`: the run's row (who, why, the window, each step's outcome) is written to the network's repository (`.nsot/reloads.jsonl`) and committed as you, with your reason, then pushed like every commit; History draws it once, as the reload, beside the restart and its window. A row that could be written and not committed says so on the result.

## While it is down

Inside its window the device is **restarting as planned**, not broken: its page's header says "Restarting as planned (until …, by …)", and Needs attention raises no row for it, saying under *What was checked* that it is restarting as planned and who planned it. Its Grafana alerts are held the same way until the window's end plus the settle margin. If it is still not answering when the window ends, Needs attention raises it as not answering, critical, naming the window that ended. The restart itself is recorded when its uptime counter is next read lower than before, however long it was down, and History draws it as **Restarted as planned**.

## When it goes wrong

- **A gate fails:** nothing is offered but reading it again; the card names the gate and what it found.
- **It moved since the preview:** nothing is sent; preview again.
- **It does not come back within the bound:** red, with the time it waited. The way in is the console, with the device's break-glass record; the planned window stays declared until its end, and from then Needs attention raises it.
- **Grafana did not take the silence:** the `window` step says so and why; the reload goes ahead, and Grafana's own notifications for the device are not held. Mercury's Needs attention holds its alerts during the window all the same.
- **It comes back running something else:** red, with how many lines went and came (a line the platform rejected at boot is dropped silently). Its golden is not changed by the reload.
- **There is no rollback.** A reload cannot be undone, and the preview says so.

## What a reload does not do

- It sends no configuration, and boots no other file: booting a moment from history is a different operation (revert by reload, the charter's Phase 2).
- It does not check routing adjacencies after the restart: the Neighbours tab reads them at Prometheus's next scrape.
