# Settings › AI

**Settings › Installation › AI** is where an admin decides which AI features may run with no
person pressing them, on which network, and within what caps. Open it from Settings, then
Installation, then the **AI** tab. It shows one network at a time; choose another under
**Network**.

## Hosted AI {#hosted-ai}

The first card, **AI (hosted)**, holds every installation-wide AI decision: the provider key
(**Replace…**, and **Test**, one small recorded call), the installation's day cap and when its
day begins (**Save**), whether hosted AI is allowed (**Allow** with a reason, or **Turn off**,
by whom, when and why), today's spend against the day cap, and each task's model, prices and
cap per call. While hosted AI is off, no AI call runs, background or pressed, whatever the
switches below say. Every background feature's caps are within the day cap. The card moved
here from the Connections tab, which keeps one line linking to it. What its actions do, step
by step: [AI (hosted)](installation-settings#ai) and [The day cap](installation-settings#ai-cap).

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
- **Its approval's end.** From 3 days before an approval ends, the row says so and offers
  **Turn on again…**: the current estimate opens in the row, and accepting it approves the
  feature for another 14 days from then (its caps typed again, recorded as a turn-on). Needs
  attention raises a row for it at the same time
  ([Needs attention](needs-attention#sources)); it stays, saying the approval ended, until
  the feature is turned on again or off.

A feature on another network that its cap stopped is named under the list, so an admin sees it
without choosing that network.

What each action does, step by step: [Turn a background AI feature on or off](ai-background).

Every page's top bar shows the same spend: the AI chip, and the spend panel it opens, list each
feature on with its spend and **Turn off**, the same action as here
([What AI is spending](getting-started#ai-spend)). Turning one on is only here.

If the record of AI calls cannot be read, the section says so, each feature's spend is
unknown, and the gateway refuses every background call until it can be read.

## Answers said wrong {#answers-said-wrong}

The last card reviews every **No** a person gave under an AI answer (**Was this right?**). It
leads with the counts (to review, accepted as case drafts, dismissed, said right); filter by
status and by feature, or search a call's id, a person or their words. Each row is collapsed to
its feature, who, when, what was wrong and its status; open it to read the call, the answer as
received (masked), what was wrong and what others said of the same call, then **Accept into a
case draft…** or **Dismiss…**. Nothing here calls a model or changes an answer or a check.

What each action does, step by step: [Was this right? and the review](ai-feedback#review).

## Not here yet {#not-here-yet}

The board for this tab draws more than is built. Still to come: one switch for each feature a
person presses
(Explain, Ask in words, Change intent in words); who sees amounts, per network; and the first
install's steps.
