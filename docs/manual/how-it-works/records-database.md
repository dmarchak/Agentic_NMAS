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

## What it does not do

- It contacts no device.
- It moves no store: a store switches to the database on its own, with its own count check
  (receipts first).
- Save never opens the database; Replace never changes the password on the server.
