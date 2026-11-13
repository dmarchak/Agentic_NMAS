# Set a secret reference's value

Intent never holds a secret. An account's line in intent names a reference
(`user_lab_secret`), and the value lives in {{product}}'s credential store, encrypted, under that
device and reference. A reference you add to intent yourself, such as a new account, has no
value until one is given, and a deploy that needs it is refused before anything is sent. **Set
value…**, on the device's Intent tab, is how a person gives it one.

![Setting a secret reference's value, write-only. You type the value twice with a reason. It is checked: the two match, one token a device's CLI accepts, the reference named in the device's committed intent and not the account Mercury signs in with; any failure stores nothing. The value is stored encrypted for this device, never shown again, and the set is committed with who, when and the reason, never the value. Nothing is sent to the device now: the next deploy sends it, and once that deploy verifies, the device's own form of the value replaces what you typed.](diagrams/set-secret-value.svg)

## The card {#the-card}

The Intent tab's **Secret references** card lists every reference the device's committed intent
names, what each is for (the account and its privilege, or "named in intent"), and its state:

- **the device's own form**: the value the device made of it (type 5, 7, 8 or 9), stored by a
  rotation or captured back after a deploy;
- **the device's value, as it keeps it**: a value the device keeps as it was typed (an SNMP
  community), read from its captured configuration when it was seeded, or set here and carried
  by a verified deploy since; it never becomes "the device's own form";
- **typed, waiting for its deploy**: a value a person set here that no verified deploy of the
  device has carried yet (the set is newer than the device's last deploy that verified);
- **held**: a value the network holds for every device (its monitoring profile, for an SNMP
  community);
- **no value**: nothing held. A deploy that needs it is refused, naming it.

No state shows a value, and no screen can show one back: keep the value yourself.

## The steps {#the-steps}

**Set value…** opens the form below the card: the value, the value again, and why, in one
line. **Store the value** runs these steps; **Cancel** closes the form, storing nothing.

1. `checks` **Check the value.** The two entries match; the value is one token a device's CLI
   accepts (printable characters, no space, at most 127); the reference is named in the
   device's committed intent; it is not the account {{product}} signs in with to the device
   (that one changes by [Rotate](rotate) only, which proves the new password signs in before it
   keeps it); it is not a profile's read-only account (`read-account:profile:<profile>`, whose
   password is set on [Credentials](credentials#read-account), one for every device); and a
   reason is given. A failing check refuses by name, and nothing is stored.
   Setting a value needs a verified person, as committing intent does.
2. `store` **Store it.** The value is stored encrypted for this device and reference, kind
   *plaintext* (typed by a person). Nothing is sent to the device.
3. `record` **Record the set.** One line in the network's repository, `.nsot/secret_values.jsonl`,
   committed as you: who, when, the device, the reference and your reason, never the value. The
   device's History shows the commit.
4. `capture_back` **After its deploy.** [Plan a deploy](deploy) now renders the account's line
   with the value, masked in the preview. A device stores its own form of a typed secret (a
   salted type 9 hash, for instance), so the line it holds never matches the one typed. Once
   the deploy verifies, its stage that records the golden reads the device's own form from the
   configuration it captured, and stores it in place of what you typed, kind *hash*. Intent
   then renders the line the device holds, so the Intent check matches and a later deploy
   changes nothing. A device whose line is absent, or not in a form it made, keeps what you
   typed, and the deploy's result says so.

## What it never does {#never}

- It never sends anything to the device: only a deploy does, with its preview and confirm.
- It never shows, returns or logs a value, and never writes one into the record.
- It never changes the account {{product}} signs in with: that is Rotate's.
- It never removes an account, and {{product}} does not offer that yet: a `username` line is
  not one of the shapes [Mode B](removal) allows, because no removal of one has been measured
  to remove exactly itself.
