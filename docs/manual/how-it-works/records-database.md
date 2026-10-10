# The records database: save, test, replace its password

Mercury's records move, store by store, from files into one PostgreSQL database on the app host
(`mercury-postgres`, on 127.0.0.1:5433, made by host step 6a). Its settings are the
installation's own, on **Settings › Installation › Connections**, in the **Records database**
card. With no host it is off: every store stays on its files, as today. Nothing here contacts a
device.

![The records database card. Save checks the host, port, database and role, writes them to the installation's settings and appends who, when and which fields to the installation's settings record; it never opens the database, so it works with the database down. Test asks the database six things in order and names the first that fails, and its answer is kept. Replace stores the new password as a secret, records it and tests it, after the role's password was changed on the server by the host step postgres-rotate.sh. No device is contacted.](diagrams/records-database.svg)

## Save {#save}

**Save** writes the card's host, port, database and role. It never opens the database it
configures, so it works with the database down or the password wrong.

1. `check`: what was sent is checked. Read: nothing else. Sent: nothing. Recorded: nothing. The
   host must be a host name or address (empty is off), the port a number from 1 to 65535, and
   the database and role PostgreSQL names; with a host set, both must be there. A refusal names
   the field, and nothing is saved.
2. `write`: only the fields that changed are written, to the installation's settings, for every
   network. Read: the settings as they stand. Sent: nothing. Recorded: the values. Saving what
   is already stored writes nothing and says "Nothing changed".
3. `record`: the save is appended to the installation's settings record, a file. Read: nothing.
   Sent: nothing. Recorded: who, how that was established, when, and the names of the fields
   written, never their values. If the record could not be written the card says so; the save
   is made either way.

A save after the last Test marks that Test out of date on the card: Test again.

## Test {#test}

**Test** asks the database what host step 6a made, with the settings as saved (save first: it
tests what is stored, not what is typed). It changes no setting. The checks run in order; the
first that fails is named with what the server said, and the rest are shown "not tried".

1. `connect`: it signs in as the role at the host, port and database. Read: the settings and the
   password from the secrets store. Sent: the sign-in. A refused password, a database that does
   not exist and nothing listening are each said in the server's words; the password never is.
2. `version`: the server is PostgreSQL 18, the major 6a runs. Another major fails, naming both.
3. `owner`: the role owns the database (6a makes it so).
4. `role`: the role is not a superuser: it owns its database and nothing more.
5. `loopback`: Mercury reaches it on a loopback address, every address the host names; 6a
   publishes the port on loopback only, so another address is another server or the port
   offered beyond this host.
6. `write`: a temporary row is written and read back inside a transaction that is rolled back,
   so nothing is kept.

The answer is kept (each check, when, by whom) and drawn on the card until the next Test:
**answering** when every check passed, **not answering** with the failed check named. When a
store is switched to the database and it does not answer, the card says what cannot be written.

## Replace the password {#replace}

The password shows only as set or not set. Rotating it is two halves, **the server first**:

- **On the server:** the host step `scripts/host-steps/postgres-rotate.sh` (the operator's, on
  the app host) asks for the new password, hidden, and changes the role's password by a
  verifier computed on the host, so the password itself is in no log and on no command line. It
  proves the new password signs in and a wrong one is refused. Until it runs, the old password
  is the one that works; once it has run, Mercury holds the old one and cannot reach its records
  until the second half.
- **Then here:** **Replace…** opens in place of the card, the order first. Enter the same new
  password and **Replace and Test**.

1. `check`: the password is letters, digits and `. _ ~ -` only, 24 characters or more: the rule
   the server's side uses, so Mercury's copy can only be one the server could have been given.
   A refusal leaves the password Mercury holds unchanged.
2. `store`: it is stored in the secrets store, encrypted, and never drawn back.
3. `record`: the replace is appended to the installation's settings record: who, when, and the
   field's name, never its value.
4. `test`: the Test above runs at once. Passing is the proof both sides agree.

## Move a store to the database {#move}

Below the card, **Record stores** lists each store, where it is now and its last check. Deploy
receipts move first. **Move to the database…** opens a preview of every network's receipts:
lines, receipts, completions, and how many lines the table already holds. Nothing is written
until **Move**, which is bound to that preview.

1. `plan`: the preview's counts are read again and compared. Read: every network's
   `deploy_receipts.jsonl` and the table's counts. Sent: nothing. Recorded: nothing. If anything
   moved since the preview (a deploy finished), or the database does not answer, or a file line
   is not JSON, it is refused, naming what it compared, and nothing changes.
2. `copy`: every file line is copied into the table `audit.receipt_lines`, one transaction per
   network, with its place in the file and its sha256. Read: the files. Sent: the lines, to the
   records database. A line already there with the same hash is skipped, so a second move
   copies nothing twice; one there with a DIFFERENT hash is refused, naming the network, the
   line and both hashes, and that network's copy is rolled back.
3. `switch`: receipts now read and write the database (`records_store_receipts`). Recorded: who,
   how that was established and when, in the installation's settings record.
4. `copy-again`: any line a deploy appended between the copy and the switch is copied too.
5. `check`: the file and the table are compared, network by network: the line count, every
   line's hash, and the receipts merged from each, row for row. If they differ, the receipts
   are switched straight back to their files (any line written to the table in between is
   appended to the file first), and the card names the first difference.
6. `read-only`: each file is made read-only and kept for a release, so anything still writing
   to it fails loudly instead of writing where nobody reads.

After the move, the **records-check** reader runs the same check every 5 minutes; a mismatch,
or a database that stops answering, is a row in Needs attention.

## Move a store back to its files {#back}

**Move back to files…** opens the same preview; **Move back** undoes the move without losing a
receipt.

1. `plan`: as above, refused if the receipts are not on the database.
2. `export`: every line written to the table since the move is appended to its network's file,
   which is made writable again, and only then removed from the table, in one transaction.
3. `switch`: receipts read and write their files again, recorded as above.
4. `check`: the receipts read from the files must equal what the table held, row for row, for
   every network; the card says so, or names the networks that differ.

## What it does not do

- It contacts no device.
- A store moves only when a person moves it here, with its count check; receipts are the first
  and, so far, the only store that moves.
- Save never opens the database; Replace never changes the password on the server.
- Moving never deletes a file: the files are deleted by a host step in the release after, once
  the check has matched since the move.
