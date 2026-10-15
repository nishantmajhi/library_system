"""Records, and the arithmetic that hangs off them.

Dates are `datetime.date` objects here, not strings. They are parsed once, at
the database boundary in `db.py`, so a malformed date in the database is
reported when it is read -- naming the record -- rather than raising out of
whichever property happened to touch it first.

Money is integer pence. A fine is a sum someone is asked to pay, and it is
stored, not recomputed: see `Loan.fine_pence`.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


#: Days a loan runs for before it falls due. The due date shown in the issue
#: dialog and the due date stored on the loan are both derived from this, so
#: they cannot disagree.
LOAN_PERIOD_DAYS = 14

#: Overdue fine, in pence per day. Pence rather than pounds because this is
#: money; the display layer divides by 100 at the last moment.
FINE_PER_DAY_PENCE = 50

#: Currency symbol used when a fine is shown to a user.
CURRENCY = "\u00a3"


def new_id(prefix: str, length: int, taken=()) -> str:
    """A short random identifier that is not already in `taken`.

    The identifiers are displayed in fixed-width table columns, so the shape
    -- eight hex characters for a book, a letter and six for a member or a
    loan -- is part of the interface and is preserved. Six hex characters is
    only 24 bits, which is a coin-flip collision at about 4,800 records, so
    the caller passes the identifiers already in use and the draw is repeated
    until it lands on a free one.
    """
    while True:
        candidate = prefix + uuid.uuid4().hex[:length].upper()
        if candidate not in taken:
            return candidate


def _book_id() -> str:
    return new_id("", 8)


def _member_id() -> str:
    return new_id("M", 6)


def _loan_id() -> str:
    return new_id("L", 6)


@dataclass
class Book:
    title: str
    author: str
    isbn: str
    genre: str
    year: int
    book_id: str = field(default_factory=_book_id)
    available: bool = True
    date_added: date = field(default_factory=date.today)


@dataclass
class Member:
    name: str
    email: str
    phone: str
    member_id: str = field(default_factory=_member_id)
    date_joined: date = field(default_factory=date.today)
    active: bool = True


@dataclass
class Loan:
    """One book, one member, one borrowing.

    `book_title` and `member_name` are deliberate point-in-time copies, not a
    failure to normalise. A loan is a receipt: it records what was handed over
    and to whom, as those read on the day. Correcting a typo in a book's title
    afterwards must not rewrite what a member was given last year, so these
    columns are never updated once the row is written. Use `book_id` and
    `member_id` when you want the record as it stands today.
    """

    book_id: str
    member_id: str
    book_title: str
    member_name: str
    loan_id: str = field(default_factory=_loan_id)
    loan_date: date = field(default_factory=date.today)
    due_date: date = field(
        default_factory=lambda: date.today() + timedelta(days=LOAN_PERIOD_DAYS)
    )
    return_date: Optional[date] = None
    returned: bool = False
    #: Fine assessed when the book came back, in pence. Zero while the loan is
    #: open -- the accruing figure is `fine_pence_now`. Stored rather than
    #: recomputed so that changing FINE_PER_DAY_PENCE does not silently rewrite
    #: what past borrowers were charged.
    fine_pence: int = 0

    def days_late(self, on: date) -> int:
        """Days past the due date as at `on`, never negative."""
        return max(0, (on - self.due_date).days)

    @property
    def days_overdue(self) -> int:
        """How late this loan is, or was.

        For an open loan that is measured against today, so the number grows.
        For a returned loan it is measured against the day it came back, which
        is the figure the loan was actually charged on.
        """
        if self.returned:
            return self.days_late(self.return_date) if self.return_date else 0
        return self.days_late(date.today())

    @property
    def is_overdue(self) -> bool:
        return self.days_overdue > 0

    @property
    def fine_pence_now(self) -> int:
        """Pence owed: the sum charged if returned, the sum accruing if not."""
        if self.returned:
            return self.fine_pence
        return self.days_overdue * FINE_PER_DAY_PENCE

    @property
    def fine_amount(self) -> float:
        """`fine_pence_now` in pounds, for display only."""
        return self.fine_pence_now / 100.0


def assess_fine(loan: "Loan", on: date) -> int:
    """Pence owed if `loan` were returned on `on`."""
    return loan.days_late(on) * FINE_PER_DAY_PENCE


def due_date_for(loan_date: date) -> date:
    return loan_date + timedelta(days=LOAN_PERIOD_DAYS)


def valid_year(text: str, today: Optional[date] = None) -> bool:
    """Whether `text` is a publication year this catalogue will accept.

    A plain function rather than the `int()` plus `assert` inside a bare
    `try`/`except` it replaces. That construction had two faults: `assert` is
    compiled out under `python -O`, so the range check simply disappeared and
    any integer was accepted, and a bare `except` also catches KeyboardInterrupt.
    """
    today = today or date.today()
    try:
        year = int(text)
    except (TypeError, ValueError):
        return False
    return 1 <= year <= today.year + 1
