"""One class per defect: the original misbehaving, then the fix.

Every test here was written before the corresponding fix and confirmed to fail
against the baseline commit. Where the defect can be provoked by calling the
original code, it is -- `original.py` imports the baseline module straight out
of git, so these are not transcriptions. Where the decision is buried inside a
Tk callback that cannot be called without a display, the baseline *source* is
asserted on instead, and those tests say so.
"""

import subprocess
import sys
import textwrap
import unittest
from datetime import date, timedelta
from pathlib import Path

from helpers import LibraryCase, memory_library, raw_rows

import original
from original import requires_original, with_db

from lms.db import DEFAULT_DB_PATH, Database
from lms.library import LibraryError
from lms.models import FINE_PER_DAY_PENCE, LOAN_PERIOD_DAYS, Book, Member, valid_year


def baseline_source():
    return original._git("show", f"{original.baseline_commit()}:library_system.py")


def stock_library(orig, overdue_by=0):
    """A book, a member and one loan, in the baseline module's world."""
    book = orig.Book("Dune", "Frank Herbert", "978-0441013593", "Fantasy", 1965)
    member = orig.Member("Alice", "alice@example.com", "07700 900100")
    orig.save_book(book)
    orig.save_member(member)
    loan = orig.Loan(book_id=book.book_id, member_id=member.member_id,
                     book_title=book.title, member_name=member.name)
    loan.due_date = (date.today() - timedelta(days=overdue_by)).strftime("%Y-%m-%d")
    orig.save_loan(loan)
    return book, member, loan


# ----------------------------------------------------------------------------
# 1. The fine on a completed loan
# ----------------------------------------------------------------------------

class HistoryFine(LibraryCase):
    """The Loan History page's "Fine (£)" column printed 0.00 for every row.

    `fine_amount` was `days_overdue * 0.50`, and `days_overdue` returned 0 as
    soon as `returned` was set, so the figure the borrower had just been asked
    to pay vanished the instant it was recorded. There was no fine column in
    the schema either, so nothing remembered it.
    """

    @requires_original
    def test_original_forgets_the_fine_the_moment_the_book_is_returned(self):
        with with_db() as orig:
            _, _, loan = stock_library(orig, overdue_by=60)
            self.assertEqual(loan.days_overdue, 60)
            self.assertEqual(loan.fine_amount, 30.00)

            loan.returned = True
            loan.return_date = date.today().strftime("%Y-%m-%d")
            orig.save_loan(loan)

            self.assertEqual(loan.fine_amount, 0.0)
            # ...and this is the exact expression the History page rendered.
            cell = f"{loan.fine_amount:.2f}" if loan.fine_amount else "0.00"
            self.assertEqual(cell, "0.00")

    @requires_original
    def test_original_has_nowhere_to_store_it(self):
        with with_db() as orig:
            columns = {
                r["name"]
                for r in orig._get_conn().execute("PRAGMA table_info(loans)")
            }
            self.assertNotIn("fine_pence", columns)

    def test_fixed_records_the_fine_that_was_charged(self):
        loan = self.issue(days_ago=LOAN_PERIOD_DAYS + 60)
        closed = self.lib.return_loan(loan.loan_id)
        self.assertEqual(closed.fine_pence, 60 * FINE_PER_DAY_PENCE)
        cell = f"{closed.fine_amount:.2f}" if closed.fine_amount else "0.00"
        self.assertEqual(cell, "30.00")

    def test_fixed_keeps_it_across_a_restart(self):
        loan = self.issue(days_ago=LOAN_PERIOD_DAYS + 60)
        self.lib.return_loan(loan.loan_id)
        self.lib.load()
        self.assertEqual(f"{self.lib.loans[loan.loan_id].fine_amount:.2f}", "30.00")


# ----------------------------------------------------------------------------
# 2. Removing a book that has ever been borrowed
# ----------------------------------------------------------------------------

