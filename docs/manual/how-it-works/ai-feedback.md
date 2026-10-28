# Was this right? on an AI answer, and the review of answers said wrong

Under every answer the model gave that {{product}} draws (Explain on an alert, Ask in words on
the metrics and the logs builder, an intent change in words, and the AI's classification of an
SDN detection) is one question: **Was this right?** You answer **Yes**, or **No…** with what was
wrong. A No is a candidate recorded case: a reviewer reads it on **Settings › Installation ›
AI**, under **Answers said wrong**, and accepts it into a case draft or dismisses it.

![Was this right? under an AI answer. You press Yes, or No with what was wrong and a sentence. Mercury checks you are a verified person, reads the call from the record of AI calls, refuses a second answer from you on the same call, and keeps your verdict with the call's id and hashes, your words masked. A No waits on Settings, Answers said wrong, until a reviewer accepts it into a case draft or dismisses it with a reason. No model call is made.](diagrams/ai-feedback.svg)

**Its effect on Mercury's checks: stricter only.** It adds cases and loosens nothing: a Yes
changes nothing but a count; a No changes nothing until it is reviewed; an accepted draft
becomes one more case the feature must pass, once a maintainer writes its expected answer; a
dismissal removes nothing. Nothing here changes an answer, a check, the caps or a case already
recorded. **No model call is made**: nothing is sent to the provider, and nothing counts against
the AI caps.

Who may: a verified person. A service, or a request whose identity is not verified, is refused
by name, and the buttons are drawn disabled with the reason. One answer per person per call.

## Was this right? {#answer}

The control is drawn under the answer, after its link to the call in History. It is not drawn
where nothing the model said is shown: an answer Mercury's check refused, Mercury answering by
itself with no call, or a question back. A background answer (the SDN loop's classification)
carries it too: whoever reads it judges it.

**Yes** records at once. **No…** opens a short form in place: what was wrong (the conclusion is
wrong; it missed something that matters; it cites the wrong evidence, or none; right, but not
useful) and, in a sentence of at most 300 characters, what the right answer would have said.
**Record as wrong** records it. Each button reads "Recording…" until the answer is drawn.

1. `person`: only a verified person's press is recorded. Read: who you are, from the access
   proxy's verified assertion. Sent: nothing. Recorded: nothing. A refusal names what the
   request is (not verified, or a service).
2. `call`: the call is read from the record of AI calls. Read: that record. Sent: nothing. A
   call it does not hold, or one with no answer, is refused by name. A press that joined
   another person's identical call is judged as that call.
3. `once`: under the store's lock, whether you already answered this call. Read: the answers
   said right or wrong. A second answer is refused, naming what you said and when; a reload or
   another tab shows what you said in place of the buttons.
4. `keep`: your verdict is kept. Recorded: the call's id, its task, model and prompt version,
   what it was about, the sha256 of the request as it left the host and of the answer as
   received (as the record of AI calls holds them, masked), what was wrong, your sentence
   masked like every record, who you are, how that was established, and when. Never the
   request or the answer themselves, which stay the call's. Sent: nothing; the sentence never
   reaches a model.
5. `review`: a No waits under **Answers said wrong** until it is reviewed (below).

If the record cannot be read, nothing is recorded and the control says why ("Couldn't
record"); the buttons stay, to press again.

## The review {#review}

**Settings › Installation › AI** has the card **Answers said wrong**. It leads with the counts
(to review, accepted as case drafts, dismissed, said right), then a filter by status and by
feature, and a search over the call's id, the person and the words. Rows are newest first,
fifty at a time with **Older…** beneath, each collapsed to its feature, who, when, what was
wrong and its status. Opening a row reads its call then: the call's id, model, prompt and who
asked it, a link to it in History, what was asked (the request's sha256 and its subject), the
answer as received (masked, folded), what was wrong, and what others said of the same call.

Every verified person is a reviewer until Mercury holds roles.

- **Accept into a case draft…** shows the draft {{product}} made from the call and the words:
  the call's id, task, model and prompt, its subject, the two hashes, the words as the case's
  `flag`, and `expect` left empty. **Accept** records your review bound to the draft's hash: if
  the draft changed since it was drawn, nothing is recorded and both hashes are named. It is
  off, with the reason, while the call cannot be read. The draft never holds who said it,
  because a case file is published with the repository.
- **Dismiss…** records why it is not a case, a few words at least, with your name.

A row another reviewer settled first is refused in place, naming who settled it and how. An
accepted row shows the draft with **Copy the draft**, and a download of every accepted draft of
its feature as JSON. {{product}} writes no case file: a maintainer adds a draft to the feature's
case file with its `expect` written, and it is then judged in CI like every case. A blind
held-out set is never drawn from these.
