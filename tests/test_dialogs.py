"""The four modal forms.

These are where the contract with app.py lives: what a dialog leaves on
`self.result`. IssueLoanDialog used to build a whole Loan record and now returns
the pair of identifiers it was asked to choose; ReturnDialog used to hand back
the Loan object and now returns its id. Both are called by exactly one line in
app.py, so nothing else would notice if they drifted.

`messagebox` is replaced for the duration, because a real one would block
waiting for a click. The replacement records what would have been shown, which
is how the validation messages are asserted.
"""

import unittest
from datetime import date, timedelta

from helpers import memory_library
from test_app import requires_display

from lms.models import CURRENCY, LOAN_PERIOD_DAYS, Book, Member


class FakeMessagebox:
    """Stands in for tkinter.messagebox. `answer` is what askyesno returns."""

    def __init__(self, answer=True):
        self.shown = []
        self.answer = answer

    def showerror(self, title, message, **kw):
        self.shown.append(("error", title, message))

    def showinfo(self, title, message, **kw):
        self.shown.append(("info", title, message))

    def showwarning(self, title, message, **kw):
        self.shown.append(("warning", title, message))

    def askyesno(self, title, message, **kw):
        self.shown.append(("askyesno", title, message))
        return self.answer

    def titles(self):
        return [entry[1] for entry in self.shown]

    def last_message(self):
        return self.shown[-1][2]


def fill(entry, text):
    """Type into a PlaceholderEntry the way a user would."""
    entry._clear_ph()
    entry.delete(0, "end")
    entry.insert(0, text)


