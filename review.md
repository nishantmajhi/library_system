# LMS (Library Management System) — review and cleanup record

First reviewed 2026-09-04. Remediated 2026-09-19 on branch `cleanup/2026-09-19`.
Nothing pushed.

**173 tests, all passing.** `python tests/run.py`, or `--no-gui` to skip the
thirty-nine that open a window. Standard library only.

---

## Corrections to the first review

The first review was accurate about everything it named, and it read the file
top to bottom. What it did not do was ask what the numbers on the screen
actually were, and the worst defect in the project is one of those.

**It missed the fine.** The Loan History page has a column headed "Fine (£)"
and the README advertises "Overdue Fines — automatically calculates a £0.50/day
fine for late returns" and "Loan History — full log of all completed loans with
return dates and fines". That column printed `0.00` for every row it has ever
drawn, however late the book was. `fine_amount` was `days_overdue * 0.50`, and
`days_overdue` returned `0` the moment `returned` was set — so the figure the
borrower had just been shown and asked to pay disappeared at the instant it
became a record. There was no fine column in the schema either, so nothing
remembered it. Reproduced against the original before anything was changed:
a loan sixty days overdue reads £30.00 while it is out and £0.00 one line
later. See `tests/test_regressions.py::HistoryFine`.

The lesson is the one from `Quadratic Parser/QIC`, in a different key: the
review checked that the arithmetic was written down somewhere sensible and did
not check what it produced. A headline feature with a column of its own is
worth one run.

**"The fine rate is a bare literal" understated it.** Named constant and
integer pence, yes — but the reason it matters is that a fine is a sum of money
somebody was asked to pay, so it has to be *stored*, not recomputed. Recomputing
means the next change to the rate quietly rewrites history.

**It missed five smaller defects**, all listed below and all reproduced against
the original first.

Everything the first review did list was real. Nothing in it was wrong.

---

## Fixed

**1. The fine on a completed loan was always zero.** The `loans` table now has
a `fine_pence` column. `Library.return_loan` works the charge out once, at the
moment of return, from the return date rather than from today, and writes it.
`Loan.fine_pence_now` reports the stored figure for a closed loan and the
accruing figure for an open one, so the Active Loans page still counts upwards
and the History page shows what was charged. Money is integer pence throughout;
`FINE_PER_DAY_PENCE = 50` and `CURRENCY` are named in `lms/models.py`.

An existing `library.db` is migrated on first launch: the column is added and
**every historical fine is reconstructed** from the due date and the return
date, both of which were already on the row. Nothing had to be written off.
The migration runs once and is covered by five tests including a leap-day case.

**2. Removing a book that had ever been borrowed threw an unhandled
exception.** `loans.book_id` is a real foreign key with the pragma on, so the
`DELETE` was refused by SQLite for any book with a loan record — including
loans returned years ago. The only guard in the application was "is it on loan
right now", which a returned book passes. Worse, the in-memory catalogue was
mutated *before* the delete was attempted, so the book left the screen, the
delete then failed, and it was back after a restart.

It is now refused, with a message that says the book has loan history and that
removing it would remove the record of who borrowed it. **Soft-deleting was the
better answer and was not taken:** it needs somewhere on the Books page to say
a title is withdrawn, and this pass is not allowed to change the interface. See
"For the author" below.

**3. The in-memory copy and the database could disagree.** The original kept
three dictionaries and wrote to SQLite separately. `lms/library.py` now owns
both: the dictionaries are a cache, every change is written first, and the
cache is updated only once the write has returned. `Database.record_loan` and
`record_return` each put their two rows in one transaction, so a loan and its
book's availability cannot half-apply. Six tests mutate the library every way
it can be mutated, reload from disk, and require the two to match — including
after a refusal.

**4. A repeated loan identifier destroyed a loan.** A loan id is a letter and
six hex characters: 24 bits, an even-money collision at about 4,800 loans.
`save_loan` was an upsert, so a collision took the `ON CONFLICT DO UPDATE`
branch and overwrote the *existing* loan's `returned` and `return_date` — the
old loan silently reopened, and the new one was never written at all.
Reproduced against the original: two loans in, one row out, and the surviving
row reopened. Writing a loan is now a plain `INSERT`, which raises on a
duplicate rather than swallowing it, and `new_id()` draws again if the
identifier it drew is in use. Same for books and members.

**5. `DB_FILE = "library.db"` was relative to the working directory.** Starting
the program from anywhere else created a second, empty library. Reproduced by
running the original from two directories. It is now
`Path(__file__).resolve().parent.parent / "library.db"`.

