"""The rules: who may borrow, what may be removed, and what is owed.

This module holds every decision the program makes and imports no tkinter, so
all of it can be exercised against an in-memory database with no display.

The original kept the whole library in dictionaries and wrote to SQLite
separately, which gave it two sources of truth that had to be kept in step by
hand -- and they did come apart, most visibly when removing a book succeeded in
memory and then failed in the database. Here the dictionaries are a cache of
the database and nothing else: every change is written first, and the cache is
updated only once the write has returned.
"""

import sqlite3
from dataclasses import replace
from datetime import date, timedelta
from typing import Dict, List, Optional

from .models import (
    LOAN_PERIOD_DAYS,
    Book,
    Loan,
    Member,
    assess_fine,
    due_date_for,
    new_id,
)


class LibraryError(Exception):
    """A refusal the user should be told about, with the heading to show it under."""

    def __init__(self, title: str, message: str):
        super().__init__(message)
        self.title = title
        self.message = message


class Library:
    def __init__(self, db):
        self.db = db
        self.books: Dict[str, Book] = {}
        self.members: Dict[str, Member] = {}
        self.loans: Dict[str, Loan] = {}

    def load(self):
        self.books, self.members, self.loans = self.db.load()

    # -- views -----------------------------------------------------------

    def available_books(self) -> List[Book]:
        return [b for b in self.books.values() if b.available]

    def active_members(self) -> List[Member]:
        return [m for m in self.members.values() if m.active]

    def active_loans(self) -> List[Loan]:
        return [l for l in self.loans.values() if not l.returned]

    def completed_loans(self) -> List[Loan]:
        return [l for l in self.loans.values() if l.returned]

    def overdue_loans(self) -> List[Loan]:
        return [l for l in self.active_loans() if l.is_overdue]

    def loan_count(self, member_id: str) -> int:
        return sum(1 for l in self.loans.values() if l.member_id == member_id)

    def active_loans_for_member(self, member_id: str) -> List[Loan]:
        return [l for l in self.active_loans() if l.member_id == member_id]

    # -- catalogue -------------------------------------------------------

    def add_book(self, book: Book) -> Book:
        book.book_id = new_id("", 8, self.books)
        self.db.save_book(book)
        self.books[book.book_id] = book
        return book

    def add_member(self, member: Member) -> Member:
        member.member_id = new_id("M", 6, self.members)
        self.db.save_member(member)
        self.members[member.member_id] = member
        return member

    def remove_book(self, book_id: str):
        """Delete a book outright. Only ever legal for one nobody has borrowed.

        `loans.book_id` is a real foreign key, so a book that appears in the
        ledger cannot be deleted -- including for loans returned years ago.
        The original checked only whether the book was on loan *now*, so
        removing any book that had ever been borrowed and returned threw an
        IntegrityError out of a Tk callback, after the book had already been
        dropped from the in-memory catalogue: it vanished from the screen and
        came back on the next launch.

        A soft delete would let the history stand and the book disappear from
        the shelves, the way a deactivated member works. That needs somewhere
        on the Books page to say a title is withdrawn, which is a change to the
        interface, so this refuses instead and says why.
        """
        book = self.books.get(book_id)
        if book is None:
            raise LibraryError("Unknown Book", "That book is no longer in the catalogue.")
        if not book.available:
            raise LibraryError("Cannot Remove", f"'{book.title}' is currently on loan.")
        if self.db.loan_count_for_book(book_id):
            raise LibraryError(
                "Cannot Remove",
                f"'{book.title}' has loan history and cannot be removed.\n"
                "Deleting it would delete the record of who borrowed it.",
            )
        try:
            self.db.delete_book(book_id)
        except sqlite3.IntegrityError:
            raise LibraryError(
                "Cannot Remove",
                f"'{book.title}' is referenced by a loan record and cannot be removed.",
            ) from None
        del self.books[book_id]

    def deactivate_member(self, member_id: str):
        member = self.members.get(member_id)
        if member is None:
            raise LibraryError("Unknown Member", "That member is no longer registered.")
        open_loans = self.active_loans_for_member(member_id)
        if open_loans:
            raise LibraryError(
                "Cannot Deactivate",
                f"{member.name} has {len(open_loans)} active loan(s). "
                "Return all books first.",
            )
        self.db.save_member(replace(member, active=False))
        member.active = False

    # -- lending ---------------------------------------------------------

    def issue_loan(self, book_id: str, member_id: str, on: Optional[date] = None) -> Loan:
        on = on or date.today()
        book = self.books.get(book_id)
        if book is None:
            raise LibraryError("Unknown Book", "That book is no longer in the catalogue.")
        if not book.available:
            raise LibraryError("Not Available", f"'{book.title}' is already on loan.")
        member = self.members.get(member_id)
        if member is None:
            raise LibraryError("Unknown Member", "That member is no longer registered.")
        if not member.active:
            raise LibraryError(
                "Inactive Member", f"{member.name}'s membership is not active."
            )

        loan = Loan(
            book_id=book.book_id,
            member_id=member.member_id,
            # Copied deliberately: see the note on Loan.
            book_title=book.title,
            member_name=member.name,
            loan_id=new_id("L", 6, self.loans),
            loan_date=on,
            due_date=due_date_for(on),
        )
        # The row that goes to disk carries the new availability; the live
        # object is only changed once the transaction has committed, so a
        # failed write leaves the catalogue on screen telling the truth.
        self.db.record_loan(loan, replace(book, available=False))
        book.available = False
        self.loans[loan.loan_id] = loan
        return loan

    def return_loan(self, loan_id: str, on: Optional[date] = None) -> Loan:
        """Close a loan, put the book back, and record the fine that was due.

        The fine is worked out here, once, and stored on the row. The original
        had no fine column and computed the figure from today's date every time
        it was asked -- and refused to compute it at all for a returned loan,
        so the Loan History page's "Fine" column printed 0.00 for every loan
        that has ever been returned, however late.
        """
        on = on or date.today()
        loan = self.loans.get(loan_id)
        if loan is None:
            raise LibraryError("Unknown Loan", "That loan is no longer on record.")
        if loan.returned:
            raise LibraryError(
                "Already Returned",
                f"'{loan.book_title}' was returned on {loan.return_date}.",
            )
        book = self.books.get(loan.book_id)
        if book is None:
            raise LibraryError(
                "Unknown Book",
                f"'{loan.book_title}' is no longer in the catalogue; "
                "the loan cannot be closed.",
            )

        closed = replace(
            loan, returned=True, return_date=on, fine_pence=assess_fine(loan, on)
        )
        self.db.record_return(closed, replace(book, available=True))
        loan.returned = True
        loan.return_date = closed.return_date
        loan.fine_pence = closed.fine_pence
        book.available = True
        return loan

    # -- first run -------------------------------------------------------

    def seed_demo(self) -> bool:
        """Fill an empty library with something to look at. Returns whether it did.

        The original ran whenever the *books* table was empty, so emptying the
        catalogue of a library that still had members re-seeded the three demo
        members alongside the books, under fresh identifiers, every launch.
        """
        if self.books or self.members or self.loans:
            return False

        for book in [
            Book("The Great Gatsby", "F. Scott Fitzgerald", "978-0743273565", "Fiction", 1925),
            Book("To Kill a Mockingbird", "Harper Lee", "978-0061935466", "Fiction", 1960),
            Book("A Brief History of Time", "Stephen Hawking", "978-0553380163", "Science", 1988),
            Book("Clean Code", "Robert C. Martin", "978-0132350884", "Technology", 2008),
            Book("Sapiens", "Yuval Noah Harari", "978-0062316097", "History", 2011),
            Book("Dune", "Frank Herbert", "978-0441013593", "Fantasy", 1965),
            Book("The Pragmatic Programmer", "David Thomas", "978-0201616224", "Technology", 1999),
            Book("1984", "George Orwell", "978-0451524935", "Fiction", 1949),
        ]:
            self.add_book(book)
        for member in [
            Member("Alice Pemberton", "alice@example.com", "07700 900100"),
            Member("James Okafor", "james@example.com", "07700 900200"),
            Member("Sophie Chen", "sophie@example.com", "07700 900300"),
        ]:
            self.add_member(member)

        # One loan, three days overdue, so the dashboard has an overdue row.
        first_book = next(iter(self.books.values()))
        first_member = next(iter(self.members.values()))
        issued = date.today() - timedelta(days=LOAN_PERIOD_DAYS + 3)
        self.issue_loan(first_book.book_id, first_member.member_id, on=issued)
        return True