class RemoveWithHistory(LibraryCase):
    """`delete_book` threw IntegrityError for any book with a loan record.

    `loans.book_id` is a foreign key and the pragma is on, so the delete was
    refused by SQLite. The only guard in the app was "is it on loan right now",
    which a returned book passes.
    """

    @requires_original
    def test_original_raises_for_a_book_that_was_borrowed_and_returned(self):
        import sqlite3
        with with_db() as orig:
            book, _, loan = stock_library(orig, overdue_by=1)
            loan.returned = True
            loan.return_date = date.today().strftime("%Y-%m-%d")
            orig.save_loan(loan)
            book.available = True
            orig.save_book(book)

            self.assertTrue(book.available)   # so the app's only check passed
            with self.assertRaises(sqlite3.IntegrityError):
                orig.delete_book(book.book_id)

    @requires_original
    def test_original_drops_the_book_from_memory_before_trying_the_delete(self):
        # Source-level: the ordering lives in a Tk callback that cannot be
        # called without a display. The consequence is that the book leaves the
        # screen, the delete then fails, and it is back after a restart.
        source = baseline_source()
        removal = source[source.index("def _remove_book"):source.index("def _deactivate_member")]
        self.assertIn("del self.books[b.book_id]", removal)
        self.assertIn("delete_book(b.book_id)", removal)
        self.assertLess(removal.index("del self.books[b.book_id]"),
                        removal.index("delete_book(b.book_id)"))
        self.assertNotIn("try", removal)

    def test_fixed_refuses_with_a_message_instead_of_raising(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        with self.assertRaises(LibraryError) as caught:
            self.lib.remove_book(self.book.book_id)
        self.assertIn("loan history", caught.exception.message)

    def test_fixed_leaves_memory_and_database_agreeing(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        with self.assertRaises(LibraryError):
            self.lib.remove_book(self.book.book_id)
        self.assertIn(self.book.book_id, self.lib.books)
        self.lib.load()
        self.assertIn(self.book.book_id, self.lib.books)


# ----------------------------------------------------------------------------
# 3. Where the database file lands
# ----------------------------------------------------------------------------

class DatabaseLocation(unittest.TestCase):
    """`DB_FILE = "library.db"` was relative to the working directory."""

    @requires_original
    def test_original_starts_a_second_empty_library_from_another_directory(self):
        import os
        import tempfile
        orig = original.load()
        previous_file, previous_cwd = orig.DB_FILE, os.getcwd()
        first = Path(tempfile.mkdtemp(prefix="lms-cwd-a-"))
        second = Path(tempfile.mkdtemp(prefix="lms-cwd-b-"))
        try:
            orig.DB_FILE = "library.db"          # exactly as the baseline has it
            os.chdir(first)
            orig.init_db()
            orig.save_book(orig.Book("Dune", "FH", "i", "Fantasy", 1965))
            self.assertEqual(len(orig.load_data()[0]), 1)

            os.chdir(second)
            self.assertEqual(len(orig.load_data()[0]), 0)   # the library is gone
            self.assertTrue((second / "library.db").exists())
        finally:
            os.chdir(previous_cwd)
            orig.DB_FILE = previous_file

    def test_fixed_resolves_against_the_program(self):
        self.assertTrue(DEFAULT_DB_PATH.is_absolute())
        self.assertEqual(DEFAULT_DB_PATH.parent,
                         Path(__file__).resolve().parent.parent)


# ----------------------------------------------------------------------------
# 4. A loan identifier drawn twice
# ----------------------------------------------------------------------------

class LoanIdentifierCollision(LibraryCase):
    """`save_loan` upserted, so a repeated identifier destroyed a loan.

    A loan id is a letter plus six hex characters: 24 bits, which is an
    even-money collision at about 4,800 loans. On a collision the ON CONFLICT
    branch updated the *existing* loan's `returned` and `return_date`, so the
    old loan silently reopened or closed and the new one was never written.
    """

    @requires_original
    def test_original_overwrites_the_loan_it_collided_with(self):
        with with_db() as orig:
            book, member, first = stock_library(orig, overdue_by=1)
            first.returned = True
            first.return_date = "2026-01-01"
            orig.save_loan(first)

            second = orig.Loan(book_id=book.book_id, member_id=member.member_id,
                               book_title=book.title, member_name="Someone Else")
            second.loan_id = first.loan_id          # the collision
            orig.save_loan(second)

            loans = orig.load_data()[2]
            self.assertEqual(len(loans), 1)                    # one loan, not two
            self.assertEqual(loans[first.loan_id].member_name, "Alice")
            self.assertFalse(loans[first.loan_id].returned)    # reopened silently
            self.assertIsNone(loans[first.loan_id].return_date)

    def test_fixed_refuses_a_duplicate_identifier(self):
        import sqlite3
        loan = self.issue()
        duplicate = self.lib.loans[loan.loan_id]
        clone = type(duplicate)(
            book_id=self.book.book_id, member_id=self.member.member_id,
            book_title="Dune", member_name="Someone Else", loan_id=loan.loan_id,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.lib.db.record_loan(clone, self.book)
        rows = raw_rows(self.lib.db, "SELECT member_name FROM loans")
        self.assertEqual([r["member_name"] for r in rows], ["Alice Pemberton"])

    def test_fixed_never_issues_an_identifier_already_in_use(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        for _ in range(30):
            issued = self.issue()
            self.lib.return_loan(issued.loan_id)
        self.assertEqual(len(self.lib.loans), 31)
        self.assertEqual(len(set(self.lib.loans)), 31)


# ----------------------------------------------------------------------------
# 5. A date the database cannot spell
# ----------------------------------------------------------------------------

class UnreadableDate(unittest.TestCase):
    """A malformed date raised out of whichever property touched it first."""

    @requires_original
    def test_original_raises_valueerror_from_a_property(self):
        orig = original.load()
        loan = orig.Loan(book_id="B1", member_id="M1",
                         book_title="Dune", member_name="Alice")
        loan.due_date = "19/09/2026"
        with self.assertRaises(ValueError) as caught:
            loan.is_overdue
        # Nothing in the message says which loan, or which column.
        self.assertNotIn("L", str(caught.exception).replace("time data", ""))

    def test_fixed_reports_it_at_load_and_names_the_record(self):
        from lms.db import DataError
        db = Database(":memory:")
        self.addCleanup(db.close)
        db.save_book(Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1"))
        db.save_member(Member("Alice", "a@e.com", "p", member_id="M1"))
        from lms.models import Loan
        db.record_loan(
            Loan(book_id="B1", member_id="M1", book_title="Dune",
                 member_name="Alice", loan_id="LBAD01"),
            Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1", available=False))
        with db._conn:
            db._conn.execute("UPDATE loans SET due_date='19/09/2026'")
        with self.assertRaises(DataError) as caught:
            db.load()
        self.assertIn("loan LBAD01", str(caught.exception))
        self.assertIn("due date", str(caught.exception))


# ----------------------------------------------------------------------------
# 6. Year validation under python -O
# ----------------------------------------------------------------------------

class YearValidationUnderOptimisation(unittest.TestCase):
    """The range check was an `assert`, which `python -O` removes."""

    ORIGINAL_IDIOM = textwrap.dedent(
        """
        from datetime import datetime
        y = "99999"
        try:
            yr = int(y)
            assert 1 <= yr <= datetime.now().year + 1
        except:
            print("REJECTED")
        else:
            print("ACCEPTED", yr)
        """
    )

    def run_snippet(self, code, optimised):
        argv = [sys.executable] + (["-O"] if optimised else []) + ["-c", code]
        return subprocess.run(argv, capture_output=True, text=True,
                              check=True).stdout.strip()

    def test_original_rejects_an_absurd_year_normally(self):
        self.assertEqual(self.run_snippet(self.ORIGINAL_IDIOM, False), "REJECTED")

    def test_original_accepts_it_under_dash_O(self):
        self.assertEqual(self.run_snippet(self.ORIGINAL_IDIOM, True), "ACCEPTED 99999")

    def test_fixed_rejects_it_either_way(self):
        code = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
            from lms.models import valid_year
            print("ACCEPTED" if valid_year("99999") else "REJECTED")
            """
        )
        self.assertEqual(self.run_snippet(code, False), "REJECTED")
        self.assertEqual(self.run_snippet(code, True), "REJECTED")

    def test_fixed_does_not_swallow_a_keyboard_interrupt(self):
        # The bare `except` the original used caught KeyboardInterrupt too.
        class Hostile:
            def __int__(self):
                raise KeyboardInterrupt
            def strip(self):
                return self
        with self.assertRaises(KeyboardInterrupt):
            valid_year(Hostile())


# ----------------------------------------------------------------------------
# 7. The demo seeder
# ----------------------------------------------------------------------------

class DemoSeeder(unittest.TestCase):
    """The guard looked at books alone, so members were re-registered."""

    @requires_original
    def test_original_guard_only_consults_the_books(self):
        # Source-level: `_seed_demo` is a method on the Tk application.
        source = baseline_source()
        seeder = source[source.index("def _seed_demo"):source.index("def _tick")]
        self.assertIn("if self.books: return", seeder)
        self.assertNotIn("self.members and", seeder)
        self.assertNotIn("self.loans", seeder.split("# one overdue loan")[0])

    def test_fixed_guard_consults_all_three(self):
        lib = memory_library()
        self.addCleanup(lib.db.close)
        lib.add_member(Member("Real Person", "r@example.com", "p"))
        self.assertFalse(lib.seed_demo())
        self.assertEqual(len(lib.members), 1)


# ----------------------------------------------------------------------------
# 8. Dead code that shadowed a Tk method
# ----------------------------------------------------------------------------

class StatCardUpdate(unittest.TestCase):
    """`StatCard.update(v)` overrode `tk.Misc.update()`, which takes no value."""

    @requires_original
    def test_original_shadows_it(self):
        source = baseline_source()
        self.assertIn("def update(self, v): self._val.config", source)

    def test_fixed_leaves_the_tk_method_alone(self):
        from lms.widgets import StatCard
        import tkinter as tk
        self.assertIs(StatCard.update, tk.Misc.update)
        self.assertTrue(callable(StatCard.set_value))

    @requires_original
    def test_the_dead_helper_is_gone(self):
        # `scrolled_tree` was never called: every page built its own scrollbar.
        source = baseline_source()
        self.assertEqual(source.count("scrolled_tree"), 1)   # the definition only
        from lms import widgets
        self.assertFalse(hasattr(widgets, "scrolled_tree"))


if __name__ == "__main__":
    unittest.main()
