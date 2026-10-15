"""Shared scaffolding for the suite."""

import sqlite3
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lms.db import Database            # noqa: E402
from lms.library import Library        # noqa: E402
from lms.models import Book, Member    # noqa: E402


def memory_library():
    """A Library over an in-memory database. No files, no display."""
    return Library(Database(":memory:"))


def temp_db_path(name="library.db"):
    return Path(tempfile.mkdtemp(prefix="lms-test-")) / name


class LibraryCase(unittest.TestCase):
    """A library holding one book and one member, ready to lend."""

    def setUp(self):
        self.lib = memory_library()
        self.book = self.lib.add_book(
            Book("Dune", "Frank Herbert", "978-0441013593", "Fantasy", 1965)
        )
        self.member = self.lib.add_member(
            Member("Alice Pemberton", "alice@example.com", "07700 900100")
        )

    def tearDown(self):
        self.lib.db.close()

    def issue(self, days_ago=0):
        """Issue the book, dated `days_ago` days in the past."""
        return self.lib.issue_loan(
            self.book.book_id, self.member.member_id,
            on=date.today() - timedelta(days=days_ago),
        )


def raw_rows(db, sql, params=()):
    """Read straight out of the database, bypassing the cache."""
    return [dict(r) for r in db._conn.execute(sql, params)]