@requires_display
class DialogCase(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from lms import dialogs
        from lms.widgets import _styled_ttk

        self.root = tk.Tk()
        self.root.withdraw()
        _styled_ttk()
        self.box = FakeMessagebox()
        self.real_messagebox = dialogs.messagebox
        dialogs.messagebox = self.box
        self.addCleanup(self._restore)

    def _restore(self):
        from lms import dialogs
        dialogs.messagebox = self.real_messagebox
        try:
            self.root.destroy()
        except Exception:
            pass

    def make(self, cls, *args):
        dialog = cls(self.root, *args)
        dialog.withdraw()
        self.addCleanup(lambda: self._safe_destroy(dialog))
        return dialog

    @staticmethod
    def _safe_destroy(dialog):
        try:
            dialog.destroy()
        except Exception:
            pass


class AddBook(DialogCase):
    def dialog(self, title="Dune", author="Frank Herbert",
               isbn="978-0441013593", year="1965"):
        from lms.dialogs import AddBookDialog
        d = self.make(AddBookDialog)
        fill(d.e_title, title)
        fill(d.e_author, author)
        fill(d.e_isbn, isbn)
        fill(d.e_year, year)
        return d

    def test_a_complete_form_produces_a_book(self):
        d = self.dialog()
        d._submit()
        self.assertIsInstance(d.result, Book)
        self.assertEqual(d.result.title, "Dune")
        self.assertEqual(d.result.year, 1965)
        self.assertEqual(d.result.genre, "Fiction")   # the default in the combo
        self.assertEqual(self.box.shown, [])

    def test_a_missing_field_is_refused(self):
        d = self.dialog(author="")
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Missing Fields"])

    def test_whitespace_is_not_a_field(self):
        d = self.dialog(title="   ")
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Missing Fields"])

    def test_a_year_that_is_not_a_number_is_refused(self):
        d = self.dialog(year="nineteen sixty-five")
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Invalid Year"])

    def test_a_year_too_far_ahead_is_refused(self):
        d = self.dialog(year=str(date.today().year + 2))
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Invalid Year"])

    def test_next_year_is_accepted(self):
        d = self.dialog(year=str(date.today().year + 1))
        d._submit()
        self.assertIsInstance(d.result, Book)

    def test_the_year_is_stored_as_an_integer(self):
        d = self.dialog(year="1965")
        d._submit()
        self.assertIsInstance(d.result.year, int)


class AddMember(DialogCase):
    def dialog(self, name="Alice Pemberton", email="alice@example.com",
               phone="07700 900100"):
        from lms.dialogs import AddMemberDialog
        d = self.make(AddMemberDialog)
        fill(d.e_name, name)
        fill(d.e_email, email)
        fill(d.e_phone, phone)
        return d

    def test_a_complete_form_produces_a_member(self):
        d = self.dialog()
        d._submit()
        self.assertIsInstance(d.result, Member)
        self.assertEqual(d.result.name, "Alice Pemberton")
        self.assertTrue(d.result.active)

    def test_a_missing_field_is_refused(self):
        d = self.dialog(phone="")
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Missing Fields"])

    def test_an_address_with_no_at_sign_is_refused(self):
        d = self.dialog(email="alice.example.com")
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Invalid Email"])

    def test_an_address_with_no_dot_after_the_at_sign_is_refused(self):
        d = self.dialog(email="alice@localhost")
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Invalid Email"])


class IssueLoan(DialogCase):
    def setUp(self):
        super().setUp()
        self.lib = memory_library()
        self.addCleanup(self.lib.db.close)
        self.book = self.lib.add_book(Book("Dune", "Frank Herbert", "i", "Fantasy", 1965))
        self.member = self.lib.add_member(Member("Alice", "a@example.com", "p"))

    def dialog(self):
        from lms.dialogs import IssueLoanDialog
        return self.make(IssueLoanDialog,
                         self.lib.available_books(), self.lib.active_members())

    def test_it_returns_the_pair_of_identifiers(self):
        d = self.dialog()
        d.v_book.set(next(iter(d._bmap)))
        d.v_member.set(next(iter(d._mmap)))
        d._submit()
        self.assertEqual(d.result, (self.book.book_id, self.member.member_id))

    def test_the_pair_is_what_the_library_accepts(self):
        d = self.dialog()
        d.v_book.set(next(iter(d._bmap)))
        d.v_member.set(next(iter(d._mmap)))
        d._submit()
        loan = self.lib.issue_loan(*d.result)
        self.assertEqual(loan.book_title, "Dune")

    def test_choosing_nothing_is_refused(self):
        d = self.dialog()
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Required"])

    def test_choosing_only_a_book_is_refused(self):
        d = self.dialog()
        d.v_book.set(next(iter(d._bmap)))
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Required"])

    def test_the_labels_carry_the_identifier_so_two_titles_alike_differ(self):
        self.lib.add_book(Book("Dune", "Frank Herbert", "i", "Fantasy", 1965))
        d = self.dialog()
        self.assertEqual(len(d._bmap), 2)
        self.assertEqual(len(set(d._bmap.values())), 2)

    def test_the_promised_due_date_is_the_date_the_loan_actually_gets(self):
        # The info box used to hard-code "14 days" and its own
        # `datetime.now() + timedelta(days=14)` alongside the model's separate
        # default, so the date promised on screen and the date written to the
        # row could drift apart. This reads the promise off the widget and the
        # answer off the loan.
        d = self.dialog()
        promised = self.info_box_text(d)
        d.v_book.set(next(iter(d._bmap)))
        d.v_member.set(next(iter(d._mmap)))
        d._submit()
        loan = self.lib.issue_loan(*d.result)
        self.assertIn(f"{LOAN_PERIOD_DAYS} days", promised)
        self.assertIn(loan.due_date.strftime("%A, %d %B %Y"), promised)

    @staticmethod
    def info_box_text(dialog):
        import tkinter as tk

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    yield child.cget("text")
                yield from walk(child)

        matches = [text for text in walk(dialog.body) if "loan period" in text]
        assert len(matches) == 1, f"expected one info box, found {len(matches)}"
        return matches[0]


class Return(DialogCase):
    def setUp(self):
        super().setUp()
        self.lib = memory_library()
        self.addCleanup(self.lib.db.close)
        self.book = self.lib.add_book(Book("Dune", "Frank Herbert", "i", "Fantasy", 1965))
        self.member = self.lib.add_member(Member("Alice", "a@example.com", "p"))

    def issue(self, days_ago=0):
        return self.lib.issue_loan(self.book.book_id, self.member.member_id,
                                   on=date.today() - timedelta(days=days_ago))

    def dialog(self, answer=True):
        from lms.dialogs import ReturnDialog
        self.box.answer = answer
        return self.make(ReturnDialog, self.lib.active_loans())

    def test_it_returns_the_loan_identifier(self):
        loan = self.issue()
        d = self.dialog()
        d.v_loan.set(next(iter(d._lmap)))
        d._submit()
        self.assertEqual(d.result, loan.loan_id)

    def test_the_identifier_is_what_the_library_accepts(self):
        self.issue()
        d = self.dialog()
        d.v_loan.set(next(iter(d._lmap)))
        d._submit()
        closed = self.lib.return_loan(d.result)
        self.assertTrue(closed.returned)

    def test_choosing_nothing_is_refused(self):
        self.issue()
        d = self.dialog()
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(self.box.titles(), ["Required"])

    def test_declining_the_confirmation_keeps_the_loan_open(self):
        self.issue()
        d = self.dialog(answer=False)
        d.v_loan.set(next(iter(d._lmap)))
        d._submit()
        self.assertIsNone(d.result)
        self.assertEqual(len(self.lib.active_loans()), 1)

    def test_an_overdue_loan_is_labelled_and_priced(self):
        self.issue(days_ago=LOAN_PERIOD_DAYS + 4)
        d = self.dialog()
        label = next(iter(d._lmap))
        self.assertIn("[OVERDUE]", label)
        d.v_loan.set(label)
        d._on_sel()
        shown = d._fine_lbl.cget("text")
        self.assertIn("4 day(s) overdue", shown)
        self.assertIn(f"{CURRENCY}2.00", shown)

    def test_the_confirmation_names_the_fine(self):
        self.issue(days_ago=LOAN_PERIOD_DAYS + 4)
        d = self.dialog()
        d.v_loan.set(next(iter(d._lmap)))
        d._submit()
        message = self.box.last_message()
        self.assertIn("Dune", message)
        self.assertIn(f"{CURRENCY}2.00", message)

    def test_a_loan_within_its_period_shows_no_fine(self):
        self.issue()
        d = self.dialog()
        label = next(iter(d._lmap))
        self.assertNotIn("[OVERDUE]", label)
        d.v_loan.set(label)
        d._on_sel()
        self.assertEqual(d._fine_lbl.cget("text"), "")


if __name__ == "__main__":
    unittest.main()
