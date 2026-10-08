# Test the logging path: does a device's log reach Mercury?

From **Show commands**, on the devices the card has chosen: **Test the logging path** asks each
device to write one line into its own log, then watches Loki for it. Each device's result says
"received after N s" or "not received within 30 s". Nothing about a device's configuration
changes; the line is the only thing it writes.

The heartbeat (a line every five minutes, on devices that carry its applet) proves the path all
the time. This test proves it now, for any device, when you ask.

![Test the logging path: the line is checked against Tier 1 of the command policy and a test is refused when Loki is not configured, before any device is asked; each device is held and sent one line, send log 6 MERCURY-LOGTEST and the run's id, through the reads engine; Loki is asked every 2 seconds, once for the whole run, until each device's line arrives or 30 seconds pass after its send; the result is recorded with the run, and History shows it.](diagrams/logging-path.svg)

## The steps

1. `refuse`: the line is checked against Tier 1 of the command policy, as any command is, and
   the test is refused when Loki is not configured (Settings, Integrations): nothing could
   watch for the line. Read: nothing. Sent: nothing.
2. `send`: each device is held and sent one line through the reads engine:
   `send log 6 MERCURY-LOGTEST <the run's id>`, at level 6 (informational), the level no alert
   rule keys on. A device another operation holds is skipped, named with its holder, and its
   result is "not sent".
3. `watch`: Loki is asked every 2 seconds, with one question for the whole run, never one per
   device, for lines holding the run's token. A line counts for a device only when it also
   carries the device's own name, matched as the Logs tab matches it. The watch ends when
   every device's line has arrived, or 30 seconds after the last send. "After N s" is the time
   Loki received the line, less the time the device's answer reached Mercury: both are this
   installation's clocks, never the device's.
4. `record`: each device's result is kept with the run, and History shows it. A device whose
   line did not arrive is drawn first, with when Loki last received anything from it.

## What the results mean

- **Received after N s**: the path works, end to end, now.
- **Not received within 30 s**: the device took the line (its answer came back) and Loki never
  received it. The path is broken after the device: its logging host, its source interface,
  the route to the collector, or the collector itself. Open the device's Logs tab to see what
  Loki last received from it.
- **Not sent**: the line never left Mercury for that device (it was held by another operation,
  or did not answer). Nothing is said about its path.
- **Unknown**: Mercury could not ask Loki, or Loki's answer was cut. The line was sent;
  whether it arrived is not known. This never reads as "not received".
