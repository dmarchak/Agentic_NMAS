# Capture and Save All

A capture moves the golden toward the device: it reads what each device runs now and records
it as that device's golden. Save All is the same operation across every device in the
network, and it is the one that can earn a baseline.

## The preview

1. **Every chosen device is read now**, at once rather than one after another (a fleet read
   takes about as long as its slowest device). The preview runs as a job: the page answers at
   once and draws each device as its read finishes.
2. **Each read is judged before anything is compared**: a configuration that came back
   stitched together (two `end` lines, a prompt, an echoed command, another device's
   hostname, or far larger than its last golden) is refused with "the device's output could
   not be read reliably", never recorded.
3. **Each capture is compared twice**:
   - against its current golden: what would change in the record;
   - against its committed intent: whether the device is at intent, or departs from it, line
     by line. A regenerated self-signed certificate is labelled as one, not drawn as hex.
4. **The baseline decision is previewed**: Save All earns a baseline only when every device
   in the network was read and every one matches its committed intent. If one departs, the
   preview says which line decides it, and that the save will record the denial.

## The confirm and the apply

1. Each confirmed device is **read again**. A device whose capture moved since the preview is
   refused alone, and nothing is recorded for it.
2. **One commit** records every changed golden, as you, with `Source: capture` (or
   `save_all`), and with an `Intent-Match:` trailer saying whether each device matched its
   intent.
3. A whole-fleet save at intent is **tagged** `baseline/<time>`, with `Baseline: earned`. One
   that is not still commits, saying why it earned nothing; nothing changed still records the
   decision, as an empty commit, so a denial is never only a message on a screen.

## Why it works this way

The golden is a record of the device, so it is read from the device, never derived. And a
baseline claims the whole network was at its intent at that moment, so it is measured, never
granted because a save happened.
