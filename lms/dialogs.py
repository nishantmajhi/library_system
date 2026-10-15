"""The modal forms.

A dialog collects and validates input and leaves the answer on `self.result`.
It does not touch the database: what to do with the answer is decided in
library.py, and what to say about a refusal is decided in app.py.
"""

import tkinter as tk
from tkinter import messagebox, ttk
from datetime import date

from .models import (
    CURRENCY, LOAN_PERIOD_DAYS, Book, Member, due_date_for, valid_year,
)
from .theme import FB, FH, FSM, P
from .widgets import DBtn, GBtn, PBtn, PlaceholderEntry, SBtn, Sep


class BaseDialog(tk.Toplevel):
    def __init__(self, parent, title_text, accent=None, w=500, h=520):
        super().__init__(parent)
        self.title(title_text)
        self.configure(bg=P["bg"])
        self.geometry(f"{w}x{h}")
        self.resizable(False, False)
        self.result = None
        self.grab_set()
        self.transient(parent)
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()-w)//2
        py = parent.winfo_y() + (parent.winfo_height()-h)//2
        self.geometry(f"+{px}+{py}")
        self._accent = accent or P["accent"]
        self._build_chrome(title_text)

    def _build_chrome(self, title_text):
        # top colour stripe
        tk.Frame(self, bg=self._accent, height=5).pack(fill="x")
        # header area
        hdr = tk.Frame(self, bg=P["bg"])
        hdr.pack(fill="x", padx=28, pady=(20,0))
        tk.Label(hdr, text=title_text, bg=P["bg"], fg=P["text"], font=FH).pack(anchor="w")
        Sep(self).pack(fill="x", padx=28, pady=12)
        # body card
        self.body = tk.Frame(self, bg=P["surface"],
                             highlightbackground=P["border"], highlightthickness=1)
        self.body.pack(fill="both", expand=True, padx=28, pady=(0,0))
        # footer
        self.footer = tk.Frame(self, bg=P["bg"])
        self.footer.pack(fill="x", padx=28, pady=16)

    def field(self, label, placeholder=""):
        row = tk.Frame(self.body, bg=P["surface"])
        row.pack(fill="x", padx=16, pady=(10,0))
        tk.Label(row, text=label, bg=P["surface"], fg=P["text_muted"],
                 font=("Segoe UI",8,"bold")).pack(anchor="w", pady=(0,3))
        wrap = tk.Frame(row, bg=P["border"], pady=1, padx=1)
        wrap.pack(fill="x")
        inner = tk.Frame(wrap, bg=P["surface2"])
        inner.pack(fill="x")
        e = PlaceholderEntry(inner, placeholder=placeholder, bg=P["surface2"])
        e.pack(fill="x", padx=10, pady=7)
        return e

    def combo(self, label, values):
        row = tk.Frame(self.body, bg=P["surface"])
        row.pack(fill="x", padx=16, pady=(10,0))
        tk.Label(row, text=label, bg=P["surface"], fg=P["text_muted"],
                 font=("Segoe UI",8,"bold")).pack(anchor="w", pady=(0,3))
        var = tk.StringVar()
        cb = ttk.Combobox(row, values=values, textvariable=var,
                          state="readonly", style="L.TCombobox", font=FB)
        cb.pack(fill="x")
        return cb, var

    def info_box(self, text, color=None):
        color = color or P["accent"]
        box = tk.Frame(self.body, bg=P["accent_bg"], padx=12, pady=10)
        box.pack(fill="x", padx=16, pady=(10,4))
        tk.Label(box, text=text, bg=P["accent_bg"], fg=P["accent"], font=FSM,
                 wraplength=420, justify="left").pack(anchor="w")

    def add_footer_buttons(self, cancel_text="Cancel", ok_text="OK",
                           ok_cmd=None, ok_color="primary"):
        GBtn(self.footer, cancel_text, cmd=self.destroy).pack(side="left", padx=(0,8))
        maker = {"primary":PBtn,"success":SBtn,"danger":DBtn}.get(ok_color, PBtn)
        maker(self.footer, ok_text, cmd=ok_cmd or self._submit).pack(side="left")

    def _submit(self): pass


# ─────────────────────────────────────────────
#  SPECIFIC DIALOGS
# ─────────────────────────────────────────────

class AddBookDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, "Register New Book", accent=P["accent"], w=500, h=530)
        self.e_title  = self.field("BOOK TITLE",  "e.g. The Great Gatsby")
        self.e_author = self.field("AUTHOR",       "e.g. F. Scott Fitzgerald")
        self.e_isbn   = self.field("ISBN",         "e.g. 978-3-16-148410-0")
        self.e_year   = self.field("YEAR",         "e.g. 1925")
        self.cb_genre, self.v_genre = self.combo("GENRE", [
            "Fiction","Non-Fiction","Science","Technology","History",
            "Biography","Fantasy","Mystery","Romance","Self-Help","Other"])
        self.cb_genre.set("Fiction")
        tk.Frame(self.body, bg=P["surface"], height=12).pack()
        self.add_footer_buttons("Cancel","Register Book", ok_cmd=self._submit)

    def _submit(self):
        t = self.e_title.get_value().strip()
        a = self.e_author.get_value().strip()
        i = self.e_isbn.get_value().strip()
        y = self.e_year.get_value().strip()
        if not all([t,a,i,y]):
            messagebox.showerror("Missing Fields","Please fill in all fields.",parent=self); return
        if not valid_year(y):
            messagebox.showerror("Invalid Year","Enter a valid 4-digit year.",parent=self); return
        self.result = Book(title=t,author=a,isbn=i,genre=self.v_genre.get(),year=int(y))
        self.destroy()


class AddMemberDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, "Register New Member", accent=P["success"], w=500, h=430)
        self.e_name  = self.field("FULL NAME",     "e.g. Jane Smith")
        self.e_email = self.field("EMAIL ADDRESS", "e.g. jane@example.com")
        self.e_phone = self.field("PHONE NUMBER",  "e.g. 07700 900000")
        tk.Frame(self.body, bg=P["surface"], height=12).pack()
        self.add_footer_buttons("Cancel","Register Member", ok_cmd=self._submit, ok_color="success")

    def _submit(self):
        n = self.e_name.get_value().strip()
        e = self.e_email.get_value().strip()
        p = self.e_phone.get_value().strip()
        if not all([n,e,p]):
            messagebox.showerror("Missing Fields","Please fill in all fields.",parent=self); return
        if "@" not in e or "." not in e.split("@")[-1]:
            messagebox.showerror("Invalid Email","Enter a valid email address.",parent=self); return
        self.result = Member(name=n,email=e,phone=p)
        self.destroy()


class IssueLoanDialog(BaseDialog):
    def __init__(self, parent, books, members):
        super().__init__(parent,"Issue Book Loan", accent=P["warning"], w=520, h=420)
        self._bmap = {f"{b.title} — {b.author}  [{b.book_id}]": b.book_id for b in books}
        self._mmap = {f"{m.name}  [{m.member_id}]": m.member_id for m in members}
        self.cb_book, self.v_book   = self.combo("SELECT BOOK",   list(self._bmap.keys()))
        self.cb_mem,  self.v_member = self.combo("SELECT MEMBER", list(self._mmap.keys()))
        # Derived from the same constant the loan itself is dated from, so the
        # date promised here cannot drift from the date actually recorded.
        due = due_date_for(date.today()).strftime("%A, %d %B %Y")
        self.info_box(f"📅  Standard loan period: {LOAN_PERIOD_DAYS} days  ·  Due: {due}")
        tk.Frame(self.body, bg=P["surface"], height=8).pack()
        self.add_footer_buttons("Cancel","Issue Loan", ok_cmd=self._submit)

    def _submit(self):
        bl = self.v_book.get(); ml = self.v_member.get()
        if not bl or not ml:
            messagebox.showerror("Required","Select both a book and a member.",parent=self); return
        # The dialog names the pair; building the loan record is the library's
        # job, because only the library knows what identifiers are free and
        # whether the book is still on the shelf by the time OK is pressed.
        self.result = (self._bmap[bl], self._mmap[ml])
        self.destroy()


class ReturnDialog(BaseDialog):
    def __init__(self, parent, loans):
        super().__init__(parent,"Return a Book", accent=P["success"], w=520, h=380)
        self._lmap = {
            f"{l.loan_id}  ·  {l.book_title[:26]}  →  {l.member_name}"
            + ("  [OVERDUE]" if l.is_overdue else ""): l
            for l in loans}
        self.cb_loan, self.v_loan = self.combo("SELECT LOAN", list(self._lmap.keys()))
        self._fine_lbl = tk.Label(self.body, text="", bg=P["surface"],
                                  fg=P["danger"], font=FB)
        self._fine_lbl.pack(anchor="w", padx=16, pady=(6,0))
        self.v_loan.trace("w", self._on_sel)
        tk.Frame(self.body, bg=P["surface"], height=8).pack()
        self.add_footer_buttons("Cancel","Confirm Return", ok_cmd=self._submit, ok_color="success")

    def _on_sel(self, *_):
        lbl = self.v_loan.get()
        if lbl in self._lmap:
            l = self._lmap[lbl]
            self._fine_lbl.config(
                text=f"⚠  {l.days_overdue} day(s) overdue  ·  Fine: {CURRENCY}{l.fine_amount:.2f}"
                if l.is_overdue else "")

    def _submit(self):
        lbl = self.v_loan.get()
        if not lbl:
            messagebox.showerror("Required","Please select a loan.",parent=self); return
        loan = self._lmap[lbl]
        msg  = f"Confirm return of '{loan.book_title}' from {loan.member_name}?"
        if loan.is_overdue: msg += f"\n\n⚠  Fine payable: {CURRENCY}{loan.fine_amount:.2f}"
        if messagebox.askyesno("Confirm Return", msg, parent=self):
            self.result = loan.loan_id
            self.destroy()
