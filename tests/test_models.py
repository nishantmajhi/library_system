"""The records and the arithmetic hanging off them."""

import re
import unittest
from datetime import date, timedelta

from helpers import LibraryCase  # noqa: F401  (adds the project root to sys.path)

from lms.models import (
    CURRENCY,
    FINE_PER_DAY_PENCE,
    LOAN_PERIOD_DAYS,
    Book,
    Loan,
    Member,
    assess_fine,
    due_date_for,
    new_id,
    valid_year,
)


def loan_due(days_from_today, **kw):
    return Loan(
        book_id="B1", member_id="M1", book_title="Dune", member_name="Alice",
        due_date=date.today() + timedelta(days=days_from_today), **kw
    )


class Defaults(unittest.TestCase):
    def test_book_defaults(self):
        b = Book("Dune", "Frank Herbert", "978-0441013593", "Fantasy", 1965)
        self.assertTrue(b.available)
        self.assertEqual(b.date_added, date.today())
        self.assertRegex(b.book_id, r"^[0-9A-F]{8}$")

    def test_member_defaults(self):
        m = Member("Alice", "a@example.com", "07700 900100")
        self.assertTrue(m.active)
        self.assertEqual(m.date_joined, date.today())
        self.assertRegex(m.member_id, r"^M[0-9A-F]{6}$")

    def test_loan_defaults(self):
        l = Loan(book_id="B1", member_id="M1", book_title="Dune", member_name="Alice")
        self.assertFalse(l.returned)
        self.assertIsNone(l.return_date)
        self.assertEqual(l.fine_pence, 0)
        self.assertRegex(l.loan_id, r"^L[0-9A-F]{6}$")

    def test_default_due_date_is_the_loan_period_away(self):
        l = Loan(book_id="B1", member_id="M1", book_title="Dune", member_name="Alice")
        self.assertEqual(l.due_date - l.loan_date, timedelta(days=LOAN_PERIOD_DAYS))

    def test_dates_render_as_the_database_spells_them(self):
        # The pages print these straight into table cells, so `str` has to keep
        # producing exactly what the original's stored strings produced.
        self.assertEqual(f"{date(2026, 9, 19)}", "2026-09-19")


class Identifiers(unittest.TestCase):
    def test_shape_is_preserved(self):
        self.assertRegex(new_id("", 8), r"^[0-9A-F]{8}$")
        self.assertRegex(new_id("M", 6), r"^M[0-9A-F]{6}$")
        self.assertRegex(new_id("L", 6), r"^L[0-9A-F]{6}$")

    def test_never_returns_one_already_in_use(self):
        # Exhaust a one-character space: fifteen of the sixteen values are
        # taken, so the only legal answer is the sixteenth.
        taken = {"L" + c for c in "0123456789ABCDE"}
        self.assertEqual(new_id("L", 1, taken), "LF")

    def test_draws_differ(self):
        self.assertEqual(len({new_id("L", 6) for _ in range(500)}), 500)


class OverdueArithmetic(unittest.TestCase):
    def test_not_overdue_before_the_due_date(self):
        self.assertFalse(loan_due(+1).is_overdue)
        self.assertEqual(loan_due(+1).days_overdue, 0)

    def test_not_overdue_on_the_due_date(self):
        self.assertFalse(loan_due(0).is_overdue)
        self.assertEqual(loan_due(0).days_overdue, 0)

    def test_overdue_the_day_after(self):
        self.assertTrue(loan_due(-1).is_overdue)
        self.assertEqual(loan_due(-1).days_overdue, 1)

    def test_days_late_never_negative(self):
        l = loan_due(+30)
        self.assertEqual(l.days_late(date.today()), 0)

    def test_days_late_counts_from_the_due_date(self):
        l = loan_due(0)
        self.assertEqual(l.days_late(l.due_date + timedelta(days=7)), 7)


