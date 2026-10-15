"""Schema, round-tripping, migration and atomicity."""

import sqlite3
import unittest
from datetime import date, timedelta

from helpers import raw_rows, temp_db_path

from lms.db import DEFAULT_DB_PATH, Database, DataError, format_date, parse_date
from lms.models import FINE_PER_DAY_PENCE, Book, Loan, Member


class Pragmas(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_foreign_keys_are_on(self):
        row = self.db._conn.execute("PRAGMA foreign_keys").fetchone()
        self.assertEqual(row[0], 1)

    def test_tables_exist(self):
        names = {
            r["name"]
            for r in self.db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertLessEqual({"books", "members", "loans"}, names)

    def test_loans_carries_a_fine_column(self):
        self.assertIn("fine_pence", self.db._columns("loans"))


class DefaultLocation(unittest.TestCase):
    def test_the_default_path_is_absolute(self):
        # The original's `DB_FILE = "library.db"` was relative to whatever
        # directory the app was started from, so launching it from elsewhere
        # silently created a second, empty library.
        self.assertTrue(DEFAULT_DB_PATH.is_absolute())

    def test_the_default_path_sits_beside_the_program(self):
        self.assertEqual(DEFAULT_DB_PATH.name, "library.db")
        self.assertTrue((DEFAULT_DB_PATH.parent / "lms").is_dir())


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_book(self):
        b = Book("Dune", "Frank Herbert", "978-0441013593", "Fantasy", 1965,
                 book_id="AAAA1111", available=False, date_added=date(2020, 3, 4))
        self.db.save_book(b)
        loaded = self.db.load()[0]["AAAA1111"]
        self.assertEqual(loaded, b)

    def test_member(self):
        m = Member("Alice", "a@example.com", "07700 900100",
                   member_id="MAAAAA", date_joined=date(2019, 12, 31), active=False)
        self.db.save_member(m)
        self.assertEqual(self.db.load()[1]["MAAAAA"], m)

    def test_loan(self):
        self.db.save_book(Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1"))
        self.db.save_member(Member("Alice", "a@e.com", "p", member_id="M1"))
        l = Loan(book_id="B1", member_id="M1", book_title="Dune", member_name="Alice",
                 loan_id="L00001", loan_date=date(2026, 1, 1), due_date=date(2026, 1, 15))
        self.db.record_loan(l, Book("Dune", "FH", "i", "Fantasy", 1965,
                                    book_id="B1", available=False))
        self.assertEqual(self.db.load()[2]["L00001"], l)

    def test_upsert_updates_rather_than_duplicates(self):
        b = Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1")
        self.db.save_book(b)
        b.title = "Dune Messiah"
        self.db.save_book(b)
        rows = raw_rows(self.db, "SELECT * FROM books")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Dune Messiah")


class DateColumns(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_dates_are_stored_in_the_original_text_format(self):
        # An existing library.db must still be readable, and sqlite3 on the
        # command line must still show dates the way it always did.
        self.db.save_book(Book("Dune", "FH", "i", "Fantasy", 1965,
                               book_id="B1", date_added=date(2026, 9, 19)))
        self.assertEqual(
            raw_rows(self.db, "SELECT date_added FROM books")[0]["date_added"],
            "2026-09-19",
        )

    def test_a_null_return_date_survives(self):
        self.assertIsNone(format_date(None))

    def test_parse_date_accepts_the_stored_format(self):
        self.assertEqual(parse_date("2026-09-19", "due date", "loan L1"), date(2026, 9, 19))

    def test_parse_date_names_the_record_it_could_not_read(self):
        with self.assertRaises(DataError) as caught:
            parse_date("19/09/2026", "due date", "loan L123456")
        self.assertIn("loan L123456", str(caught.exception))
        self.assertIn("due date", str(caught.exception))

    def test_parse_date_rejects_a_null(self):
        with self.assertRaises(DataError):
            parse_date(None, "due date", "loan L1")

    def test_a_bad_date_on_disk_is_reported_at_load(self):
        # The original parsed the string inside three separate properties, so a
        # damaged row raised ValueError out of whichever page touched it first,
        # with nothing in the message to say which loan was at fault.
        self.db.save_book(Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1"))
        self.db.save_member(Member("Alice", "a@e.com", "p", member_id="M1"))
        self.db.record_loan(
            Loan(book_id="B1", member_id="M1", book_title="Dune",
                 member_name="Alice", loan_id="LBAD01"),
            Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1", available=False),
        )
        with self.db._conn:
            self.db._conn.execute("UPDATE loans SET due_date='soon' WHERE loan_id='LBAD01'")
        with self.assertRaises(DataError) as caught:
            self.db.load()
        self.assertIn("loan LBAD01", str(caught.exception))


class Migration(unittest.TestCase):
    """An existing database, written before fines were stored."""

    OLD_SCHEMA = """
        CREATE TABLE books (
            book_id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL,
            isbn TEXT NOT NULL, genre TEXT NOT NULL, year INTEGER NOT NULL,
            available INTEGER NOT NULL DEFAULT 1, date_added TEXT NOT NULL);
        CREATE TABLE members (
            member_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
            phone TEXT NOT NULL, date_joined TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE loans (
            loan_id TEXT PRIMARY KEY, book_id TEXT NOT NULL, member_id TEXT NOT NULL,
            book_title TEXT NOT NULL, member_name TEXT NOT NULL, loan_date TEXT NOT NULL,
            due_date TEXT NOT NULL, return_date TEXT, returned INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (book_id) REFERENCES books(book_id),
            FOREIGN KEY (member_id) REFERENCES members(member_id));
    """

    def old_database(self, loans):
        path = temp_db_path()
        conn = sqlite3.connect(str(path))
        conn.executescript(self.OLD_SCHEMA)
        conn.execute(
            "INSERT INTO books VALUES ('B1','Dune','FH','i','Fantasy',1965,1,'2020-01-01')"
        )
        conn.execute(
            "INSERT INTO members VALUES ('M1','Alice','a@e.com','p','2020-01-01',1)"
        )
        for loan in loans:
            conn.execute(
                "INSERT INTO loans (loan_id,book_id,member_id,book_title,member_name,"
                "loan_date,due_date,return_date,returned) VALUES (?,?,?,?,?,?,?,?,?)",
                loan,
            )
        conn.commit()
        conn.close()
        return path

    def test_the_column_is_added(self):
        path = self.old_database([])
        db = Database(path)
        self.addCleanup(db.close)
        self.assertIn("fine_pence", db._columns("loans"))

    def test_historical_fines_are_reconstructed_from_the_two_stored_dates(self):
        # Both dates were always on the row, so the charge that was never
        # recorded can be worked out exactly rather than written off.
        path = self.old_database([
            ("L00001", "B1", "M1", "Dune", "Alice", "2026-01-01", "2026-01-15",
             "2026-02-04", 1),      # twenty days late
            ("L00002", "B1", "M1", "Dune", "Alice", "2026-01-01", "2026-01-15",
             "2026-01-10", 1),      # five days early
            ("L00003", "B1", "M1", "Dune", "Alice", "2026-01-01", "2026-01-15",
             None, 0),              # still out
        ])
        db = Database(path)
        self.addCleanup(db.close)
        loans = db.load()[2]
        self.assertEqual(loans["L00001"].fine_pence, 20 * FINE_PER_DAY_PENCE)
        self.assertEqual(loans["L00002"].fine_pence, 0)
        self.assertEqual(loans["L00003"].fine_pence, 0)

    def test_the_backfill_crosses_a_month_and_a_leap_day(self):
        path = self.old_database([
            ("L00001", "B1", "M1", "Dune", "Alice", "2028-02-01", "2028-02-15",
             "2028-03-01", 1),      # 15 days, through 29 February
        ])
        db = Database(path)
        self.addCleanup(db.close)
        self.assertEqual(db.load()[2]["L00001"].fine_pence, 15 * FINE_PER_DAY_PENCE)

    def test_migrating_twice_does_not_double_the_fines(self):
        path = self.old_database([
            ("L00001", "B1", "M1", "Dune", "Alice", "2026-01-01", "2026-01-15",
             "2026-02-04", 1),
        ])
        Database(path).close()
        db = Database(path)
        self.addCleanup(db.close)
        self.assertEqual(db.load()[2]["L00001"].fine_pence, 20 * FINE_PER_DAY_PENCE)

    def test_a_current_database_is_left_alone(self):
        path = temp_db_path()
        Database(path).close()
        db = Database(path)
        self.addCleanup(db.close)
        self.assertIn("fine_pence", db._columns("loans"))


class ForeignKeys(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.save_book(Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1"))
        self.db.save_member(Member("Alice", "a@e.com", "p", member_id="M1"))

    def tearDown(self):
        self.db.close()

    def loan(self, loan_id="L00001", **kw):
        return Loan(book_id="B1", member_id="M1", book_title="Dune",
                    member_name="Alice", loan_id=loan_id, **kw)

    def test_a_loan_must_point_at_a_real_book(self):
        bad = self.loan()
        bad.book_id = "NOPE"
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.record_loan(bad, Book("x", "y", "z", "g", 1, book_id="NOPE"))

    def test_deleting_a_borrowed_book_is_refused_by_the_database(self):
        self.db.record_loan(self.loan(), Book("Dune", "FH", "i", "Fantasy", 1965,
                                              book_id="B1", available=False))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.delete_book("B1")

    def test_loan_count_for_book(self):
        self.assertEqual(self.db.loan_count_for_book("B1"), 0)
        self.db.record_loan(self.loan(), Book("Dune", "FH", "i", "Fantasy", 1965,
                                              book_id="B1", available=False))
        self.assertEqual(self.db.loan_count_for_book("B1"), 1)


class Atomicity(unittest.TestCase):
    """Two rows change together or not at all."""

    def setUp(self):
        self.db = Database(":memory:")
        self.db.save_book(Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1"))
        self.db.save_member(Member("Alice", "a@e.com", "p", member_id="M1"))

    def tearDown(self):
        self.db.close()

    def test_a_duplicate_loan_id_is_refused_outright(self):
        # The original upserted, so a second loan drawing an identifier that
        # was already in use quietly overwrote the first loan's return state
        # and was itself never written.
        unavailable = Book("Dune", "FH", "i", "Fantasy", 1965,
                           book_id="B1", available=False)
        first = Loan(book_id="B1", member_id="M1", book_title="Dune",
                     member_name="Alice", loan_id="LSAME1")
        self.db.record_loan(first, unavailable)
        second = Loan(book_id="B1", member_id="M1", book_title="Dune",
                      member_name="Bob", loan_id="LSAME1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.record_loan(second, unavailable)
        rows = raw_rows(self.db, "SELECT member_name FROM loans")
        self.assertEqual([r["member_name"] for r in rows], ["Alice"])

    def test_a_rejected_loan_leaves_the_book_on_the_shelf(self):
        unavailable = Book("Dune", "FH", "i", "Fantasy", 1965,
                           book_id="B1", available=False)
        self.db.record_loan(
            Loan(book_id="B1", member_id="M1", book_title="Dune",
                 member_name="Alice", loan_id="LSAME1"), unavailable)
        with self.db._conn:
            self.db._conn.execute("UPDATE books SET available=1 WHERE book_id='B1'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.record_loan(
                Loan(book_id="B1", member_id="M1", book_title="Dune",
                     member_name="Bob", loan_id="LSAME1"), unavailable)
        self.assertEqual(
            raw_rows(self.db, "SELECT available FROM books")[0]["available"], 1
        )

    def test_a_return_writes_the_loan_and_the_book_together(self):
        self.db.record_loan(
            Loan(book_id="B1", member_id="M1", book_title="Dune",
                 member_name="Alice", loan_id="L00001",
                 due_date=date(2026, 1, 15)),
            Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1", available=False))
        closed = Loan(book_id="B1", member_id="M1", book_title="Dune",
                      member_name="Alice", loan_id="L00001",
                      due_date=date(2026, 1, 15), returned=True,
                      return_date=date(2026, 1, 20), fine_pence=250)
        self.db.record_return(closed, Book("Dune", "FH", "i", "Fantasy", 1965,
                                           book_id="B1", available=True))
        loans = raw_rows(self.db, "SELECT * FROM loans")
        self.assertEqual(loans[0]["returned"], 1)
        self.assertEqual(loans[0]["return_date"], "2026-01-20")
        self.assertEqual(loans[0]["fine_pence"], 250)
        self.assertEqual(
            raw_rows(self.db, "SELECT available FROM books")[0]["available"], 1
        )

    def test_a_return_does_not_rewrite_the_snapshot_columns(self):
        self.db.record_loan(
            Loan(book_id="B1", member_id="M1", book_title="Dune",
                 member_name="Alice", loan_id="L00001"),
            Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1", available=False))
        tampered = Loan(book_id="B1", member_id="M1", book_title="WRONG",
                        member_name="WRONG", loan_id="L00001", returned=True,
                        return_date=date.today())
        self.db.record_return(tampered, Book("Dune", "FH", "i", "Fantasy", 1965,
                                             book_id="B1", available=True))
        row = raw_rows(self.db, "SELECT book_title, member_name FROM loans")[0]
        self.assertEqual(row["book_title"], "Dune")
        self.assertEqual(row["member_name"], "Alice")


class Persistence(unittest.TestCase):
    def test_a_database_survives_being_closed_and_reopened(self):
        path = temp_db_path()
        db = Database(path)
        db.save_book(Book("Dune", "FH", "i", "Fantasy", 1965, book_id="B1",
                          date_added=date(2026, 9, 19)))
        db.close()
        reopened = Database(path)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.load()[0]["B1"].date_added, date(2026, 9, 19))


if __name__ == "__main__":
    unittest.main()
