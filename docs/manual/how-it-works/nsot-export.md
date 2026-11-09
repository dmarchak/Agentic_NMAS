# Commit a network's NSOT export

A network's NSOT export is what NetBox says about the network at a moment: its devices,
interfaces, VLANs, prefixes, services and cables, as one document that reads the same bytes
every time it is read. Mercury keeps it in the network's configuration repository as
`nsot/export.json`, and SDN's controller apps read the controller hosts and the expected
switches and links from the committed one, never from NetBox live, so every plan made from it
names the same facts. You commit it from [SDN › Apps](sdn#apps), with **Export from NetBox…**.

![Committing a network's NSOT export: Export from NetBox reads the network's records from NetBox, read only, builds the export and compares it with the committed one by kind, and shows its hash; you confirm, bound to that hash and the committed file's; NetBox is read again and a moved export, or a commit made since, commits nothing and says both; the export is committed to the network's configuration repository as you, the commit is the record, and every page reading the export reads it again. No device is contacted and nothing is written to NetBox.](diagrams/nsot-export.svg)

## The steps

1. `read`: Mercury reads the network's records from NetBox: its devices (the inventory's own
   filters, and the parent of each `openflow` Service), their interfaces, addresses, services
   and cables, and its sites' VLANs and prefixes. Whole lists, never one request per device,
   and nothing is written to NetBox. A network whose devices are not NetBox's has no export.
2. `compare`: the export is built and compared with the committed one, kind by kind: what was
   added, removed and changed, each named by its key (a device's name, an interface's device
   and name, a cable's two ends). Its SHA-256 and the committed file's are the hash the confirm
   binds.
3. `confirm`: you confirm, as yourself, with **Commit the export**.
4. `check`: NetBox is read again and the export built again. If its hash is not the one you
   saw, or someone committed an export since, nothing is committed, and the card says what
   moved with both values.
5. `commit`: `nsot/export.json` is committed in the network's configuration repository as you,
   with `Actor:`, `Actor-Verified:`, `Export-Sha256:` and `Source: nsot_export`. The committed
   file is checked once more inside the repository's lock.
6. `announce`: every open page reading the export (SDN › Apps' controllers, a deploy's expected
   switches and links) reads it again.

## The preview {#preview}

**Export from NetBox…** opens the preview in the card's place: this export's hash beside the
committed one's (with its commit, when and who), where it goes, and a table of what changes by
kind. Each kind's names fold under its count; a kind that does not change is listed once as
unchanged. Reading the preview writes nothing.

## A preview that changes nothing {#nothing}

When NetBox reads as the committed export, byte for byte, the card says so and offers no
confirm: committing it would change no line.

## The confirm {#confirm}

**Commit the export** is a verified person's (the approve gate: an export is a record later
changes act on, as committed intent is). It is bound to the preview's hash: the new export's and
the committed file's together. A refusal names what it compared: "NetBox's export now hashes
…, and the preview showed …", or "the committed export moved since the preview (now …;
previewed …)". Preview again to see what moved.

## The commit, and where it is kept {#commit}

The commit is the record. It changes no device, so there is nothing to verify on one or roll
back: a wrong export is corrected by committing the next one. The card at rest reads the newest
export commit from the repository's history (its hash, its commit, who and when, NetBox's
version and what it holds), so it says the same later, and History's commits list it with its
Actor and its Export-Sha256.

The export is installation data: it lives under Mercury's data folder, in the network's own
repository, and never in Mercury's published code.
