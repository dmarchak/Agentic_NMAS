# Turn a background AI feature on or off for a network

A background AI feature calls the model with no person pressing anything: a job's call, made
only when Mercury's own checks have found something (the SDN loop's classify, for example,
runs only when a detection rule fires). Every background feature is **off on every network**
until an admin turns it on, on **Settings › Installation › AI**, after reading what it is
expected to cost. Turning it on, turning it off and changing its caps are all there; nothing
here contacts a device, and nothing here calls the provider.

![Turning a background AI feature on for one network. Turn on shows the estimate, labelled as one, with its digest; you type the day and month caps and accept it. Mercury checks you are a verified person and the caps are within the installation's day cap, measures the estimate again and refuses if it moved, then writes the switch with who, when, the estimate and the caps, and records the decision. The gateway reads the switch at every call; Turn off removes it and the next call is refused. No provider call is made.](diagrams/ai-background.svg)

Who may: a verified person. Mercury holds no roles yet, so every verified person is an admin
here; a service, or a request whose identity is not verified, is refused by name, whatever
the installation's `configure` settings allow a service. One network never inherits another's
switch: turning a feature on for one network leaves it off everywhere else.

## Turn on {#turn-on}

**Turn on…** opens the feature's estimate in place of its row. Nothing is turned on until you
press **Turn on with this estimate** (or **Turn on with no measured estimate**, when Mercury has
nothing to measure).

1. `estimate`: the estimate is shown, labelled as one, with its digest (the short code after
   "Estimate"). Read: how often the feature's trigger fired on this network (for the SDN
   classify, the network's SDN detections in its alert history over the last 30 days), and
   the record of AI calls (the mean cost of this task's sent calls on its pinned model in the
   last 30 days). Sent: nothing. Recorded: nothing. **Calls a day** is the trigger's measured
   frequency times the calls one finding makes; **unknown** when the trigger has never fired
   on this network, never guessed. **Cost per call** is measured when calls were sent, else
   the task's per-call cap, the most one call can cost, said as not measured. **Dollars** a
   day and a month (30 days) follow, or are unknown, and then the caps you type are the bound.
   Prices come from Mercury's dated table; the provider bills.
2. `check`: you are a verified person, you ticked "I have read the estimate", and the caps are
   positive amounts in US dollars with the day cap within the installation's day cap. Read:
   the installation's day cap. Sent: nothing. Recorded: nothing. A cap you type may be written
   `0.50` or `$0.50`. A refusal names what it compared (a $8.00 day cap against the
   installation's $5.00, for example) and nothing is changed.
3. `compare`: the estimate is measured again and its digest compared with the one you were
   shown. Read: the same two records. Sent: nothing. Recorded: nothing. If it moved (the
   trigger fired again, or a call was sent, since you opened the form) nothing is turned on:
   both digests are named and the estimate now is drawn, to read and accept again.
4. `write`: the switch is written for this network: on, who you are, how that was
   established, when, the estimate you accepted with its figures, and the caps. Read: the
   switches, under the settings lock, so two admins never write over each other. Sent:
   nothing. The gateway reads the switch at every call, so the feature's next finding is
   classified.
5. `record`: the decision is appended to the installation's settings record. Read: nothing.
   Sent: nothing. Recorded: who, how that was established, when, the network, the feature, the
   estimate shown and the caps. **History** draws it under the kind **Installation
   settings**. If the record could not be written the section says so; the switch is on
   either way.

**An approval lasts 14 days.** On the fifteenth day the switch reads as off everywhere: the
gateway refuses the feature's next call, naming when its approval ended, and the row says
**approval ended**. Turning it on again is a new approval, after a new estimate. Changing the
caps never extends one. From 3 days before the end, Mercury asks for it: the row offers **Turn
on again…** (the same steps as Turn on…, from the current estimate; accepting it starts a new
14 days from then), and Needs attention raises a row naming the feature, the network and when
the approval ends. That row reads only the switches, never the record of AI calls; it turns
critical once the approval has ended, and clears only when an admin turns the feature on
again or off.

## Turn off {#turn-off}

**Turn off** is one press, with no confirm: turning a feature off spends nothing. The switch is
removed for that network and the next call is refused at once, in every worker; a call already
sent finishes and is recorded. It is recorded in the installation's settings record with who
turned it on and when. Pressing it on a feature that is already off writes nothing and says
so. On a feature whose approval ended, Turn off removes the ended switch.

## Change caps {#caps}

**Change caps…** opens the day and month caps of a feature that is on. Each is a positive
amount in US dollars; the day cap is within the installation's day cap. **Save caps** (a
verified person's) saves them and records the old and new caps; **Cancel** closes the form
with nothing changed. Raising a cap is how a feature stopped by its cap runs again before its day or
month ends; **Mercury never raises a cap by itself**. A feature that reaches a cap stops until
the day or month ends, and Needs attention raises a row (at 50% and 80% too, and when the
feature runs at 150% or more of the estimate it was approved at). Each of its
calls is judged by its spend so far, plus the worst case its calls still in flight on this
network have reserved, plus this call's worst case, so several calls at once never pass its
caps together (see [The day cap](installation-settings#ai-cap)).
