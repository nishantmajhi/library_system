"""The window itself.

app.py was rewritten hardest -- every page now reads through the Library -- so
these drive a real Tk instance against a scratch database and walk every page.
Nothing is clicked: the tests call the same methods the buttons are bound to.

They need a display. Set LMS_SKIP_GUI_TESTS=1, or pass --no-gui to run.py, to
skip them; everything that decides anything is covered without a window in
test_models, test_db, test_library and test_regressions.
"""

import os
import unittest
from datetime import date, timedelta

from helpers import temp_db_path

from lms.models import FINE_PER_DAY_PENCE, LOAN_PERIOD_DAYS, Book, Member


def _display_available():
    if os.environ.get("LMS_SKIP_GUI_TESTS"):
        return False
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


requires_display = unittest.skipUnless(
    _display_available(), "no Tk display, or LMS_SKIP_GUI_TESTS is set"
)

PAGES = ("dashboard", "books", "members", "loans", "history")


@requires_display
class AppCase(unittest.TestCase):
    def setUp(self):
        from lms.app import LibraryApp
        self.path = temp_db_path()
        self.app = LibraryApp(self.path)
        self.app.withdraw()          # keep it off the screen during a test run

    def tearDown(self):
        # A test may have called _on_close, which already did both.
        for shutdown in (self.app.db.close, self.app.destroy):
            try:
                shutdown()
            except Exception:
                pass

    def clock_jobs(self):
        """The pending `after` jobs Tk is holding for this interpreter."""
        return self.app.tk.call("after", "info")


class Startup(AppCase):
    def test_it_seeds_an_empty_database(self):
        self.assertEqual(len(self.app.books), 8)
        self.assertEqual(len(self.app.members), 3)
        self.assertEqual(len(self.app.loans), 1)

    def test_the_database_lands_where_it_was_asked_to(self):
        self.assertTrue(self.path.exists())

    def test_the_pages_read_through_the_library(self):
        self.assertIs(self.app.books, self.app.lib.books)
        self.assertIs(self.app.members, self.app.lib.members)
        self.assertIs(self.app.loans, self.app.lib.loans)


class Pages(AppCase):
    def test_every_page_draws(self):
        for page in PAGES:
            with self.subTest(page=page):
                self.app._show(page)
                self.app.update_idletasks()

    def test_every_page_draws_again_after_a_return(self):
        loan = next(iter(self.app.lib.active_loans()))
        self.app.lib.return_loan(loan.loan_id)
        for page in PAGES:
            with self.subTest(page=page):
                self.app._show(page)
                self.app.update_idletasks()

    def test_the_books_table_lists_the_catalogue(self):
        self.app._show("books")
        self.assertEqual(len(self.app._btree.get_children()), 8)

    def test_the_books_filter_pills(self):
        self.app._show("books")
        self.app._bfilter.set("available")
        self.app._fill_books()
        self.assertEqual(len(self.app._btree.get_children()), 7)
        self.app._bfilter.set("on_loan")
        self.app._fill_books()
        self.assertEqual(len(self.app._btree.get_children()), 1)
        self.app._bfilter.set("all")
        self.app._fill_books()
        self.assertEqual(len(self.app._btree.get_children()), 8)

    def test_the_books_search(self):
        self.app._show("books")
        self.app._bsearch.set("orwell")
        self.assertEqual(len(self.app._btree.get_children()), 1)
        self.app._bsearch.set("")
        self.assertEqual(len(self.app._btree.get_children()), 8)

    def test_the_members_table_counts_loans(self):
        self.app._show("members")
        rows = {
            iid: self.app._mtree.item(iid, "values")
            for iid in self.app._mtree.get_children()
        }
        borrower = next(iter(self.app.lib.active_loans())).member_id
        self.assertEqual(int(rows[borrower][5]), 1)

    def test_the_active_loans_table_shows_the_accruing_fine(self):
        self.app._show("loans")
        values = self.app._ltree.item(
            self.app._ltree.get_children()[0], "values"
        )
        self.assertEqual(values[7], "OVERDUE")
        self.assertEqual(values[5], "3")        # the seeded loan is 3 days late
        self.assertEqual(values[6], "1.50")


class HistoryPage(AppCase):
    def test_a_completed_overdue_loan_shows_the_fine_it_was_charged(self):
        # The regression, at the surface it was visible on: this cell printed
        # 0.00 for every completed loan, however late.
        loan = next(iter(self.app.lib.active_loans()))
        self.app.lib.return_loan(
            loan.loan_id, on=loan.due_date + timedelta(days=12)
        )
        self.app._show("history")
        tree = [w for w in self._trees(self.app.main)][0]
        values = tree.item(tree.get_children()[0], "values")
        self.assertEqual(values[0], loan.loan_id)
        self.assertEqual(values[6], "6.00")     # 12 days at 50p

    def test_a_loan_returned_on_time_shows_nothing_owed(self):
        loan = next(iter(self.app.lib.active_loans()))
        self.app.lib.return_loan(loan.loan_id, on=loan.due_date)
        self.app._show("history")
        tree = [w for w in self._trees(self.app.main)][0]
        self.assertEqual(tree.item(tree.get_children()[0], "values")[6], "0.00")

    @staticmethod
    def _trees(widget):
        from lms.widgets import LTree
        for child in widget.winfo_children():
            if isinstance(child, LTree):
                yield child
            yield from HistoryPage._trees(child)


class Clock(AppCase):
    def test_moving_between_pages_does_not_multiply_the_timer(self):
        # Each visit to the dashboard used to start another `after` chain
        # without stopping the last, so the label ended up repainted once per
        # visit per second.
        self.app._show("dashboard")
        baseline = len(self.clock_jobs())
        for _ in range(6):
            self.app._show("books")
            self.app._show("dashboard")
        self.assertEqual(len(self.clock_jobs()), baseline)

    def test_closing_cancels_it(self):
        self.app._show("dashboard")
        self.assertIsNotNone(self.app._clk_job)
        self.app._on_close()
        self.assertIsNone(self.app._clk_job)


class Persistence(unittest.TestCase):
    @requires_display
    def test_a_second_launch_reads_what_the_first_wrote(self):
        from lms.app import LibraryApp
        path = temp_db_path()
        first = LibraryApp(path)
        first.withdraw()
        first.lib.add_book(Book("Persisted", "Author", "i", "Fiction", 2001))
        titles = {b.title for b in first.lib.books.values()}
        first.db.close()
        first.destroy()

        second = LibraryApp(path)
        second.withdraw()
        try:
            self.assertEqual({b.title for b in second.lib.books.values()}, titles)
            self.assertIn("Persisted", {b.title for b in second.lib.books.values()})
        finally:
            second.db.close()
            second.destroy()


if __name__ == "__main__":
    unittest.main()