**6. A malformed date raised out of whichever property touched it first.**
Three properties each called `datetime.strptime` on the stored string, so a
damaged row produced a `ValueError` from the middle of drawing a page, with
nothing in the message to say which record. Dates are now `datetime.date`
objects on the records, parsed once at the database boundary; an unreadable one
raises `DataError` at load naming the record and the column, and `main()` shows
it. The stored format is unchanged, so existing files and `sqlite3` on the
command line are unaffected.

**7. The demo seeder re-registered the demo members.** The guard was
`if self.books: return`, so emptying the catalogue of a library that still had
members added Alice, James and Sophie again, under fresh identifiers, on every
launch. It now runs only when books, members and loans are all empty.

**8. The publication-year check vanished under `python -O`.** It was
`assert 1 <= yr <= datetime.now().year + 1` inside a bare `try`/`except`.
`assert` is compiled out by `-O`, so the range check simply disappeared and any
integer was accepted; the bare `except` also caught `KeyboardInterrupt`. It is
now `models.valid_year()`, a plain function, tested under `-O` in a subprocess
alongside the original idiom, which does accept the year 99999 that way.

**9. The dashboard clock multiplied its own timer.** Every visit to the
dashboard started a fresh chain of `after` callbacks without stopping the one
already running, so six round trips left seven timers repainting the same
label. The pending job is now cancelled first, and again on close. Confirmed
against the unfixed `_tick`: eight pending jobs where there should be two.

**10. `StatCard.update(v)` overrode `tk.Misc.update()`,** which takes no
argument — any standard redraw call on a stat card would have raised
`TypeError`. It was never called. Renamed `set_value`. The equally dead
`scrolled_tree` helper was removed; every page built its own scrollbar inline.

**11. No `.gitignore`.** Added, covering `library.db` and its `-wal`/`-shm`
companions, which contain real member names, emails and phone numbers once the
program has been used. This was the first review's P1 and was one `git add -A`
away from mattering. Nothing of the sort had actually been committed — the
repository had a single commit and no database in it.

**12. The loan period was written twice.** `14` appeared in the `Loan` default
and again in the text of the issue dialog, so the date promised and the date
recorded could drift. Both derive from `LOAN_PERIOD_DAYS` now.

**13. The connection was reopened per call and never closed.** `_get_conn()`
ran `PRAGMA journal_mode=WAL` on every single save. One connection is now
opened by `Database` and closed when the window closes.

---

## Deliberately not done

**The denormalised loan columns stay.** The first review asked for a decision:
drop `book_title` and `member_name` and join, or declare them a point-in-time
snapshot. They are declared. A loan is a receipt — it records what was handed
over and to whom, as those read on the day — so correcting a title next year
must not rewrite what somebody was given last year. This is written on the
`Loan` class, in the README, and asserted by a test, so it will not be quietly
tidied away later. `Database.record_return` writes only the columns a return
changes, and a test confirms the snapshot survives a hostile write.

**Books are not soft-deleted.** See item 2 above. This is the one place where
the right answer needs an interface change, and the pass did not have licence
to make one.

**No `LICENSE` file.** The README has claimed MIT since the first commit and
links to a file that has never existed. Choosing and adding a licence is the
author's decision, not a cleanup's; the README now says so plainly instead of
linking to nothing.

**Membership reactivation was not added.** There is no way back from
deactivating a member. That is a missing feature rather than a bug, and adding
it would need a context-menu item the interface does not have.

**The UI was not touched** — layout, styling, copy and interaction are as they
were. One visible string did change: the sidebar reads `LMS v1.1.0` rather than
`v1.0.0`, because the database schema changed and a version that stands still
through a schema change is a lie. It is now read from `lms.__version__` rather
than typed into the sidebar, which was the first review's point about version
numbers that live in exactly one place.

---

## Structure

The 1,149-line single file is now 1,661 lines across eight modules plus a
thirteen-line entry point -- more lines in total, and much less in each of them.
The largest is app.py at 539.

```
library_system.py      entry point, so `python library_system.py` still works
lms/models.py          the records, and the arithmetic hanging off them
lms/db.py              schema, migration, and the writes
lms/library.py         the rules
lms/theme.py           palette and fonts
lms/widgets.py         the custom Tk widgets
lms/dialogs.py         the modal forms
lms/app.py             the window, the pages and the wiring
```

`models.py`, `db.py` and `library.py` import no Tkinter, which is the whole
point: 134 of the 173 tests need no display at all. The dialogs no longer build
records — `IssueLoanDialog` returns the pair of identifiers it was asked to
choose, and the library decides whether the book is still on the shelf by the
time OK is pressed.

`widgets.py` is the reusable toolkit the first review spotted, now separable.

---

## Notes for whoever is next

