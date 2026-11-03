# The assistant: how to do something, from the manual

The top bar's **AI Assistant**, after the AI chip, opens a panel on the right, in the help panel's
place. Ask how to do something in {{product}}, in your own words, and press **Ask**. The answer
is the steps, from this manual, each resting on a section it links to. It is labelled
**Advisory (beta)**: a person should confirm it. Esc or **Close the assistant** (✕) closes the
panel; it and the help panel take the same place, one at a time.

![The toolbar assistant's answer. You ask how to do something; Mercury chooses the manual's passages for the question by code (keyword ranking with the aliases and the boost for the screen you are on; below the floor, the manual's gap, and no call); it sends one recorded, capped call through the AI gateway, the instructions and the screens cached, then your question masked and the passages; it checks that every citation is a passage it sent and every screen named exists; and it draws the answer with its passages' links, or says the manual does not cover it and records the gap. Nothing changes anywhere.](diagrams/assistant.svg)

**It never changes anything.** It answers how to do a thing, and where; it never changes,
deploys, approves or saves anything, writes nothing to any source of truth, and names no
command to type into a device. For a fact about your network use **Ask in words** (History ›
Query); to change a device, **Change it in words** on its Intent tab.

## How an answer is made {#answer}

1. `choose`: the manual's passages are chosen for your question by code, never by the model:
   a keyword ranking (BM25) over the manual's sections, a long section split into passages
   that keep its link; a maintained list of the words people use for what the manual says
   otherwise (host key and re-key, password and secret reference, reboot and reload); and a
   boost for the page of the screen you asked from. At most 8 passages are sent. Below a floor
   (no passage scores enough, or the best meets too little of your question) nothing is sent:
   the answer is **The manual doesn't cover this.** and no call is made. The ranking reads
   your question with any secret masked out, so a pasted value never ranks the manual.
2. `ask`: one recorded, capped call through {{product}}'s AI gateway, as you (trigger
   person): the instructions and the list of screens first, the same on every question and
   cached, then your question and the passages. Your question is masked before it leaves: a
   value in a secret's place, and any credential {{product}} holds wherever it appears. The
   answer says what was masked, by its kind and never its value.
3. `check`: {{product}} checks the answer before it is drawn: every section it cites is one
   it was sent, and every screen it names is one this manual names. An answer that fails is
   never drawn: **Couldn't answer:** says why, and the call is in History.
4. `draw`: the answer is drawn with its passages' links (**From:**), each opening its section
   of this manual. When the passages do not cover your question, it says **The manual doesn't
   cover this.**, names the nearest sections it holds, and records the question as a gap in the
   manual. **Was this right?** under the answer records whether it was.

## A gap in the manual {#gaps}

A question the manual does not answer is recorded, masked, with the screen it was asked from
and who asked: for whoever keeps the manual. It is never a Needs attention row: nobody must act
on it now.

## The call {#call}

It makes one call to a hosted model (Anthropic's), through {{product}}'s AI gateway, as you:
allowed only once hosted AI is allowed on **Settings › Installation › AI (hosted)**, capped,
and recorded with who asked. When hosted AI cannot answer, **Ask** is disabled and the panel
says why; the manual stays yours to read under **Help**.
