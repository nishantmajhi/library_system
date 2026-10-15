"""SQLite persistence.

Every write that changes more than one row goes through one transaction, so
the catalogue and the loan ledger cannot half-apply: issuing a loan writes the
loan row and marks the book unavailable together or not at all.

The connection is opened once and kept. The original opened a fresh one per
call, which meant `PRAGMA journal_mode=WAL` was re-issued on every save and
nothing was ever closed.
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from .models import FINE_PER_DAY_PENCE, Book, Loan, Member

#: Where the database lives when nobody says otherwise: next to the program,
#: not next to whatever directory it happened to be launched from. The
#: original used a bare relative path, so starting the app from elsewhere
#: silently created a second, empty library.
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "library.db"

DATE_FORMAT = "%Y-%m-%d"

SCHEMA = """
    CREATE TABLE IF NOT EXISTS books (
        book_id    TEXT PRIMARY KEY,
        title      TEXT NOT NULL,
        author     TEXT NOT NULL,
        isbn       TEXT NOT NULL,
        genre      TEXT NOT NULL,
        year       INTEGER NOT NULL,
        available  INTEGER NOT NULL DEFAULT 1,
        date_added TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS members (
        member_id   TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        email       TEXT NOT NULL,
        phone       TEXT NOT NULL,
        date_joined TEXT NOT NULL,
        active      INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS loans (
        loan_id     TEXT PRIMARY KEY,
        book_id     TEXT NOT NULL,
        member_id   TEXT NOT NULL,
        book_title  TEXT NOT NULL,
        member_name TEXT NOT NULL,
        loan_date   TEXT NOT NULL,
        due_date    TEXT NOT NULL,
        return_date TEXT,
        returned    INTEGER NOT NULL DEFAULT 0,
        fine_pence  INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (book_id)   REFERENCES books(book_id),
        FOREIGN KEY (member_id) REFERENCES members(member_id)
    );
"""


class DataError(Exception):
    """A stored record cannot be read back. The message names the record."""


def parse_date(value, what: str, record: str) -> date:
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise DataError(
            f"{record} has an unreadable {what}: {value!r} "
            f"(expected a date written as YYYY-MM-DD)"
        ) from None


def format_date(value: Optional[date]) -> Optional[str]:
    return None if value is None else value.strftime(DATE_FORMAT)


class Database:
    """Owns the connection and the schema. Knows nothing about the rules."""

    def __init__(self, path=DEFAULT_DB_PATH):
        self.path = path if path == ":memory:" else Path(path)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        # WAL lets a reader (a sqlite3 shell, a backup) run while the app
        # writes. Foreign keys are off by default in SQLite and have to be
        # asked for on every connection.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()
        self._migrate()

    # -- setup -----------------------------------------------------------

    def _create_schema(self):
        with self._conn:
            self._conn.executescript(SCHEMA)

    def _columns(self, table: str):
        return {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self):
        """Bring a database written by an older version up to date."""
        if "fine_pence" not in self._columns("loans"):
            with self._conn:
                self._conn.execute(
                    "ALTER TABLE loans ADD COLUMN fine_pence INTEGER NOT NULL DEFAULT 0"
                )
                # Fines were never stored before, so every completed loan in an
                # existing database reads as zero. Both dates are on the row,
                # which means the charge can be reconstructed exactly rather
                # than written off. This runs once, when the column appears.
                self._conn.execute(
                    "UPDATE loans SET fine_pence = MAX(0, CAST(ROUND("
                    "  julianday(return_date) - julianday(due_date)"
                    ") AS INTEGER)) * ? "
                    "WHERE returned = 1 AND return_date IS NOT NULL",
                    (FINE_PER_DAY_PENCE,),
                )

    def close(self):
        self._conn.close()

    # -- reads -----------------------------------------------------------

    def load(self) -> Tuple[Dict[str, Book], Dict[str, Member], Dict[str, Loan]]:
        books = {}
        for r in self._conn.execute("SELECT * FROM books"):
            where = "book " + r["book_id"]
            books[r["book_id"]] = Book(
                title=r["title"], author=r["author"], isbn=r["isbn"],
                genre=r["genre"], year=r["year"], book_id=r["book_id"],
                available=bool(r["available"]),
                date_added=parse_date(r["date_added"], "date added", where),
            )

        members = {}
        for r in self._conn.execute("SELECT * FROM members"):
            where = "member " + r["member_id"]
            members[r["member_id"]] = Member(
                name=r["name"], email=r["email"], phone=r["phone"],
                member_id=r["member_id"],
                date_joined=parse_date(r["date_joined"], "join date", where),
                active=bool(r["active"]),
            )

        loans = {}
        for r in self._conn.execute("SELECT * FROM loans"):
            where = "loan " + r["loan_id"]
            return_date = (
                parse_date(r["return_date"], "return date", where)
                if r["return_date"] is not None
                else None
            )
            loans[r["loan_id"]] = Loan(
                book_id=r["book_id"], member_id=r["member_id"],
                book_title=r["book_title"], member_name=r["member_name"],
                loan_id=r["loan_id"],
                loan_date=parse_date(r["loan_date"], "loan date", where),
                due_date=parse_date(r["due_date"], "due date", where),
                return_date=return_date, returned=bool(r["returned"]),
                fine_pence=r["fine_pence"],
            )

        return books, members, loans

    def loan_count_for_book(self, book_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM loans WHERE book_id = ?", (book_id,)
        ).fetchone()
        return row["n"]

    # -- writes ----------------------------------------------------------

    _BOOK_UPSERT = """
        INSERT INTO books (book_id,title,author,isbn,genre,year,available,date_added)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(book_id) DO UPDATE SET
            title=excluded.title, author=excluded.author, isbn=excluded.isbn,
            genre=excluded.genre, year=excluded.year,
            available=excluded.available, date_added=excluded.date_added
    """

    @staticmethod
    def _book_row(book: Book):
        return (book.book_id, book.title, book.author, book.isbn, book.genre,
                book.year, int(book.available), format_date(book.date_added))

    def save_book(self, book: Book):
        with self._conn:
            self._conn.execute(self._BOOK_UPSERT, self._book_row(book))

    def save_member(self, member: Member):
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO members (member_id,name,email,phone,date_joined,active)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(member_id) DO UPDATE SET
                    name=excluded.name, email=excluded.email, phone=excluded.phone,
                    date_joined=excluded.date_joined, active=excluded.active
                """,
                (member.member_id, member.name, member.email, member.phone,
                 format_date(member.date_joined), int(member.active)),
            )

    def delete_book(self, book_id: str):
        with self._conn:
            self._conn.execute("DELETE FROM books WHERE book_id=?", (book_id,))

    def record_loan(self, loan: Loan, book: Book):
        """Write a new loan and mark its book unavailable, together.

        A plain INSERT, not an upsert: a loan identifier that already exists is
        a collision, and quietly updating the loan it collided with would lose
        the new loan and corrupt the old one.
        """
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO loans
                  (loan_id,book_id,member_id,book_title,member_name,
                   loan_date,due_date,return_date,returned,fine_pence)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (loan.loan_id, loan.book_id, loan.member_id, loan.book_title,
                 loan.member_name, format_date(loan.loan_date),
                 format_date(loan.due_date), format_date(loan.return_date),
                 int(loan.returned), loan.fine_pence),
            )
            self._conn.execute(self._BOOK_UPSERT, self._book_row(book))

    def record_return(self, loan: Loan, book: Book):
        """Close a loan and put its book back on the shelf, together.

        Only the columns a return changes are written. The title and member
        name on the row are the point-in-time record and are left alone.
        """
        with self._conn:
            self._conn.execute(
                "UPDATE loans SET returned=?, return_date=?, fine_pence=? "
                "WHERE loan_id=?",
                (int(loan.returned), format_date(loan.return_date),
                 loan.fine_pence, loan.loan_id),
            )
            self._conn.execute(self._BOOK_UPSERT, self._book_row(book))
