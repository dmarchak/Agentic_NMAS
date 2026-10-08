# Settings

The tool's configuration, in three scopes of one page: **Installation** (what every network shares: sign-in, the central NetBox connection, this host), **Default** (the base layer the networks that inherit take their values from) and **a network** (its own settings). The scope bar at the top moves between them; its network picker leads with the networks that differ from Default, standalone ones first.

## A network's page {#network}

- **Its mode**, on the banner: it inherits from Default, or it is standalone and takes nothing from Default, with who made it so and when. The banner's button opens the switch's preview (see [Inherit or stand alone](settings-switch)).
- **One card per group**, on two tabs (Integrations: Grafana, its dashboards, Prometheus, Loki, Kea, the topology service, the monitoring profile, the S3 archive and the lab; Network: the deploy tuning, the TFTP server and NetBox's excluded VRFs). Each card says where its values come from: *set here*, *inherited from Default*, *not configured for this network*, *not applicable here*, or *unset everywhere*; and every field shows its value with where it came from. A secret shows as "set", never its value.
- **Each group's own choice**: inherit from Default, its own, or not applicable. Choosing another opens that switch's preview in place of the card; nothing is saved by the choice itself. A group that is its own has **Configure…**, which takes its values in the card.

## Default's page {#default}

Default's cards show its values and, on each, who takes them: "inherited by 12 · own Grafana in 4 · not configured in 2 · not applicable in 1", counting only the networks that chose to inherit, with the names one click down. A change to Default changes every network counted there.

## What is not here yet {#not-yet}

- **Installation** is on today's Settings page: the scope bar's Installation opens it.
- **Saving one field of a group**, and Default's change with its warning naming who inherits it, are on today's Settings page until they reach this page.
- **Creating a network** is on today's page; a new network starts as inheriting from Default, and its page here offers the switch at once.
