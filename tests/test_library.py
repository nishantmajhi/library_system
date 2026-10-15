"""The rules, and that the cache never disagrees with the database."""

import unittest
from datetime import date, timedelta

from helpers import LibraryCase, memory_library, raw_rows

from lms.library import LibraryError
from lms.models import FINE_PER_DAY_PENCE, LOAN_PERIOD_DAYS, Book, Member


class Registering(LibraryCase):
    def test_a_book_is_written_and_cached(self):
        b = self.lib.add_book(Book("1984", "Orwell", "i", "Fiction", 1949))
        self.assertIn(b.book_id, self.lib.books)
        self.assertEqual(self.lib.db.load()[0][b.book_id].title, "1984")

    def test_a_member_is_written_and_cached(self):
        m = self.lib.add_member(Member("Bob", "b@example.com", "p"))
        self.assertIn(m.member_id, self.lib.members)
        self.assertEqual(self.lib.db.load()[1][m.member_id].name, "Bob")

    def test_identifiers_do_not_collide_with_ones_in_use(self):
        for _ in range(50):
            self.lib.add_book(Book("t", "a", "i", "g", 2000))
        self.assertEqual(len(self.lib.books), 51)


class Issuing(LibraryCase):
    def test_a_loan_marks_the_book_unavailable(self):
        self.issue()
        self.assertFalse(self.lib.books[self.book.book_id].available)
        self.assertEqual(
            raw_rows(self.lib.db, "SELECT available FROM books")[0]["available"], 0
        )

    def test_the_due_date_is_the_loan_period_away(self):
        loan = self.issue()
        self.assertEqual(loan.due_date - loan.loan_date,
                         timedelta(days=LOAN_PERIOD_DAYS))

    def test_the_snapshot_columns_are_filled_from_the_records(self):
        loan = self.issue()
        self.assertEqual(loan.book_title, "Dune")
        self.assertEqual(loan.member_name, "Alice Pemberton")

    def test_a_book_already_out_cannot_be_issued_again(self):
        self.issue()
        with self.assertRaises(LibraryError) as caught:
            self.issue()
        self.assertEqual(caught.exception.title, "Not Available")

    def test_an_unknown_book_is_refused(self):
        with self.assertRaises(LibraryError) as caught:
            self.lib.issue_loan("NOSUCH", self.member.member_id)
        self.assertEqual(caught.exception.title, "Unknown Book")

    def test_an_unknown_member_is_refused(self):
        with self.assertRaises(LibraryError) as caught:
            self.lib.issue_loan(self.book.book_id, "NOSUCH")
        self.assertEqual(caught.exception.title, "Unknown Member")

    def test_a_deactivated_member_cannot_borrow(self):
        self.lib.deactivate_member(self.member.member_id)
        with self.assertRaises(LibraryError) as caught:
            self.issue()
        self.assertEqual(caught.exception.title, "Inactive Member")

    def test_a_refused_loan_changes_nothing(self):
        self.issue()
        before = raw_rows(self.lib.db, "SELECT * FROM loans")
        with self.assertRaises(LibraryError):
            self.issue()
        self.assertEqual(raw_rows(self.lib.db, "SELECT * FROM loans"), before)

    def test_the_title_on_the_loan_does_not_follow_a_later_correction(self):
        loan = self.issue()
        self.lib.books[self.book.book_id].title = "Dune Messiah"
        self.lib.db.save_book(self.lib.books[self.book.book_id])
        self.lib.load()
        self.assertEqual(self.lib.loans[loan.loan_id].book_title, "Dune")
        self.assertEqual(self.lib.books[self.book.book_id].title, "Dune Messiah")