**`tests/original.py` is the pattern worth stealing here.** The original was a
single self-contained module that does nothing at import time, so there was no
need to transcribe it the way `wordgit` and `replace-em-en-dash` had to: the
baseline commit is read out of `git show`, written to a scratch file, imported
under its own name, and its one global — `DB_FILE` — is redirected at a
temporary directory. Every behavioural claim about the original in this
project's tests is made against the real original. It is about eighty lines.
The baseline is found by its commit *subject*, not its hash, so a rebase does
not silently disable half the suite; it raises, and the tests skip loudly.

Where a defect lives inside a Tk callback that cannot be called without a
display — the `_remove_book` ordering, the `_seed_demo` guard — the tests
assert on the baseline *source* instead, and say so in the test name and the
docstring. That is weaker evidence and is marked as such rather than dressed up.

**A Tkinter application can be tested properly without clicking anything.**
`tests/test_app.py` opens the real window with `withdraw()`, calls the same
methods the buttons are bound to, and reads the table cells back with
`Treeview.item(iid, "values")`. That is how the History page's fine is asserted
at the surface it was wrong on, rather than only in the model. Two things to
know: those cells come back as **strings**, so `assertEqual(values[5], 3)` fails
against `'3'`; and `self.app.tk.call("after", "info")` lists the pending timers,
which is what made the clock leak visible as a number.

**The dashboard rebuilds every page from scratch on `_show`.** That is why
`StatCard` never needed an update method and why there is no incremental
refresh to keep in step. If you add one, the stat cards have `set_value`.

**Do not run the program while the tests are running.** They use scratch
databases under `%TEMP%`, but a stray `python library_system.py` will create
`library.db` in the project directory, which is git-ignored but easy to forget.

---

## For the author

Two decisions are yours and nothing has been done about either:

1. **Whether a book should be withdrawable while keeping its loan history.**
   Right now the answer to "remove this book" is no for anything ever
   borrowed. A soft delete — an `available`-style flag, a "Withdrawn" status in
   the Books table, and the withdrawn ones filtered out of the issue dialog —
   is the proper answer and needs an interface change to carry it.

2. **The licence.** The README has said MIT since the first commit with no
   `LICENSE` file behind it.

No credentials, no secrets, no personal data and no deployed anything were
found in this project. The repository had one commit and no database in it.

---

## Five minutes at a real keyboard

Everything below has been driven by a test except the right-click menus, which
`tk_popup` makes unreachable: it grabs the pointer and waits. The program itself
has been launched and its database inspected, and 39 of the 173 tests open a
real window, walk every page and read the cells and labels back. This is the
remainder.

Start with no `library.db`, so the demo data is seeded.

1. **`python library_system.py`.** Dashboard: four stat cards, one active loan,
   one overdue. The clock ticks.

2. **Active Loans → Return Book.** Choose the loan. If you seeded it today the
   label under the combo reads `3 day(s) overdue · Fine: £1.50`, and one day
   more for each day since. Confirm; the dialog names the same figure.

3. **Loan History.** *The Great Gatsby* is there with a return date and a fine
   in the last column. **It must not be `0.00`.** That column printed `0.00`
   for every completed loan the program had ever recorded, and this is the fix.

4. **Books → right-click *The Great Gatsby* → Remove Book.** It must refuse:
   "has loan history and cannot be removed". Close the program, reopen it, and
   confirm the book is still in the catalogue. The original threw an
   IntegrityError here *after* deleting it from the screen, so it vanished and
   came back on the next launch.

5. **Books → right-click a book nobody has borrowed → Remove Book.** It should
   ask for confirmation and then go, and stay gone after a restart.

6. **Issue a loan to a member, then Members → right-click them → Deactivate
   Member.** It must refuse and say how many they are holding.

Then move to each of the five pages once, and back to the Dashboard a few
times — the clock should tick once a second, not several times.

## Licence, 2026-10-02

The author chose one licence for all of their projects: free for personal,
non-commercial use, modifiable for the user's own use, and not to be
distributed, original or modified. No standard licence says that, so `LICENSE`
is a short custom text, the same in every project apart from the year and what
it excludes. The README's licence section says the same. Anything above that
calls the licence an open question, or calls the project MIT, is superseded.

## CI, 2026-10-02

`.github/workflows/ci.yml` runs `tests/run.py` under `xvfb-run` on Python
3.12, `ubuntu-latest`, so the 39 tests that open Tk windows run instead of
being skipped with `--no-gui`. Nothing has been pushed, so it has not run on
GitHub yet. Every job was run before committing, from a fresh clone of this
branch, the way a runner would run it: Linux jobs in a throwaway Ubuntu 24.04
(the image `ubuntu-latest` uses) with the same tool versions. all 173.

Full history, which `tests/original.py` reads.
