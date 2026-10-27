# Settings › AI

**Settings › Installation › AI** is where an admin decides which AI features may run with no
person pressing them, on which network, and within what caps. Open it from Settings, then
Installation, then the **AI** tab. It shows one network at a time; choose another under
**Network**.

## Hosted AI {#hosted-ai}

The first card says whether hosted AI is allowed for the installation, by whom, when and why,
and the installation's day cap. While hosted AI is off, no AI call runs, background or
pressed, whatever the switches below say. The master switch, the provider key, the day cap and
each task's model and prices are set on **Settings › Installation › Connections**, on the **AI
(hosted)** card, which the card links to.

## Background features {#background-features}

Each background feature Mercury knows is a row:

- **The feature and its state.** **off** (never turned on, or turned off); **on**, with who
  turned it on, when, and the date its approval ends (an approval lasts 14 days); **stopped by
  its day cap** or **month cap**, with when, until that day or month ends or an admin raises
  the cap; **approval ended**, when its 14 days have passed and its calls are refused until an
  admin turns it on again.
- **Trigger:** what makes it call the model, and how many calls one finding makes. The SDN
  classify calls once for each detection a rule fires.
- **Caps:** its own day and month caps on this network, with today's and this month's spend
  and their share of each cap.
- **Estimate against actual:** the estimate accepted when it was turned on, a day's dollars,
  beside the average day's actual spend over the complete days since (up to 30).
- **Its controls:** **Turn on…** when it is off (the estimate opens in the row), **Change
  caps…** and **Turn off** when it is on. Each answer is drawn in the section, and a refusal
  names what it compared.

A feature on another network that its cap stopped is named under the list, so an admin sees it
without choosing that network.

What each action does, step by step: [Turn a background AI feature on or off](ai-background).

If the record of AI calls cannot be read, the section says so, each feature's spend is
unknown, and the gateway refuses every background call until it can be read.

## Not here yet {#not-here-yet}

The board for this tab draws more than is built. Still to come: the master switch, key and day
cap moved here from the Connections tab's card; one switch for each feature a person presses
(Explain, Ask in words, Change intent in words); who sees amounts, per network; the first
install's steps; and a Needs attention row three days before an approval ends.