class Returning(LibraryCase):
    def test_the_book_goes_back_on_the_shelf(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        self.assertTrue(self.lib.books[self.book.book_id].available)
        self.assertEqual(
            raw_rows(self.lib.db, "SELECT available FROM books")[0]["available"], 1
        )

    def test_the_loan_is_closed(self):
        loan = self.issue()
        closed = self.lib.return_loan(loan.loan_id, on=date(2026, 5, 1))
        self.assertTrue(closed.returned)
        self.assertEqual(closed.return_date, date(2026, 5, 1))
        self.assertEqual(self.lib.active_loans(), [])
        self.assertEqual([l.loan_id for l in self.lib.completed_loans()], [loan.loan_id])

    def test_no_fine_when_returned_on_time(self):
        loan = self.issue()
        closed = self.lib.return_loan(loan.loan_id, on=loan.due_date)
        self.assertEqual(closed.fine_pence, 0)

    def test_no_fine_when_returned_early(self):
        loan = self.issue()
        closed = self.lib.return_loan(loan.loan_id,
                                      on=loan.due_date - timedelta(days=3))
        self.assertEqual(closed.fine_pence, 0)

    def test_the_fine_is_charged_per_day_late(self):
        loan = self.issue()
        closed = self.lib.return_loan(loan.loan_id,
                                      on=loan.due_date + timedelta(days=9))
        self.assertEqual(closed.fine_pence, 9 * FINE_PER_DAY_PENCE)
        self.assertEqual(f"{closed.fine_amount:.2f}", "4.50")

    def test_the_fine_is_written_to_the_row(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id, on=loan.due_date + timedelta(days=9))
        self.assertEqual(
            raw_rows(self.lib.db, "SELECT fine_pence FROM loans")[0]["fine_pence"],
            9 * FINE_PER_DAY_PENCE,
        )

    def test_the_fine_survives_a_reload(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id, on=loan.due_date + timedelta(days=60))
        self.lib.load()
        reloaded = self.lib.loans[loan.loan_id]
        self.assertEqual(reloaded.fine_pence, 60 * FINE_PER_DAY_PENCE)
        self.assertEqual(f"{reloaded.fine_amount:.2f}", "30.00")

    def test_the_fine_does_not_keep_growing_after_the_book_is_back(self):
        loan = self.issue(days_ago=LOAN_PERIOD_DAYS + 2)
        closed = self.lib.return_loan(loan.loan_id)
        charged = closed.fine_pence
        self.lib.loans[loan.loan_id].due_date -= timedelta(days=1000)
        self.assertEqual(self.lib.loans[loan.loan_id].fine_pence_now, charged)

    def test_returning_twice_is_refused(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        with self.assertRaises(LibraryError) as caught:
            self.lib.return_loan(loan.loan_id)
        self.assertEqual(caught.exception.title, "Already Returned")

    def test_an_unknown_loan_is_refused(self):
        with self.assertRaises(LibraryError) as caught:
            self.lib.return_loan("NOSUCH")
        self.assertEqual(caught.exception.title, "Unknown Loan")

    def test_the_book_can_be_lent_again_afterwards(self):
        first = self.issue()
        self.lib.return_loan(first.loan_id)
        second = self.issue()
        self.assertNotEqual(first.loan_id, second.loan_id)
        self.assertEqual(len(self.lib.loans), 2)


class Removing(LibraryCase):
    def test_a_book_nobody_borrowed_can_be_removed(self):
        self.lib.remove_book(self.book.book_id)
        self.assertNotIn(self.book.book_id, self.lib.books)
        self.assertEqual(raw_rows(self.lib.db, "SELECT * FROM books"), [])

    def test_a_book_on_loan_is_refused(self):
        self.issue()
        with self.assertRaises(LibraryError) as caught:
            self.lib.remove_book(self.book.book_id)
        self.assertEqual(caught.exception.title, "Cannot Remove")
        self.assertIn("currently on loan", caught.exception.message)

    def test_a_book_with_loan_history_is_refused(self):
        # The headline crash: the book is available again, so the original's
        # only check passed, and the delete then broke the foreign key.
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        with self.assertRaises(LibraryError) as caught:
            self.lib.remove_book(self.book.book_id)
        self.assertEqual(caught.exception.title, "Cannot Remove")
        self.assertIn("loan history", caught.exception.message)

    def test_a_refused_removal_leaves_the_catalogue_intact(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        with self.assertRaises(LibraryError):
            self.lib.remove_book(self.book.book_id)
        self.assertIn(self.book.book_id, self.lib.books)
        self.assertEqual(len(raw_rows(self.lib.db, "SELECT * FROM books")), 1)
        self.lib.load()
        self.assertIn(self.book.book_id, self.lib.books)

    def test_removing_an_unknown_book_is_refused(self):
        with self.assertRaises(LibraryError) as caught:
            self.lib.remove_book("NOSUCH")
        self.assertEqual(caught.exception.title, "Unknown Book")

    def test_the_loan_record_still_names_the_removed_book(self):
        # A book with no history can go; nothing in the ledger refers to it.
        spare = self.lib.add_book(Book("Spare", "A", "i", "g", 2000))
        self.lib.remove_book(spare.book_id)
        self.assertEqual(self.lib.db.loan_count_for_book(spare.book_id), 0)


class Deactivating(LibraryCase):
    def test_a_member_with_nothing_out_can_be_deactivated(self):
        self.lib.deactivate_member(self.member.member_id)
        self.assertFalse(self.lib.members[self.member.member_id].active)
        self.assertEqual(
            raw_rows(self.lib.db, "SELECT active FROM members")[0]["active"], 0
        )

    def test_a_member_holding_a_book_is_refused(self):
        self.issue()
        with self.assertRaises(LibraryError) as caught:
            self.lib.deactivate_member(self.member.member_id)
        self.assertEqual(caught.exception.title, "Cannot Deactivate")
        self.assertIn("1 active loan(s)", caught.exception.message)

    def test_a_refused_deactivation_leaves_the_member_active(self):
        self.issue()
        with self.assertRaises(LibraryError):
            self.lib.deactivate_member(self.member.member_id)
        self.assertTrue(self.lib.members[self.member.member_id].active)
        self.assertEqual(
            raw_rows(self.lib.db, "SELECT active FROM members")[0]["active"], 1
        )

    def test_a_returned_loan_does_not_block_deactivation(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        self.lib.deactivate_member(self.member.member_id)
        self.assertFalse(self.lib.members[self.member.member_id].active)

    def test_an_unknown_member_is_refused(self):
        with self.assertRaises(LibraryError) as caught:
            self.lib.deactivate_member("NOSUCH")
        self.assertEqual(caught.exception.title, "Unknown Member")


class Views(LibraryCase):
    def test_counts_line_up_with_the_dashboard(self):
        self.assertEqual(len(self.lib.available_books()), 1)
        self.assertEqual(len(self.lib.active_loans()), 0)
        self.assertEqual(len(self.lib.overdue_loans()), 0)
        loan = self.issue(days_ago=LOAN_PERIOD_DAYS + 5)
        self.assertEqual(len(self.lib.available_books()), 0)
        self.assertEqual(len(self.lib.active_loans()), 1)
        self.assertEqual(len(self.lib.overdue_loans()), 1)
        self.lib.return_loan(loan.loan_id)
        self.assertEqual(len(self.lib.available_books()), 1)
        self.assertEqual(len(self.lib.active_loans()), 0)
        self.assertEqual(len(self.lib.overdue_loans()), 0)
        self.assertEqual(len(self.lib.completed_loans()), 1)

    def test_a_loan_within_its_period_is_not_overdue(self):
        self.issue(days_ago=LOAN_PERIOD_DAYS - 1)
        self.assertEqual(self.lib.overdue_loans(), [])

    def test_loan_count_counts_completed_loans_too(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        self.issue()
        self.assertEqual(self.lib.loan_count(self.member.member_id), 2)
        self.assertEqual(len(self.lib.active_loans_for_member(self.member.member_id)), 1)

    def test_active_members_excludes_deactivated_ones(self):
        self.lib.deactivate_member(self.member.member_id)
        self.assertEqual(self.lib.active_members(), [])


class Seeding(unittest.TestCase):
    def setUp(self):
        self.lib = memory_library()

    def tearDown(self):
        self.lib.db.close()

    def test_an_empty_library_is_seeded(self):
        self.assertTrue(self.lib.seed_demo())
        self.assertEqual(len(self.lib.books), 8)
        self.assertEqual(len(self.lib.members), 3)
        self.assertEqual(len(self.lib.loans), 1)

    def test_the_seeded_loan_is_three_days_overdue(self):
        self.lib.seed_demo()
        loan = next(iter(self.lib.loans.values()))
        self.assertEqual(loan.days_overdue, 3)
        self.assertEqual(loan.fine_pence_now, 3 * FINE_PER_DAY_PENCE)

    def test_seeding_is_not_repeated(self):
        self.lib.seed_demo()
        self.assertFalse(self.lib.seed_demo())
        self.assertEqual(len(self.lib.books), 8)

    def test_a_library_with_members_but_no_books_is_not_reseeded(self):
        # The original guarded on the books dictionary alone, so emptying the
        # catalogue re-registered the three demo members on every launch.
        self.lib.add_member(Member("Real Person", "r@example.com", "p"))
        self.assertFalse(self.lib.seed_demo())
        self.assertEqual(len(self.lib.members), 1)
        self.assertEqual(len(self.lib.books), 0)

    def test_a_library_with_history_but_no_books_is_not_reseeded(self):
        self.lib.seed_demo()
        for loan in list(self.lib.active_loans()):
            self.lib.return_loan(loan.loan_id)
        for book_id in list(self.lib.books):
            try:
                self.lib.remove_book(book_id)
            except LibraryError:
                pass
        self.assertFalse(self.lib.seed_demo())

    def test_the_seed_survives_a_reload(self):
        self.lib.seed_demo()
        self.lib.load()
        self.assertEqual(len(self.lib.books), 8)
        self.assertEqual(len(self.lib.loans), 1)
        self.assertEqual(len(self.lib.available_books()), 7)


class CacheAndDatabaseAgree(LibraryCase):
    """Every mutation, then a reload, and the two must match."""

    def reload_and_compare(self):
        cached = (dict(self.lib.books), dict(self.lib.members), dict(self.lib.loans))
        self.lib.load()
        self.assertEqual(cached[0], self.lib.books)
        self.assertEqual(cached[1], self.lib.members)
        self.assertEqual(cached[2], self.lib.loans)

    def test_after_adding(self):
        self.lib.add_book(Book("1984", "Orwell", "i", "Fiction", 1949))
        self.lib.add_member(Member("Bob", "b@example.com", "p"))
        self.reload_and_compare()

    def test_after_issuing(self):
        self.issue()
        self.reload_and_compare()

    def test_after_returning(self):
        loan = self.issue(days_ago=20)
        self.lib.return_loan(loan.loan_id)
        self.reload_and_compare()

    def test_after_removing(self):
        spare = self.lib.add_book(Book("Spare", "A", "i", "g", 2000))
        self.lib.remove_book(spare.book_id)
        self.reload_and_compare()

    def test_after_deactivating(self):
        self.lib.deactivate_member(self.member.member_id)
        self.reload_and_compare()

    def test_after_a_refusal(self):
        loan = self.issue()
        self.lib.return_loan(loan.loan_id)
        for attempt in (
            lambda: self.lib.remove_book(self.book.book_id),
            lambda: self.lib.return_loan(loan.loan_id),
            lambda: self.lib.deactivate_member("NOSUCH"),
        ):
            with self.assertRaises(LibraryError):
                attempt()
        self.reload_and_compare()


if __name__ == "__main__":
    unittest.main()
