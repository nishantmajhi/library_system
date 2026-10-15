# LMS — Library Management System

A single-user desktop program for running a small lending library: a catalogue
of books, a register of members, and a ledger of who has what. Python and
Tkinter for the window, SQLite for the data. No server, no third-party
packages.

```
python library_system.py
```

Python 3.8 or later, with Tkinter — which ships with the standard Windows and
macOS installers. On Debian and Ubuntu it is a separate package
(`apt install python3-tk`).

---

## What it does

**Books.** Register a title with its author, ISBN, genre and year. Search by
title or author, filter by whether it is on the shelf, and remove a book that
has never been borrowed.

**Members.** Register a name, email address and phone number. Search by name or
email. Deactivate a membership once everything is back.

**Loans.** Lend an available book to an active member for 14 days. The Active
Loans page shows how late each outstanding loan is and what it has accrued.

**Returns.** Close a loan, put the book back on the shelf, and charge the
overdue fine — £0.50 for each day past the due date. The fine is worked out
once, at the moment of return, and written to the loan.

**History.** Every completed loan, with the day it came back and the fine that
was charged.

**Dashboard.** Totals for the catalogue, what is available, what is out and
what is late.

The first launch of an empty library fills it with eight books, three members
and one overdue loan, so there is something to look at. That happens only when
all three tables are empty.

---

## Where the data lives

`library.db`, next to `library_system.py`, in SQLite's WAL mode. The path is
absolute and derived from the program's own location, so it does not matter
which directory you start the program from.

That file holds real names, email addresses and phone numbers once the program
has been used. It is listed in `.gitignore` along with the `-wal` and `-shm`
files SQLite writes beside it. Do not commit it.

To read or back up the data without the application:

```sh
sqlite3 library.db ".dump" > backup.sql
```

### Opening a library made by an older version

A database written before fines were stored is upgraded in place on the first
launch: a `fine_pence` column is added to `loans`, and the fine on every
completed loan is reconstructed from the due date and the return date, both of
which were already on the row. Nothing is lost and nothing needs to be typed
back in. The upgrade runs once.

---

## The records

| | |
| --- | --- |
| `Book` | `book_id`, `title`, `author`, `isbn`, `genre`, `year`, `available`, `date_added` |
| `Member` | `member_id`, `name`, `email`, `phone`, `date_joined`, `active` |
| `Loan` | `loan_id`, `book_id`, `member_id`, `book_title`, `member_name`, `loan_date`, `due_date`, `return_date`, `returned`, `fine_pence` |

Identifiers are generated: eight hexadecimal characters for a book, `M` or `L`
and six for a member or a loan. They are drawn again if the one drawn is
already in use.

**A loan carries a copy of the book's title and the member's name, and that is
deliberate.** A loan is a receipt: it records what was handed over and to whom,
as those read on the day. Correcting a typo in a title next year must not
rewrite what somebody was given last year, so those two columns are written
once and never updated. Join on `book_id` and `member_id` when you want the
record as it stands today.

**Fines are integer pence.** `FINE_PER_DAY_PENCE` in `lms/models.py` is the
rate; the display divides by 100 at the last moment. A fine that has been
charged is stored on the loan rather than recomputed, so changing the rate
later does not silently rewrite what past borrowers were asked to pay.

---

## What it will refuse to do

Each of these is refused with a message saying why, rather than being allowed
and then failing.

- **Lending a book that is already out,** or lending to a membership that has
  been deactivated.
- **Deactivating a member who still has something out.** The message says how
  many.
- **Removing a book that is on loan.**
- **Removing a book anybody has ever borrowed,** even if every one of those
  loans came back years ago. `loans.book_id` is a real foreign key and the
  loan ledger is the point of the program, so deleting the book would mean
  deleting the record of who had it. There is currently no way to withdraw a
  book from the shelves while keeping its history; see "Known limits".
- **Returning a loan twice.**

If a date in the database cannot be read, the program says which record is at
fault and stops, rather than failing later while drawing a page.

---

## How the code is arranged

```
library_system.py      entry point
lms/
  models.py            the records, and the arithmetic hanging off them
  db.py                schema, migration, and the writes
  library.py           the rules: who may borrow, what may be removed, what is owed
  theme.py             palette and fonts
  widgets.py           the custom Tk widgets
  dialogs.py           the modal forms
  app.py               the window, the pages and the wiring
tests/
```

`models.py`, `db.py` and `library.py` import no Tkinter. Every decision the
program makes is in those three, which is why the suite can drive the whole
thing against an in-memory database with no display.

The dictionaries the pages read are a cache of the database and nothing else:
each change is written first and the cache is updated only once the write has
returned, so a refused write cannot leave the screen disagreeing with the disk.

`widgets.py` has nothing to do with libraries — rounded frames, placeholder
entries, styled buttons, stat cards and a themed `Treeview`. It is usable in
any other Tkinter project as it stands.

---

## Tests

```sh
python tests/run.py             # everything
python tests/run.py --no-gui    # skip the tests that open a window
```

173 tests, standard library only. Roughly a third of them are regressions:
`tests/original.py` reads the pre-cleanup version of the program straight out
of git and imports it, so each of those tests can be run against the code that
had the bug as well as the code that does not. Anything asserted about the
original is asserted against the real original, not a paraphrase of it.

The tests in `tests/test_app.py` and `tests/test_dialogs.py` need a display.
They open the real window and the real forms, call the methods the buttons are
bound to, and read the table cells and labels back. They skip themselves if Tk
cannot start.

---

## Known limits

- **One person at a time.** WAL mode lets another process read while this one
  writes, but there is no locking, no login and no audit trail. Two copies
  running against the same file will overwrite each other's ideas of what is
  on the shelf.
- **A book cannot be withdrawn while keeping its history.** Members have an
  `active` flag; books do not. Adding one means finding somewhere on the Books
  page to say a title has been withdrawn, which is a change to the interface
  rather than to the rules.
- **A deactivated membership cannot be reactivated** from inside the program.
- **Fines are calculated, not collected.** Nothing records that one was paid.
- **No notion of copies.** Two copies of the same title are two books with
  two identifiers.

---

## Licence

Free for personal, non-commercial use. You may use, study and modify this
software for yourself, but you may not use it commercially, and you may not
share or publish it, in its original form or modified. See [LICENSE](LICENSE)
for the full terms.
