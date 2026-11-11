# SDN

A network's SDN controllers and the flow tables of the switches they manage, under OBSERVE.
The sidebar's SDN opens it for the network you are on (`/v2/sdn?list=<network>`). Its tabs are
**Controllers**, **Flows**, **Apps** (the apps each controller runs, deployed by Mercury),
**Policies** (a policy in words, checked and confirmed: [SDN › Policies](sdn-policies)) and
**Responses** (what awaits you, HITL or AUTO, the loop and the detection rules).

The connections are the network's own, set in Settings › Integrations' SDN controllers card
([Settings](settings#sdn-controllers)): a network never takes Default's controllers. With none
set the page says so, "No SDN controller is connected to this network. Add one in Settings ›
Integrations.", with the link, and draws nothing else.

## How it is read {#read}

Mercury's SDN reader reads each network's controllers every 30 seconds, and the page is drawn
from what it kept, never by asking a controller while you look; it redraws by itself when a
read finishes. While a card you opened in place is on the page (a response's or a flow's
preview, its result or refusal, the flow editor), or you are typing (a dismissal's reason), the
redraw waits: the card says **Paused while you review this: newer data is waiting.** with
**Show it now**, which closes the card and redraws (nothing is sent); a typed field's redraw
happens when you send or empty it. When Mercury refuses one of the page's controls (Classify,
a dismissal, Turn AUTO on or off, the loop's Start or Stop), the refusal is drawn under that
control ("Not saved: " and why), and the page keeps redrawing by itself; its next redraw shows
the state that refused it.

**When the page is not current.** A page that is live is redrawn at every read, so every 30
seconds at least. If no redraw has reached the page within 90 seconds of when it was drawn (the
reader's promise: three of its reads), or the page's live connection has stopped, gone silent
or could not connect, an amber note under the tabs says so: **Last updated** with the drawing's
age (its UTC time on hover), why ("no update has arrived in the 90 s it promises", or "live
updates stopped"), "so this page may be out of date", and **Reload**, which loads the tab again
as it is now (Flows keeps its filter). A frozen page is never shown as current; while the page
is current the note is not there. While a card you opened in place holds the redraw, the note
offers no Reload, because a reload would close that card: it says "a reload would close the
card open below. Send or close it first.", or "newer data is waiting, held for the card open
below" when a redraw already arrived; once the card is sent or closed, the page redraws or
Reload is offered. Each time the note appears, the page records the stall on History (**Page
stalls**: the page, its tab, its live connection's state and Mercury's view of it), so why a
page stopped updating can be read afterwards; you need not catch it as it happens.

For each connection the reader asks its driver for the controller's switches;
for each switch, its flow table, its port counters twice a second apart, what the switch says
it is (its own name, the one Mininet gives it), and its meters and meter features where the
driver reads meters. It then decides whose each flow is, by its cookie (see
[Flows](#flows)). A controller that does not answer keeps what it last read, drawn with that
read's time. A connection saved a moment ago is drawn at once as **not read yet**.

Where the driver reads topology (**read topology** among a card's capabilities), the reader also
asks the controller for its topology: its switches with their ports, the links it discovered
between them, and the hosts it learned. That read draws the switches, their links and hosts on
[Topology](topology#controller), with the controller's own symbol, and puts the hosts in the
endpoint layer. Ryu serves it only with `ryu.app.rest_topology` loaded and `--observe-links`
given; without the application, its topology is said as "the topology app is not running",
and the rest of the controller is read as before. A topology that cannot be read keeps its last
read, with that read's time.

The 30 seconds come from the lab's controller application, which removes an idle flow after 30
seconds: a read every 30 seconds sees each flow at least once.

## Controllers {#controllers}

- **The summary**: how many controllers, how many connected and not answering, how many
  switches, and how old the read is (its time on hover).
- **A card per connection**, its state beside its name: **connected**, **partly read** (some of
  its switches could not be read whole, each named), **not answering**, **driver not built** or
  **not read yet**. A connected card lists:
  - **Driver**, and its status (built; later; unmaintained);
  - **Northbound**, the URL Mercury reads, and whether TLS is used and verified;
  - **Southbound**, where its switches connect: informational, never dialled;
  - **Version**, or "not reported" with why (Ryu's `ofctl_rest` reports none);
  - **Cluster role**: not reported; no driver built yet reads one;
  - **Switches**: how many are connected, each by its datapath id, a link to its flows on
    Flows; they are discovered through the controller and not adopted as devices;
  - **Can**: what the driver declares (read flows, port statistics and meters; write flows and
    meters; delete flows), and what it does not offer (Ryu's reads no topology);
  - **Controller's own flows**: the cookies the connection declares as its application's;
  - **Last read**: when, and what (flows, port statistics and meters of N switches, how many
    failed).
- **Not answering** says since when, what failed and how many reads in a row, and that its
  switches' flows are as last read. **Needs attention has a red row for the network too**, so
  you need not have this tab open: one per network, naming each controller not answering, its
  URL, the failure, since when and how many reads in a row, and the read its switches are drawn
  from; while it lasts the closed loop finds no threat on those switches. Its action is to
  check the controller answers, read its error here, and correct its connection in Settings if
  it moved. It clears at the first read that finds every controller named answering (the
  reader reads every 30 seconds). A network with no controller set has no such row.
- **Test connection** asks the controller now, with what is saved, and answers in place:
  "Answered: N switches connected" or "Couldn't connect: <the reason>" (see
  [Test connection](#test-connection)).
- **Edit connection** opens Settings › Integrations, where the connection is changed.

## Test connection {#test-connection}

**Test connection** on a controller's card, or on its row in Settings, asks that controller
now through its driver, with what is saved, its stored credential among it. It reads the
switch list and the version, and answers beside the button. It changes nothing: the card's
state stays the reader's last read until its next one. A failure is said in the driver's
words: a refused credential, a controller that did not answer within its timeout, an address
nothing listens on.

## Flows {#flows}

Each switch's flow table, Mercury's expected flows beside what is installed.

- **The summary**, for every switch whatever you filter: how many switches and flows, how many
  are Mercury's, how many the controller's own, how many unauthorised, how many of Mercury's
  are missing, and how many meters, with the controllers read and the read's age.
- **The granularity note**, once per switch where it limits what can be seen: a switch whose
  flows match only Ethernet fields and the switch port (L2), or IP addresses and no transport
  port (L3), cannot show a port scan as distinct destination ports; a port's high packet rate
  there is **High packet rate**, at lower confidence, watched and never called a scan.
- **Analyse this network**, above the filter (an AI control): one recorded, capped AI call that
  reports what is abnormal in the network's latest collected snapshot, each finding with its
  severity, why and the evidence ids it cites, checked against the snapshot before it is shown
  (a finding citing nothing the snapshot holds is dropped, and the card says how many were).
  Beside it, the snapshot's size and time, the model and about what a call costs, and
  **Collect now**, which reads the switches again as a job. Under them, the latest snapshot's
  id as text with **Copy**, when it was collected (UTC) and what it holds, and **Kept
  snapshots**, which lists every snapshot kept when you open it: its id, time, switches,
  flows and whether its seal holds ([Collect now](sdn-analyse#collect)). **Planted issues** is the sheet
  that compares the findings with problems you planted, each **found** or **missed** with your
  why, or **planted after this analysis** (neither, and outside the counts) when it was
  planted after the analysis was made. Each row's **Edit…** corrects its name and evidence
  (**Save changes**), and **Remove…** takes it off the sheet (**Remove from the sheet**),
  keeping its record; **Changes to the sheet** lists who changed what, and when. **Download
  the sheet** gives it as Markdown or CSV. Under the findings, **Check this answer again**
  makes no AI call: it reads the call's recorded answer again and checks it against the same
  snapshot, draws that result under the first one, and marks the sheet from it, saying so
  ([Check this answer again](sdn-analyse#recheck)). How it works: [Analyse this
  network](sdn-analyse).
- **Analyse with the trace tool**, its own card under those two (an AI control): the same
  question about the same snapshot, the model first asking Mercury for up to three reads (a
  packet trace through the flow tables, a switch's flows, its ports, a link's state), each
  checked and answered from the snapshot alone, then answering. Under its findings, **Tool
  calls** lists each read with what it returned; when both have answered the same snapshot, a
  table compares their findings, found, missed, false positives, calls and cost. Its own
  **Check this answer again** does the same for its answer, with no AI call. How it works:
  [Analyse with the trace tool](sdn-analyse-tools).
- **Trace a packet…**, beside the filter, opens Topology › Path… on this network with the Flow
  tables layer chosen and its form open: the trace has one home ([A flow-table
  trace](sdn-trace)).
- **The filter**: words matched against the switch, a flow's match, its actions or its cookie;
  **Show** applies it. **Hide the controller's own flows** is ticked by default.
- **The switches**, folded, one row each: its datapath id, its own name, its controller, and
  what is wrong (unauthorised flows, Mercury's flows not as recorded or missing, a switch not
  read whole, a controller not answering) or **as expected**. A switch with something wrong is
  open; the rest open on a click, and stay open when the page redraws.
- **A switch's flows**: owner, priority, match, actions, packets, timeouts (a hard timeout
  with the seconds it has left) and cookie, what is wrong first.
- **Whose a flow is**, decided by its cookie, in code (no AI):
  - **Mercury's**: its cookie is in Mercury's range and recorded for this connection, and the
    switch, table, priority, match and actions are the record's; **Mercury's, not as
    recorded** names each difference;
  - **the controller's own**: its cookie is one the connection declares as its application's;
  - **unauthorised**: anything else, named with why (an unknown cookie; Mercury's range with no
    record; a record withdrawn; another connection's record). It is drawn red, with
    **Remove…** ([Add, edit and remove a flow](#flow-operations)).
  - **Mercury's, missing**: recorded and not installed. **Mercury's, expired**: its hard
    timeout, as set, has passed, so the switch removed it as asked: nothing to do.
- **Not in force**, at the top of a switch: a response whose flows or meter the switch no
  longer holds while its hard timeout has time left, as after a switch restart. The line names
  the response, what is missing, and the time left. **Re-apply…** previews putting back
  exactly what is missing, for the time its hard timeout has left; nothing is sent until you
  confirm. The same response is a row on Needs attention until the reader finds it installed
  again, its hard timeout passes, or a newer response answers the same threat on that switch.
  How it works: [Re-apply a lost response](sdn-flows#reapply).
- **Answered**, in the same place: a lost response whose threat a newer response of Mercury's
  already answers on that switch (its detection fired again and was answered as new). The line
  names the lost response and what is missing, then the newer response (its id and, when it
  differs, its operation; its action and source; and the time it is in force until), and says
  there is nothing to re-apply: there is no Re-apply…. It is judged as Needs attention judges
  it, from the same SDN read the page draws: the same rule, the same switch, the same source or
  the same detection, and every flow and the meter of the newer response in place as last
  read. A newer response for another source, rule or switch, one not in force itself, or a
  controller that has not answered since (its read is then carried, so nothing on it is known
  to be in force) leaves the line **Not in force** with Re-apply…. A page drawn before the newer
  response was applied still shows Re-apply… until it redraws; pressed, it is refused, naming
  that response, and nothing is sent.
- **Meters**: each switch's meters (its id, its rate and what happens above it, the packets
  counted in that band) and whose each is, by the flows that use it; and on how many switches
  meters are supported, from each switch's meter features.

## Add, edit and remove a flow {#flow-operations}

Each switch on Flows has **Add flow…**; each flow has **Remove…**, and each of Mercury's flows
**Edit…**. Each opens its form in place:

- **Add**: the table, the priority, the idle and hard timeouts, the match as `field=value` pairs
  (OpenFlow 1.3's names: `in_port`, `eth_type`, `ipv4_src`, `ipv6_dst`, `ip_proto`, `tcp_dst`…)
  and the actions (`drop`, or `output:<port>`, `meter:<id>`, `group:<id>`, `goto_table:<id>`,
  `set_field:<field>=<value>`). Mercury sets the cookie.
- **Edit**: the same form for one of Mercury's flows. New actions change it in place; a new
  match, priority or timeout is a remove and an add as one action, and the preview says so.
- **Remove**: the flow named by its table, priority, match and cookie, removed by delete-strict.

**Preview** reads the switch now and draws the card: what it does, exactly these requests, what
will not happen, any warning (the table-miss flow, a flow of the controller's own), and Verify.
**Send** confirms it, bound to the requests' hash; the result replaces the card: **Done,
verified**, or **Rolled back** naming the check that failed. A match missing a field it needs is
refused at the preview, naming both. How each step works:
[Change an SDN switch's flows](sdn-flows).

## Apps {#apps}

The apps the network's controller runs (Ryu apps such as `of_versions`, `switch_quirks` and
`dns_blacklist`), deployed by Mercury from the network's code repository. Each deploy restarts
the controller, so every switch drops and reconnects. How a deploy works, step by step:
[Deploy apps to an SDN controller](controller-app-deploy).

- **The NSOT export card** comes first: the committed export the tab reads its controller hosts
  and every deploy's expected switches and links from (its hash, its commit, who and when,
  NetBox's version and what it holds), or that none is committed. **Export from NetBox…**
  reads NetBox now and opens the preview in the card's place: the export's hash beside the
  committed one and what changes, by kind; **Commit the export** commits it as you, bound to
  that hash. Step by step: [Commit a network's NSOT export](nsot-export).
- **Add an app as a Draft…** comes next: choose an app's folder (its `manifest.yml` at its
  top, the folder's name the app's), and Mercury previews the one commit that adds it as
  `apps/<name>/` to the network's code repository: the branch's commit it goes on top of, each
  file with its size and hash, the message and you as its author. **Add <name> as a Draft**
  commits and pushes it as you, bound to that preview, then fetches the repository, so the new
  version is listed as a Draft with **Run its tests** and **Review and publish…**. It only ever
  adds a new folder, and only to a code repository at a local path: an https location, or a
  folder already in the repository, is refused naming why. Step by step: [Add an app to the code
  repository as a Draft](draft-write).
- **DHCP steering** (on a network whose devices are NetBox's) names the DHCP server as the
  committed NSOT export holds it (the router carrying the NetBox Service `dhcp`, its address,
  its MAC and the switch port it is on, and whether the NSOT's protected dhcp classes name this
  feature as their owner), what the flows do (each host's DHCP broadcast unicast to the
  server's MAC from the edge port it enters, a server reply dropped on every port but the
  server's), that **DHCPv6 (UDP 546 and 547) is not steered: it floods as before**, and the
  requests steered and replies dropped, counted from the SDN reader's last read of the flows.
  **Edit settings…** chooses every edge switch or some; **Preview steering…** compiles the
  flows and reads each switch's table, listing every request with its REST body; **Steer DHCP
  on <N> switch(es)** sends them as you, bound to that preview. While steering can't be
  compiled (no committed NSOT export, one that can't be read, or one that does not compile),
  the card says why and what to do, and **Preview steering…** is greyed with that reason until
  it compiles. **Remove steering…** previews
  removing exactly the flows it recorded, and **Remove <N> steering flow(s)** removes them. Step by
  step: [Steer DHCP to the network's server](dhcp-steering).
- **No app version can be listed** says why (no code repository set, not fetched yet, or the
  setting changed since the last fetch), with **Open the code repository's card**, where its
  location is set and **Fetch now** registers each app folder at the fetched commit (see
  [A network's code repository](code-repository)). App folders a fetch could not register are
  named with why.
- **The controller card** leads: its name and whether it runs **Mercury's record** (the last
  deploy whose outcome left it running a request Mercury recorded), **differs from Mercury's
  record**, or **can't tell** (its unit's command line could not be read; never drawn as
  matching). Under it: the unit and where it listens (NetBox's `openflow` Service), the
  **Last deploy** with its outcome, who and when, and **its receipt**; what a miss **rolls
  back to** (what it runs by Mercury's record, or with none the drop-in before, which the apply
  script keeps); the host, with **Open its device page**.
- **Preview a deploy…** reads the controller now and opens the plan of the set it runs by
  Mercury's record (with nothing changed, a plan that changes nothing, and its redeploy). It is
  disabled, its reason on hover, while Mercury holds no record for it: choose an app's version
  on its page first.
- **Drift**: when what systemd holds for the unit differs from Mercury's record, the card draws
  a table naming each side (each app's version, the User, the drop-in) and **Preview the
  redeploy…**. It reads what systemd holds, not the running process's own command line, so a
  unit changed and not yet restarted reads as changed. To keep what the controller runs
  instead, deploy that version from its app's page: the deploy makes it the record.
- **The apps** are grouped by what to do: **/health failing**, **Differs from Mercury's
  record**, **A newer Published version**, **Running as recorded**, and **Registered, not in
  the set**. Each row names the version running and its place in the load order, the newest
  Published version and its reviewer (a newer Draft beside it), the OpenFlow versions it
  declares and its /health as last read. A row opens its app's page.
- **An app's page** lists its versions as registered (each pinned by commit and content
  hash): a **Published** one by its reviewer, a **Draft** with why it is never offered (it
  deploys only in the container harness), a **Retired** one kept for audit. Choosing a version
  enables "Preview deploying <version>…", the plan of the record's set with that one change;
  the version the controller runs is disabled, its reason on hover. Beside it: what the chosen
  version's manifest declares (controllers, OpenFlow versions, what it requires, its REST
  endpoints with the /health the post-check reads, the flows it owns, its egress, its config).
- **A receipt** (from **its receipt**, History, or a result's **Open the receipt**): who
  confirmed it and how they were verified, the plan's hash, the request and the one before, the
  files, the drop-in's before and after, the window, the apply script's outcome, the
  post-check, **Download the receipt (JSON)** and **Open the controller** (the controller's
  card). Every text is masked as History masks.
- **Not drawn yet**, each a registered gap: a controller's **Read again** (the card draws the
  newest preview's reads of the host), the code repository's **Fetch now** on this tab (it is
  on the code repository's card in Settings; where each fact comes from:
  [Deploy apps to an SDN controller](controller-app-deploy#sources)), Publish (every
  registered version is a Draft until it is published),
  **Compare** two versions and **Open the review**, and the Needs attention rows drawn from the
  controller's reads (an app's /health failing, a switch or link missing outside a window,
  drift). A deploy whose outcome is not known, or that left the controller not back as it
  was, is already a row (see
  [Deploy apps to an SDN controller](controller-app-deploy)).

## Responses {#responses}

What to act on first: **N awaiting approval**, how many incidents and on how many switches, the
mode and whether the loop is running.

- **Incidents awaiting a person**: one attack is one incident however many switches see it (a
  scan crosses every switch on the source's path, and each switch's rule fires). Detections of
  the same rule and source (IPv4, IPv6 or MAC, in any spelling) within the rule's own window
  (the scan's 60 seconds, the flood's 30, as set in the rules below) are one incident, with one
  AI classification and one response, proposed at the **ingress switch**: the switch where the
  controller's topology lists the source's host port, since a response where the source enters
  holds it off from every switch behind it. The others are **seen also**. An unauthorised flow
  is one flow on one switch, so each is its own incident. How it works:
  [Incidents](sdn-flows#incidents). The incidents are a compact table, most severe first
  (critical, high, not classified, medium, low, no threat), then the longest waiting: its
  severity, rule, source, how many switches saw it, its age, the AI's verdict and the action
  proposed at a switch. The severity counts above it filter the table, and the search finds an
  incident by its rule, source, any of its switches or its action; a filtered table says
  **Showing N of M** with **Show all**, and past 50 rows it says how many more a filter would
  show. **Click a row to open it**; everything you do there acts on that incident only, and
  nothing confirms or dismisses several incidents at once.
- **Watching: High packet rate**, above the incidents: a port receiving at least the High
  packet rate threshold (100 packets a second by default) on a switch whose flows name no
  transport ports. A rate alone cannot tell a scan from a flood's first seconds or other heavy
  traffic, so it is not called either: nothing is proposed and no AI call is made. Its row
  reads **Watching**, with **not asked** and **nothing: a rate alone names no threat**; opened,
  it says **Why it is not called a scan or a flood** and **What happens next**. Mercury closes
  it itself: when the flood rule fires for the same port or source, it joins that incident,
  whose row then reads **Flood · began as High packet rate** and says since when; when the
  rate falls below the threshold, it ends as "ended, never more than a rate". The same source
  on several switches is one row. You may dismiss it with a reason. It also watches what the
  flood rule holds but does not call a flood:
  - **a TCP transfer**, its data with its ACKs returning;
  - **one large-packet stream**, whose packets average more than the flood's size (200 B by
    default, `sdn_flood_max_mean_bytes`).

  A flood is a high packet rate of small packets. **A large-packet flood is left to you:** its
  row says so, and nothing is proposed by itself.

  **Rate-limit this source…** on that row makes the stream an incident awaiting you:
  - **What it proposes:** the flood rule's rate limit on the stream's source, at the
    catalogue's defaults (1,000 kbit/s, a burst of 100, the network's hard timeout). Its why
    names you, and its evidence is the watched detection's.
  - **What pressing it does:** it sends nothing and asks no AI. The watching row closes as
    proposed by a person, and the new incident opens.
  - **From there:** you preview the rate limit (its rate, unit, burst and timeout are yours to
    change), confirm it by its hash, and it is applied, verified and recorded as any response
    is.
  - **When it is disabled:** it is checked as the Flood rule's response under the network's
    response policy, since the stream is what the flood rule held. Where the policy does not
    allow `rate_limit_source` for floods, or the stream names no source to act on (a link
    port), the control is drawn disabled and says why.

  Large packets from two or more sources to one host are one attack on that host, and are
  called a flood. How it works: [High packet rate](sdn-flows#high-rate).
- **An incident, opened**: the detection (the rule, the source, the switch, its confidence
  and its words, an alert with its evidence pack; an unauthorised flow's words also say what it
  does, decided in code: it lifts or shadows a Mercury flow, drops, diverts, mirrors, copies
  to the controller (still delivering the traffic), forwards as the
  controller would, or has an effect the table cannot tell, naming why:
  [What an unauthorised flow does](sdn-flows#classify)), the AI's classification when there is one
  (marked AI: threat or not, its kind and severity, a severity the flow's effect raised in code
  saying so with the model's own rating and the floor's words on hover; its reasoning, what it
  recommends, the devices it names, the evidence ids it cites, and the model, cost and call),
  else who chose the
  action (the catalogue's default, chosen in code), and the action proposed from the catalogue
  with its risk and the switch it acts on. **Ingress:** names that switch and the port the
  controller lists the source's host on; when the ingress cannot be told (no source named, the
  topology not read now, no host or several ports listing the source, or the source on a switch
  that has not fired) the line reads **Proposed at:**, says why, and the switch that saw it
  first is proposed. **Source:** for a drop or a rate limit of a flood whose port's flows
  named no address, where the source came from: the
  one host the controller's topology lists on that port, named; with several hosts there, they
  are named and a **source** picker beside Preview lists exactly them (any other is refused);
  with none to act on (no host, no address to match, or the port a link to another switch),
  **No source to act on:** says why and there is no Preview; when the topology could not be read
  then, the preview looks the host up again
  ([Where a port's source comes from](sdn-flows#port-source)). The table's Source column reads
  **one of N** while you have a choice to make. **Seen also on N other switches** opens to each switch, its port, controller,
  time and detection; nothing is proposed there. **Classify** (an AI control, beside its mark) asks the model about this
  detection as you and redraws the card with its answer, its action proposed; it sends nothing
  to a switch, and is drawn disabled with the reason while AI cannot answer. How it works:
  [Classify a detection with AI](sdn-flows#classify).
  Its preview button, named for the action ("Preview the drop traffic from the source…"), builds its card as Flows' changes are (the action's parameters checked
  against the evidence: the source is the detection's, the hard timeout within the network's
  ceiling); **Send** applies it as you. **Dismiss with this reason** closes it, sending nothing
  (on an incident seen on several switches, **Dismiss the incident (N switches) with this
  reason**, which closes the incident with all its switches).
  An incident stays until you approve or dismiss it: when no switch shows it any longer, its row
  is marked **Inactive** and the opened incident says **Threat no longer active since** the
  collection that stopped showing it, its classification kept, and the line goes if it fires
  again. When the AI's answer was
  refused by the check (or no classification could be made), the card says so ("AI
  classification refused: why; proposed by the catalogue default") with **The refused answer
  in History**, and the rule's catalogue default awaits you, even in AUTO.
- **Mode**: **HITL**, a person confirms each response, is the default. **Turn AUTO on** takes a
  reason, how many hours (at most 24) and the allowed risk (low: rate-limit and drop; medium:
  also remove a flow). While AUTO is on the card names who turned it on, why and until when;
  **Turn AUTO off** ends it at once. At its expiry the mode is HITL again, and the record says so.
  The card says the network's stage in one line: "This network is marked lab.", or that it is
  not marked (or marked pilot or production) and that AUTO is turned on only on a network marked
  lab until the AUTO production-readiness gate is complete, with a link to the stage on
  [Settings › Integrations › SDN controllers](settings#sdn-controllers). On a network not marked
  lab, **Turn AUTO on** is drawn disabled with that reason, and Mercury refuses it anyway,
  naming the network's stage and the gate. When AUTO was on and the network has since been
  marked otherwise (or its stage cannot be read), the card says **AUTO is suspended**: nothing
  runs unattended and each response awaits you; it clears when you turn AUTO off or mark the
  network lab again. Even with AUTO on, a response whose source was inferred (named from the
  controller's topology, or to be chosen among a port's hosts) awaits you, its card saying "the
  source was inferred from the topology: a person confirms it": AUTO acts only on a source the
  flows themselves name ([Where a port's source comes from](sdn-flows#port-source)). A
  response AUTO decided to apply and could not preview awaits you too, nothing sent, its card
  saying "AUTO could not preview <action>: <why>"; so does one whose preview passed and whose
  confirm was then refused before anything was sent (the policy or the connection saved in
  between, the switch gone or its table changed, the switch held by another operation), its
  card saying "AUTO could not confirm <action>: <the refusal>". Preview it again and confirm
  it, or dismiss it with a reason.
- **The loop**: **Start** runs detect, classify and respond on this network every N seconds (5 to
  600), start to start: a pass that takes longer starts the next at once, and the log says so;
  classify is an AI call only where an admin turned its background feature on for this
  network (off by default; the screen that turns it on, Settings › AI, is not built yet), and
  otherwise the log says why none was made and the catalogue's default is proposed; its log
  lists each pass's steps, newest first; **Stop** ends it after its current pass,
  and the card says who stopped it and when. **A restart of Mercury stops the loop, and it does
  not start again by itself** (a loop that resumed unattended would make AI calls and, in AUTO,
  act with no one present): the stop is recorded as **stopped by the app's restart**, with its
  last line's time, and Needs attention shows a warning for the network until you press Start
  or 24 hours pass. **Incidents awaiting you are on Needs attention too**, so you need not have
  this tab open: one row per incident, never one per switch or per detection, naming its
  network, rule, source, how many switches saw it, its severity, its age and the switch its
  response is proposed at; it is red when classified high or critical, and clears once its
  response is applied or it is dismissed. Each **High packet rate** being watched is a warning
  there too, naming its network, switch, port and source, cleared when it joins a flood, ends
  or is dismissed; it is never escalated, since nothing awaits your approval. **An incident
  left unanswered is escalated**: once
  it has awaited you for the network's **SDN: escalate an unanswered incident after (minutes)**
  (15 unless set on the network's Settings, Network tab), its row turns red whatever its
  classification and says "unanswered for N minutes", counted on Mercury's clock from when
  its response was proposed. It stays the one row, and clears only as above. Mercury has no
  on-call integration (no paging, chat or webhook notifier), so nothing is sent anywhere: the
  row says so, and it is the only notice. A threshold that cannot be read is said on the row,
  which is then drawn escalated. **Open the incident** opens this tab with that incident open.
  What the log says:
  - a pass that finds nothing new says which of these it is: **network healthy: no threat
    detected** only when the collection read every switch whole and no detection is active;
    **no new threat; N still active**, naming each detection still firing; or that the
    collection was partial, or read no switch, which is never called healthy;
  - **a threat already answered** says it **fired again while mitigated by response <id>
    until <time>**: a response still in force holds its source off, so no card is raised, no AI
    call is made and nothing is sent ([how](sdn-flows#already-mitigated));
  - **an incident** seen on several switches says so in one line: the rule and source, how many
    switches, the window it was grouped within, the ingress (or why it cannot be told) and the
    switches seen also; a switch that sees an incident still awaiting you, within its window,
    **joins incident <id>**, with no AI call and nothing proposed;
  - **a response** (AUTO's, or yours when you send it) says who applied which action on which
    switch (its DPID, and the name it reports when Mercury knows one), the operation's id, and
    the resulting entries **as Verify read them back from the switch**: each flow's match,
    actions, priority, idle and hard timeouts and cookie; a rate limit's meter, its band, rate,
    unit and burst; a removed flow gone, and Mercury's flow put back. An entry Verify did not
    read back is said so, never shown from the request; a response rolled back or refused says
    that and why;
  - **where a detection's time went**: after each classified detection's response, a
    **timing** line names each stage and its seconds, in the order the pass ran them: detect
    (with its evidence pack's build), holds, incidents, queued (waiting for a free call when
    more than 10 are classified at once), classify (prepare; the gateway, with the provider's
    own count and send from the call's record and the rest, its checks, the caps and the
    record; the answer's check), waited (for slower calls and earlier responses), respond, and
    the total from detection to response, with the read before it. A pass's detections are
    classified at once, each its own call, so a slow stage is named on its own line.
- **The loop stops by itself.** **Start** takes **run for** (5, 20 or 60 minutes, 20 by
  default; a loop is never left running unattended, so an hour is the most), and the loop
  also stops after its **pass cap**, the passes its run-for holds at its interval and one
  more. While it runs, the card says **Stops by itself** at what time, after how many passes
  (and how many so far), or on Stop. When it ends itself its log says **stopped by itself**,
  naming which bound ended it and how many passes ran; start it again for another run. The
  five-minute demonstration is the 5-minute choice.
- **Link failures** ([how it works](#link-failure)): a card for each link the topology held
  that is down, with no AI call. **Verify the reroute** traces every pair of hosts over the
  controller's flow tables; **Dismiss with this reason** closes the card. Neither sends
  anything.
- **What each switch can do** ([the capability matrix](#capabilities)): each switch's
  OpenFlow version, tables, meters, fast-failover groups and rewrite, read from its own
  answers, and what a response does where it cannot. **Read again** reads them now.
- **A detection decided in code**: where the evidence settles it, a benign detection is
  answered **no threat** with no AI call, its card marked **Code** where an AI answer is
  marked **AI**. Two shapes are decided this way:
  - **a bulk TCP transfer**: its port's data one way and its ACKs the other, at most four TCP
    sessions, and under 90% of the port's link speed where that speed was read;
  - **sessions carrying data**: the source's flows each carry a session's packets, not a scan's
    probe.

  Nothing is proposed for AUTO; the rule's default is drawn for you to dismiss.
- **The loop's log** shows one run whole, from its start, in a box that scrolls: every pass's
  steps, newest first. **Run** chooses an earlier run, each named by its job id (the network and
  the time it started) and its start time in UTC, with its line count. **Download log** saves
  the run shown as plain text, every line oldest first under a header naming the network and the
  run, in a file named for the run's job id (for example, a lab's evidence of a 3-minute run). A
  run longer than 2,000 lines is drawn to its newest 2,000, and the box says how many of how
  many; the download has every line.
- **Detection rules**: each rule's threshold on this network (High packet rate's among them,
  which takes no response), the responses each rule may take (its default first), and the
  response timeouts: every response flow expires at its hard
  timeout. The responses are set under the table ([Response policy](#response-policy)).

Verify checks installation and counters; testing traffic between the hosts is yours.

## Link failures {#link-failure}

The **Link down** rule watches every link the controller's link discovery has listed. Each link
is checked in each pass of the loop, which reads each switch's port descriptions and the
controller's links. A link is **down** when either:

- **one of its ports reports it at once**: its link is down (the switch's LINK_DOWN bit; never
  the LIVE bit, which a working Arista port does not set), it is administratively down, it is
  no longer listed by its switch, or its switch has left the controller. Confidence high;
- **the controller stops listing it** for two passes in a row while both ports still report
  up. Confidence lower: one pass without it can be link discovery's own timing.

A switch whose port descriptions could not be read leaves its links unjudged rather than
called up or down. One link is one card, whichever end reported it.

**Mercury sends nothing for a link down.** The network's forwarding application (Lab 9's
fabric_forwarding) recomputes every path when a port goes down and rewrites its own flows, so
the response is to **verify** that reroute:

1. Mercury traces every pair of hosts the controller lists (up to 12 pairs) through the
   controller's stored flow tables ([the trace](sdn-trace)).
2. Each pair must be **delivered** on a path that leaves by neither end of the failed link.
3. The card's **Reroute** line then says one of:
   - **rerouted**, every pair delivered;
   - **not rerouted**, naming the first pair and where it ended;
   - **cannot tell**, naming what the trace could not follow;
   - **verifying**, while the stored read is from before the failure or still lists the link.
     Mercury never judges the old tables as the new.

**Each host pair traced** opens to every pair's outcome. In **AUTO**, on a network marked lab,
Mercury verifies at every pass until the link is rerouted. If it has not seen a reroute after
75 seconds, the card says so and leaves it to you. In **HITL**, press **Verify the reroute**.
Nothing was written, so nothing is rolled back.

The card closes by itself once the controller lists the link again and both its ports report
up. **Dismiss with this reason** closes it sooner; the link stays on the Alerts tab until it
returns.

**Needs attention has a row for each link down whose reroute is not verified**, so a failed
link reaches you when you are not on this tab. The row names the network, both ends (each
switch by its DPID and the port) and since when the link is down. It is amber while the reroute
is not verified yet, is being verified, or cannot be told, and red once a verify found it not
rerouted. Its action opens the link's card here, where you press **Verify the reroute**. A link
whose reroute is verified is not a row: it is down, and the fabric works around it. The row
clears when the reroute is verified, when the loop's next pass finds the link listed and both
its ports up, or when you dismiss the card. While the loop is stopped nothing judges the link,
so a link that came back stays a row until the loop runs again or you dismiss its card. If the
network's link-failure cards cannot be read, Needs attention says so in a row of its own.

## What each switch can do {#capabilities}

The matrix is read from each switch's own answers through its controller, never from its
vendor's name. The loop reads it when it starts, and **Read again** reads it now. Each switch
answers three reads: its description, its meter features and its table features. **Not read**
and **none** are different: a switch that did not answer is never shown as lacking a feature.

Each row, and each switch on **Flows**, is named as NetBox names the switch: the device whose
`openflow_datapath_id` is the switch's DPID, in the network's committed NSOT export. A switch
NetBox does not name is drawn by the description it gives of itself where it gives one (never
the placeholder `None`), else by its DPID. Flows' search still finds a switch by what it calls
itself.

- **OpenFlow**: 1.3 or later where it answers table features; 1.0 where the controller says its
  version does not support the request.
- **Tables**: how many tables its table features list.
- **Meters**: yes where it reports a meter with a DROP band, the band a rate limit uses.
- **Fast-failover groups**: always not read for now. No driver reads a switch's group features
  yet; a table that accepts group actions is said beside it.
- **Rewrite (set_field)**: whether any table lists a field it can set.
- **When it cannot** says what Mercury does instead:
  - **a rate limit on a switch with no meters is a drop of the source**, where the network's
    response policy allows a drop. Where it does not, the response waits for you, saying why;
  - **a switch whose meters were not read** keeps the rate limit, and its preview reads them,
    refusing (saying why) if it cannot.

The fallback is said on the response's line in the loop's log, in HITL and in AUTO, and the
protected set still refuses a fallback drop that would touch a protected flow.

## Response policy {#response-policy}

Under the detection rules, **Response policy** says, for each rule, which catalogue actions a
response to it may take on this network, and which is its default (the one proposed when a
detection fires). Where it comes from is beside its name: set on this network, inherited from
Default, or the default (every action that answers the rule: a scan's default a drop, a
flood's a rate-limit, an unauthorised flow's its removal).

- **Each rule**: its **default** (a list of the actions that answer it) and a tick for each
  other action allowed. The default is always allowed.
- **Save the response policy** checks each action answers its rule and saves it as you,
  recorded in the network's settings record with the policy before and after; the rules redraw
  with it. It is refused, beside the button, naming why: an action that does not answer its
  rule, or the policy changed by someone else since the page drew it (look again).
- **What it changes**: the loop proposes the rule's default; Classify sends the model only the
  actions this network allows for the rule, and an answer naming another is refused (the
  card says "AI classification refused: … outside the network's response policy …") and the
  default awaits you, even in AUTO; a preview or a confirm of an action outside it is refused,
  naming the action, the rule and what is allowed.
- **A policy that cannot be read** is said in red under the table: no response action is
  allowed and nothing is sent to AI until it is set again here.

## At phone width {#phone}

Each tab stacks: the summary, then the cards. A flow row becomes a block, each value under its
column's name; tables scroll inside their box, never the page.
