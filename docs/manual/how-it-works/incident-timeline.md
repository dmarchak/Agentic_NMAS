# An incident's timeline and its time to repair

An incident's page ([An incident's page](incident)) leads with four times and a time to repair.
Each one is a record Mercury wrote while the incident happened. None is typed by a person, and
none is read from a device's clock.

![An incident's timeline, each time from a record Mercury wrote while it happened: detected is the event's receive time, the incident's first trigger (a log line's receive time, an alert's start, an adjacency's loss, a drift check's run); decided is the heal decision's time, or the time a person approved the proposed fix; applied is the act's check of each unit at intent, the first step after its program was sent; verified is the act's record step, when its outcome is a passed verify. Time to repair is verified minus detected, in whole seconds, drawn only from a passed verify: an attempt whose verify failed reads applied, verify failed, and the incident needs a person. No time is read from a device's clock.](diagrams/incident-timeline.svg)

## The four times {#the-four-times}

1. **Detected** is the event's receive time: the time of the incident's first trigger. For a
   configuration change, that is when Mercury's log reader received the device's line. For an
   alert, it is when the alert began, by Grafana's time. For an adjacency, it is when the
   adjacencies reader saw it go down. For drift, it is when the drift check ran.
2. **Decided** is when the fix was chosen: the time of self-healing's decision to heal, or,
   for a fix proposed to a person, the time that person approved it. A decision that chooses no
   fix (a can't-fix, a dry run's would-heal) leaves Decided at "not yet".
3. **Applied** is when an attempt's fix was on the device, whatever its verify then said: the
   time of the step that checks each healed unit is at intent, which is the first step after
   the program was sent. For an action such as a port bounce, it is the time of its send step.
4. **Verified** is when the fix's last check passed: the time of the step that records the
   outcome, when that outcome is a passed verify.

**Fixed** in the header is the applied time of the attempt whose verify passed, and only that.

## Time to repair {#time-to-repair}

Time to repair is Verified minus Detected, in whole seconds. It is computed each time the page
is drawn, from those two records. Hover over it for both times in UTC and what each one is.

It is drawn only from a passed verify. Otherwise it reads:

- "not repaired": the incident is open, or needs a person;
- "not repaired: verify failed": a fix was applied and its verify failed;
- "not repaired: nothing was sent": the fix was refused before anything reached the device;
- "not repaired: the fix was declined": a person declined the fix proposed;
- "cleared, no repair recorded": the incident closed with no fix recorded;
- "not recorded": one of the two times is no longer kept, and the page says which.

## A failed verify {#a-failed-verify}

A fix that was applied and did not pass its verify is never drawn as fixed. This covers a heal
that was rolled back, one that failed after sending, one only partly shown, and one whose
symptom remained. The incident's state is Needs a person. Its attempt reads "applied <time> ·
verify failed:" followed by the run's own reason, and its Fixed time stays empty.

## Who it was by {#who}

Beside the time to repair the page says who the fix was by, in the words its card and History
use.

- **by Mercury's self-healing · policy set by** a name is drawn only where the record shows
  the policy alone: the fix ran in Auto as the network's policy, no approval is recorded for
  it, and the decision was taken by self-healing's own apply. The name is the person who
  confirmed the policy. Turning Auto on was a person's decision; this fix was not.
- **by Mercury's self-healing · approved by** a name is a proposed fix that person approved.
- Where the record shows neither, the page names nobody.

## What the page reads {#what-it-reads}

Opening an incident's page reads only what Mercury already holds: its network's records of
the incident, its step log and its decisions, and the job of a heal still running. It reads
no device, Grafana, Loki or NetBox, calls no AI, and writes nothing, so it opens at once.
