# Reveal a log line

Every log line {{product}} shows is masked: a password, a secret, an SNMP community or a key in
the line is drawn as a placeholder such as `<redacted:snmp_community>`, and the placeholder is
marked. In History › Query's logs builder, a line with a masked value offers **Reveal…**: it
shows you that one line unmasked, once you have said why, and records that you did. It reads
the network's log store; it changes nothing on any device and writes nothing but its record.

![Revealing a log line: a verified person gives a reason; the line is named by its Loki stream, its time and a digest of the masked line shown; it is read from Loki again, now; the reveal is recorded with who, when, which line and the reason, never the value; then the line is drawn unmasked under its row to that person, and History lists the record.](diagrams/reveal-log-line.svg)

## Where to open it {#open}

**History › Query › Ask your own › Logs**, Show **Lines**, Ask: each line holding a masked
value has **Reveal…** at the end of its row. It opens a box asking why you need to see it, with
**Reveal** and **Cancel**. A line with nothing masked has no Reveal…: there is nothing to show.

## The steps {#steps}

1. `person`: only a verified person sees an unmasked line. A service is refused whatever it is
   allowed elsewhere, and so is a request no one is identified behind; the refusal names what
   the request was. Read: nothing. Sent: nothing. Recorded: nothing.
2. `reason`: you say why, in at least three words and eight characters (the shape every
   recorded reason in {{product}} has; its quality is never judged), at most 300 characters.
   A reason too short is refused, saying how many words and characters it had.
3. `line`: the line is named by what the page drew, and nothing else: its Loki stream (the
   labels, as drawn), its time to the nanosecond, and the sha256 of the masked line you saw.
   The line itself never travels from the page.
4. `read`: the line is read from Loki again, now, never kept from the answer the page drew:
   Loki's indexed labels over that second select the stream, and the one line at that
   nanosecond whose masked form is the one you saw is taken. If Loki no longer holds it (it
   passed Loki's retention), if two different lines mask to the same, or if nothing in it is
   masked, nothing is shown and the refusal says which. Loki is waited for at most its own
   query timeout and 5 s.
5. `record`: the reveal is recorded BEFORE anything is shown, in the reveal record every
   reveal in {{product}} writes: who (with how they were verified), when, the network, which
   line by its stream and time, the sha256 of the masked line and your reason, each masked
   again at rest. Never the line and never the value: a record that copied the secret would be
   a second place it lives. If the record cannot be written, nothing is shown: a line is never
   revealed unrecorded.
6. `show`: the line, unmasked, is drawn under its masked form in your page only, in the
   answer to your own request, saying it was revealed to you and recorded. {{product}} keeps
   it nowhere, and nothing else on the page changes. Close the page or ask again and it is
   masked again.

## Afterwards {#afterwards}

The History **Timeline** lists each reveal under **Log lines revealed** (in Decisions and
records): who, when, the device, the line's stream and time and the reason; a device's History
tab lists the reveals of its lines. The Timeline redraws when a reveal is recorded. To see the
same line again, reveal it again: each reveal is its own record.