class Fines(unittest.TestCase):
    def test_no_fine_while_within_the_period(self):
        self.assertEqual(loan_due(+3).fine_pence_now, 0)
        self.assertEqual(loan_due(+3).fine_amount, 0.0)

    def test_open_loan_accrues_from_today(self):
        l = loan_due(-4)
        self.assertEqual(l.fine_pence_now, 4 * FINE_PER_DAY_PENCE)
        self.assertEqual(l.fine_amount, 2.0)

    def test_returned_loan_reports_the_sum_it_was_charged(self):
        # The headline regression: a returned loan must keep its fine. See
        # test_regressions.HistoryFine for the same case against the original.
        l = loan_due(-60, returned=True, return_date=date.today(), fine_pence=3000)
        self.assertEqual(l.days_overdue, 60)
        self.assertEqual(l.fine_pence_now, 3000)
        self.assertEqual(f"{l.fine_amount:.2f}", "30.00")

    def test_returned_loan_is_measured_at_the_return_date_not_today(self):
        # Brought back one day late a year ago: still one day, not 366.
        returned_on = date.today() - timedelta(days=365)
        l = Loan(book_id="B1", member_id="M1", book_title="Dune", member_name="Alice",
                 due_date=returned_on - timedelta(days=1),
                 returned=True, return_date=returned_on, fine_pence=FINE_PER_DAY_PENCE)
        self.assertEqual(l.days_overdue, 1)
        self.assertEqual(l.fine_amount, 0.50)

    def test_stored_fine_is_not_recomputed_from_the_current_rate(self):
        # A fine is what someone was asked to pay. Changing the rate later must
        # not rewrite it.
        l = loan_due(-10, returned=True, return_date=date.today(), fine_pence=1234)
        self.assertEqual(l.fine_pence_now, 1234)

    def test_assess_fine_is_the_rate_times_the_days(self):
        l = loan_due(0)
        for days in (0, 1, 2, 30, 365):
            with self.subTest(days=days):
                self.assertEqual(
                    assess_fine(l, l.due_date + timedelta(days=days)),
                    days * FINE_PER_DAY_PENCE,
                )

    def test_assess_fine_is_zero_when_returned_early(self):
        l = loan_due(0)
        self.assertEqual(assess_fine(l, l.due_date - timedelta(days=5)), 0)

    def test_money_is_exact_in_pence(self):
        # 0.1 + 0.2 arithmetic cannot creep in when the sum is an integer.
        l = loan_due(0)
        self.assertEqual(assess_fine(l, l.due_date + timedelta(days=3)), 150)
        self.assertIsInstance(assess_fine(l, l.due_date + timedelta(days=3)), int)

    def test_currency_is_named_once(self):
        self.assertEqual(CURRENCY, "£")


class DueDates(unittest.TestCase):
    def test_due_date_for(self):
        self.assertEqual(
            due_date_for(date(2026, 1, 1)),
            date(2026, 1, 1) + timedelta(days=LOAN_PERIOD_DAYS),
        )

    def test_crosses_a_month_boundary(self):
        self.assertEqual(due_date_for(date(2026, 1, 25)), date(2026, 2, 8))

    def test_crosses_a_leap_day(self):
        self.assertEqual(due_date_for(date(2028, 2, 20)), date(2028, 3, 5))


class YearValidation(unittest.TestCase):
    TODAY = date(2026, 9, 19)

    def test_accepts_a_plain_year(self):
        self.assertTrue(valid_year("1925", self.TODAY))

    def test_accepts_next_year(self):
        self.assertTrue(valid_year("2027", self.TODAY))

    def test_rejects_the_year_after_next(self):
        self.assertFalse(valid_year("2028", self.TODAY))

    def test_rejects_zero_and_negatives(self):
        self.assertFalse(valid_year("0", self.TODAY))
        self.assertFalse(valid_year("-100", self.TODAY))

    def test_rejects_nonsense(self):
        for text in ("", "   ", "nineteen", "19.25", "1925a", None):
            with self.subTest(text=text):
                self.assertFalse(valid_year(text, self.TODAY))

    def test_rejects_an_absurd_year(self):
        self.assertFalse(valid_year("99999", self.TODAY))


class SnapshotColumns(unittest.TestCase):
    def test_the_deliberate_denormalisation_is_documented(self):
        # The review asked for a decision: either drop the copies and join, or
        # declare them a point-in-time record. This asserts the decision is
        # written down where the next reader will find it, so the columns are
        # not quietly "tidied" later.
        self.assertIsNotNone(Loan.__doc__)
        self.assertIn("point-in-time", Loan.__doc__)
        self.assertRegex(Loan.__doc__, re.compile("receipt", re.I))


if __name__ == "__main__":
    unittest.main()
