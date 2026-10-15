"""LMS — a Tkinter library management system backed by SQLite.

The package is split so that every decision the program makes can be tested
without a display:

    models.py    the records, and the arithmetic that hangs off them
    db.py        SQLite schema, migration and the unit-of-work writes
    library.py   the rules: who may borrow, what may be removed, what is owed
    theme.py     palette and fonts
    widgets.py   the custom Tk widgets
    dialogs.py   the modal forms
    app.py       the window, the pages and the wiring

Only the last three import tkinter.
"""

#: Shown in the sidebar. One definition, so it cannot go stale in one
#: place and stay right in another.
__version__ = "1.1.0"
