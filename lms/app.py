"""The window, the pages and the wiring.

Everything here is presentation. The rules live in library.py; this module
asks for a decision, and shows whatever comes back.
"""

import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime

from . import __version__
from .db import DataError, Database
from .dialogs import AddBookDialog, AddMemberDialog, IssueLoanDialog, ReturnDialog
from .library import Library, LibraryError
from .theme import FB, FBD, FS, FSM, FT, P
from .widgets import LTree, PBtn, PlaceholderEntry, SBtn, Sep, StatCard, _styled_ttk


class LibraryApp(tk.Tk):
    def __init__(self, db_path=None):
        super().__init__()
        self.title("LMS  ·  Library Management System")
        self.configure(bg=P["bg"])
        self.geometry("1200x780")
        self.minsize(1020, 660)
        _styled_ttk()
        self.db = Database(db_path) if db_path else Database()
        self.lib = Library(self.db)
        self.lib.load()
        self.lib.seed_demo()
        self._build_sidebar()
        self._build_main()
        self._current = None
        self._clk = None
        self._clk_job = None
        self._show("dashboard")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # The pages read the catalogue through these. There is one copy of the
    # data, held by the Library, and it is a cache of the database.
    @property
    def books(self):
        return self.lib.books

    @property
    def members(self):
        return self.lib.members

    @property
    def loans(self):
        return self.lib.loans

    # ── Clock tick (used by dashboard) ──────────
    def _tick(self):
        """Repaint the dashboard clock once a second.

        Each visit to the dashboard used to start a fresh chain of `after`
        callbacks without stopping the one already running, so a session that
        moved between pages ended up with as many timers as it had visits, all
        painting the same label. The pending job is cancelled first.
        """
        if self._clk_job is not None:
            self.after_cancel(self._clk_job)
            self._clk_job = None
        if self._clk and self._clk.winfo_exists():
            self._clk.config(text=datetime.now().strftime("%A %d %B %Y  ·  %H:%M:%S"))
            self._clk_job = self.after(1000, self._tick)

    # ── Sidebar ───────────────────────────────
    def _build_sidebar(self):
        self.sb = tk.Frame(self, bg=P["sidebar"], width=210)
        self.sb.pack(side="left", fill="y"); self.sb.pack_propagate(False)
        tk.Frame(self.sb, bg=P["border"], width=1).pack(side="right", fill="y")

        self._nav_btns = {}
        tk.Label(self.sb, text="NAVIGATION", bg=P["sidebar"],
                 fg=P["text_dim"], font=FBD).pack(anchor="w", padx=18, pady=(24,8))

        for pid, lbl in [("dashboard","⊞   Dashboard"),("books","📖   Books"),
                         ("members","👥   Members"),("loans","🔖   Active Loans"),
                         ("history","📋   Loan History")]:
            b = tk.Button(self.sb, text=lbl, bg=P["sidebar"], fg=P["text_muted"],
                          activebackground=P["nav_active"], activeforeground=P["accent"],
                          font=FB, relief="flat", bd=0, anchor="w",
                          padx=18, pady=11, cursor="hand2",
                          command=lambda p=pid: self._show(p))
            b.pack(fill="x")
            self._nav_btns[pid] = b

        Sep(self.sb).pack(fill="x", padx=14, pady=16)
        tk.Label(self.sb, text="QUICK ACTIONS", bg=P["sidebar"],
                 fg=P["text_dim"], font=FBD).pack(anchor="w", padx=18, pady=(0,8))

        for lbl, cmd in [("➕   Add Book",   self._add_book),
                         ("➕   Add Member", self._add_member),
                         ("📤   Issue Loan", self._issue_loan)]:
            tk.Button(self.sb, text=lbl, bg=P["sidebar"], fg=P["text_muted"],
                      activebackground=P["nav_active"], activeforeground=P["accent"],
                      font=FSM, relief="flat", bd=0, anchor="w",
                      padx=18, pady=8, cursor="hand2", command=cmd).pack(fill="x")

        tk.Label(self.sb, text=f"LMS v{__version__}", bg=P["sidebar"],
                 fg=P["text_dim"], font=("Segoe UI",8)).pack(side="bottom", pady=14)

    def _set_nav(self, pid):
        for p, b in self._nav_btns.items():
            if p == pid:
                b.config(bg=P["nav_active"], fg=P["accent"],
                         font=("Segoe UI",10,"bold"))
            else:
                b.config(bg=P["sidebar"], fg=P["text_muted"], font=FB)

    # ── Main area ─────────────────────────────
    def _build_main(self):
        self.main = tk.Frame(self, bg=P["bg"])
        self.main.pack(side="left", fill="both", expand=True)

    def _clear(self):
        for w in self.main.winfo_children(): w.destroy()

    def _show(self, pid):
        self._current = pid
        self._set_nav(pid)
        self._clear()
        {"dashboard":self._pg_dashboard,"books":self._pg_books,
         "members":self._pg_members,"loans":self._pg_loans,
         "history":self._pg_history}[pid]()

    # ── Shared page header ────────────────────
    def _page_hdr(self, parent, title, subtitle=None):
        hdr = tk.Frame(parent, bg=P["bg"])
        hdr.pack(fill="x", pady=(0,6))
        tk.Label(hdr, text=title, bg=P["bg"], fg=P["text"], font=FT).pack(side="left")
        if subtitle:
            tk.Label(hdr, text=f"  {subtitle}", bg=P["bg"],
                     fg=P["text_muted"], font=("Segoe UI",13)).pack(side="left", pady=(8,0))
        Sep(parent).pack(fill="x", pady=(4,16))
        return hdr

    def _section_hdr(self, parent, title, color):
        f = tk.Frame(parent, bg=P["surface"])
        f.pack(fill="x", padx=12, pady=(12,6))
        tk.Frame(f, bg=color, width=3, height=16).pack(side="left")
        tk.Label(f, text=f"  {title}", bg=P["surface"],
                 fg=P["text"], font=FS).pack(side="left")
        Sep(parent).pack(fill="x", padx=12, pady=(0,6))

    # ─────────────────────────────────────────
    #  PAGE: DASHBOARD
    # ─────────────────────────────────────────
    def _pg_dashboard(self):
        p = tk.Frame(self.main, bg=P["bg"])
        p.pack(fill="both", expand=True, padx=30, pady=26)

        # Dashboard header with live clock on the right
        hdr = tk.Frame(p, bg=P["bg"])
        hdr.pack(fill="x", pady=(0,6))
        tk.Label(hdr, text="Dashboard", bg=P["bg"], fg=P["text"], font=FT).pack(side="left")
        self._clk = tk.Label(hdr, bg=P["bg"], fg=P["text_muted"], font=FSM)
        self._clk.pack(side="right", pady=(10,0))
        self._tick()
        Sep(p).pack(fill="x", pady=(4,16))

        active  = self.lib.active_loans()
        overdue = self.lib.overdue_loans()
        avail   = self.lib.available_books()

        # Stat cards
        grid = tk.Frame(p, bg=P["bg"])
        grid.pack(fill="x")
        grid.columnconfigure((0,1,2,3), weight=1, uniform="sc")
        cards_data = [
            ("Total Books",   len(self.books),  P["accent"],  P["accent_bg"],  "📚"),
            ("Available",     len(avail),        P["success"], P["success_bg"], "✅"),
            ("Active Loans",  len(active),       P["warning"], P["warning_bg"], "🔖"),
            ("Overdue",       len(overdue),      P["danger"],  P["danger_bg"],  "⚠️"),
        ]
        for i,(lbl,val,col,bgc,ico) in enumerate(cards_data):
            c = StatCard(grid, lbl, val, col, bgc, ico)
            c.grid(row=0, column=i, sticky="ew",
                   padx=(0,14) if i<3 else 0, ipady=4)

        # Lower two columns
        low = tk.Frame(p, bg=P["bg"])
        low.pack(fill="both", expand=True, pady=(18,0))
        low.columnconfigure(0, weight=3)
        low.columnconfigure(1, weight=2)
        low.rowconfigure(0, weight=1)

        # Active loans card
        lc = tk.Frame(low, bg=P["surface"],
                      highlightbackground=P["border"], highlightthickness=1)
        lc.grid(row=0, column=0, sticky="nsew", padx=(0,14))
        self._section_hdr(lc, "Active Loans", P["warning"])

        dash_sf = tk.Frame(lc, bg=P["surface"])
        dash_sf.pack(fill="both", expand=True, padx=12, pady=(0,12))
        dash_sb = ttk.Scrollbar(dash_sf, orient="vertical", style="L.Vertical.TScrollbar")
        dash_sb.pack(side="right", fill="y")
        tree = LTree(dash_sf, ("id","book","member","due","status"),
                     ("Loan ID","Book","Member","Due Date","Status"),
                     col_widths=[75,175,130,105,80])
        tree.configure(yscrollcommand=dash_sb.set)
        dash_sb.configure(command=tree.yview)
        rows = []
        for l in active:
            st = "OVERDUE" if l.is_overdue else "On Loan"
            rows.append((l.loan_id, (l.loan_id, l.book_title[:22],
                                      l.member_name, l.due_date, st)))
        tree.refill(rows, tag_fn=lambda v,i: "overdue" if v[4]=="OVERDUE" else ("alt" if i%2 else ""))
        tree.pack(side="left", fill="both", expand=True)

        # Recent books card
        rc = tk.Frame(low, bg=P["surface"],
                      highlightbackground=P["border"], highlightthickness=1)
        rc.grid(row=0, column=1, sticky="nsew")
        self._section_hdr(rc, "Recently Added", P["accent"])

        recent = sorted(self.books.values(), key=lambda b: b.date_added, reverse=True)[:10]
        for i, book in enumerate(recent):
            row = tk.Frame(rc, bg=P["surface"] if i%2==0 else P["row_alt"])
            row.pack(fill="x", padx=12, pady=0)
            dot_col = P["success"] if book.available else P["warning"]
            tk.Label(row, text="●", bg=row["bg"], fg=dot_col,
                     font=("Segoe UI",8)).pack(side="left", padx=(6,4), pady=8)
            tk.Label(row, text=book.title[:26], bg=row["bg"],
                     fg=P["text"], font=FB, anchor="w").pack(side="left",fill="x",expand=True)
            tk.Label(row, text=book.genre, bg=row["bg"],
                     fg=P["text_dim"], font=FSM).pack(side="right", padx=8)

    # ─────────────────────────────────────────
    #  PAGE: BOOKS
    # ─────────────────────────────────────────
    def _pg_books(self):
        p = tk.Frame(self.main, bg=P["bg"])
        p.pack(fill="both", expand=True, padx=30, pady=26)
        hdr = self._page_hdr(p, "Books", f"{len(self.books)} titles")

        # Search + button
        self._bsearch = tk.StringVar()
        self._bsearch.trace_add("write", lambda *_: self._fill_books())
        self._bfilter = tk.StringVar(value="all")

        PBtn(hdr, "＋  Add Book", cmd=self._add_book).pack(side="right")

        # Search bar
        se_wrap = tk.Frame(hdr, bg=P["border"], padx=1, pady=1)
        se_wrap.pack(side="right", padx=(0,10))
        se_inner = tk.Frame(se_wrap, bg=P["surface"])
        se_inner.pack(fill="both", expand=True)
        se = PlaceholderEntry(se_inner, placeholder="🔍  Search title or author…",
                              textvariable=self._bsearch, bg=P["surface"],
                              font=FB, width=26)
        se.pack(fill="both", expand=True, padx=10, pady=8)

        # Filter pills
        pf = tk.Frame(p, bg=P["bg"])
        pf.pack(anchor="w", pady=(0,12))
        for lbl,val in [("All","all"),("Available","available"),("On Loan","on_loan")]:
            tk.Radiobutton(pf, text=lbl, variable=self._bfilter, value=val,
                           command=self._fill_books,
                           bg=P["bg"], fg=P["text_muted"],
                           selectcolor=P["bg"], activebackground=P["bg"],
                           activeforeground=P["accent"],
                           font=FSM, indicator=0, relief="flat",
                           padx=12, pady=5, cursor="hand2").pack(side="left", padx=(0,6))

        sf = tk.Frame(p, bg=P["bg"])
        sf.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(sf, orient="vertical", style="L.Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        self._btree = LTree(sf,
            ("id","title","author","isbn","genre","year","added","status"),
            ("Book ID","Title","Author","ISBN","Genre","Year","Date Added","Status"),
            col_widths=[80,200,150,140,90,60,100,80])
        self._btree.configure(yscrollcommand=sb.set)
        sb.configure(command=self._btree.yview)
        self._btree.pack(side="left", fill="both", expand=True)

        ctx = tk.Menu(self, tearoff=0, bg=P["surface"], fg=P["text"],
                      activebackground=P["accent_bg"], activeforeground=P["accent"],
                      bd=0, relief="flat")
        ctx.add_command(label="Issue Loan",  command=self._issue_loan)
        ctx.add_separator()
        ctx.add_command(label="Remove Book", command=self._remove_book)
        self._btree.bind("<Button-3>", lambda e: self._popup(e, ctx))
        self._fill_books()

    def _fill_books(self):
        if not hasattr(self,"_btree"): return
        raw = self._bsearch.get() if hasattr(self,"_bsearch") else ""
        q   = "" if (not raw or raw.startswith("🔍")) else raw.lower()
        flt = self._bfilter.get() if hasattr(self,"_bfilter") else "all"
        rows = []
        for b in self.books.values():
            if q and q not in b.title.lower() and q not in b.author.lower(): continue
            if flt=="available" and not b.available: continue
            if flt=="on_loan"   and b.available:     continue
            st = "Available" if b.available else "On Loan"
            rows.append((b.book_id,(b.book_id,b.title,b.author,b.isbn,
                                    b.genre,b.year,b.date_added,st)))
        self._btree.refill(rows, tag_fn=lambda v,i:
            "on_loan" if v[7]=="On Loan" else ("alt" if i%2 else ""))

    # ─────────────────────────────────────────
    #  PAGE: MEMBERS
    # ─────────────────────────────────────────
    def _pg_members(self):
        p = tk.Frame(self.main, bg=P["bg"])
        p.pack(fill="both", expand=True, padx=30, pady=26)
        hdr = self._page_hdr(p, "Members", f"{len(self.members)} registered")

        self._msearch = tk.StringVar()
        self._msearch.trace_add("write", lambda *_: self._fill_members())
        SBtn(hdr, "＋  Add Member", cmd=self._add_member).pack(side="right")

        se_wrap = tk.Frame(hdr, bg=P["border"], padx=1, pady=1)
        se_wrap.pack(side="right", padx=(0,10))
        se_inner = tk.Frame(se_wrap, bg=P["surface"])
        se_inner.pack(fill="both", expand=True)
        se = PlaceholderEntry(se_inner, placeholder="🔍  Search name or email…",
                              textvariable=self._msearch, bg=P["surface"],
                              font=FB, width=26)
        se.pack(fill="both", expand=True, padx=10, pady=6)

        sf = tk.Frame(p, bg=P["bg"])
        sf.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(sf, orient="vertical", style="L.Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        self._mtree = LTree(sf,
            ("id","name","email","phone","joined","loans","status"),
            ("Member ID","Full Name","Email","Phone","Joined","Total Loans","Status"),
            col_widths=[90,160,200,120,100,80,80])
        self._mtree.configure(yscrollcommand=sb.set)
        sb.configure(command=self._mtree.yview)
        self._mtree.pack(side="left", fill="both", expand=True)

        ctx = tk.Menu(self, tearoff=0, bg=P["surface"], fg=P["text"],
                      activebackground=P["danger_bg"], activeforeground=P["danger"],
                      bd=0, relief="flat")
        ctx.add_command(label="Deactivate Member", command=self._deactivate_member)
        self._mtree.bind("<Button-3>", lambda e: self._popup(e, ctx))
        self._fill_members()

    def _fill_members(self):
        if not hasattr(self,"_mtree"): return
        raw = self._msearch.get() if hasattr(self,"_msearch") else ""
        q = "" if (not raw or raw.startswith("🔍")) else raw.lower()
        rows = []
        for m in self.members.values():
            if q and q not in m.name.lower() and q not in m.email.lower(): continue
            lc = self.lib.loan_count(m.member_id)
            rows.append((m.member_id,(m.member_id,m.name,m.email,m.phone,
                                      m.date_joined,lc,
                                      "Active" if m.active else "Inactive")))
        self._mtree.refill(rows, tag_fn=lambda v,i:
            "muted" if v[6]=="Inactive" else ("alt" if i%2 else ""))

    # ─────────────────────────────────────────
    #  PAGE: ACTIVE LOANS
    # ─────────────────────────────────────────
    def _pg_loans(self):
        p = tk.Frame(self.main, bg=P["bg"])
        p.pack(fill="both", expand=True, padx=30, pady=26)
        hdr = self._page_hdr(p,"Active Loans",
                              f"{len(self.lib.active_loans())} active")
        SBtn(hdr, "📥  Return Book", cmd=self._return_book).pack(side="right")
        PBtn(hdr, "📤  Issue Loan",  cmd=self._issue_loan).pack(side="right", padx=(0,10))

        sf = tk.Frame(p, bg=P["bg"])
        sf.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(sf, orient="vertical", style="L.Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        self._ltree = LTree(sf,
            ("id","book","member","issued","due","overdue","fine","status"),
            ("Loan ID","Book","Member","Issued","Due Date","Days Overdue","Fine (£)","Status"),
            col_widths=[80,185,140,100,100,100,80,80])
        self._ltree.configure(yscrollcommand=sb.set)
        sb.configure(command=self._ltree.yview)
        self._ltree.pack(side="left", fill="both", expand=True)
        self._fill_loans()

    def _fill_loans(self):
        if not hasattr(self,"_ltree"): return
        rows=[]
        for l in [x for x in self.loans.values() if not x.returned]:
            st = "OVERDUE" if l.is_overdue else "On Loan"
            rows.append((l.loan_id,(l.loan_id, l.book_title[:22], l.member_name,
                                    l.loan_date, l.due_date,
                                    l.days_overdue if l.days_overdue else "-",
                                    f"{l.fine_amount:.2f}" if l.fine_amount else "-",
                                    st)))
        self._ltree.refill(rows, tag_fn=lambda v,i:
            "overdue" if v[7]=="OVERDUE" else ("alt" if i%2 else ""))

    # ─────────────────────────────────────────
    #  PAGE: HISTORY
    # ─────────────────────────────────────────
    def _pg_history(self):
        p = tk.Frame(self.main, bg=P["bg"])
        p.pack(fill="both", expand=True, padx=30, pady=26)
        ret = self.lib.completed_loans()
        self._page_hdr(p, "Loan History", f"{len(ret)} completed loans")

        sf = tk.Frame(p, bg=P["bg"])
        sf.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(sf, orient="vertical", style="L.Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        tree = LTree(sf,
            ("id","book","member","issued","due","returned","fine"),
            ("Loan ID","Book","Member","Issued","Due Date","Returned On","Fine (£)"),
            col_widths=[80,200,150,100,100,110,80])
        tree.configure(yscrollcommand=sb.set)
        sb.configure(command=tree.yview)
        rows = [(l.loan_id,(l.loan_id,l.book_title,l.member_name,
                            l.loan_date,l.due_date,
                            l.return_date or "-",
                            f"{l.fine_amount:.2f}" if l.fine_amount else "0.00"))
                for l in ret]
        tree.refill(rows, tag_fn=lambda v,i: "alt" if i%2 else "")
        tree.pack(side="left", fill="both", expand=True)

    # ─────────────────────────────────────────
    #  ACTIONS
    # ─────────────────────────────────────────
    def _popup(self, e, menu):
        try: menu.tk_popup(e.x_root, e.y_root)
        finally: menu.grab_release()

    def _add_book(self):
        d = AddBookDialog(self); self.wait_window(d)
        if d.result:
            b = self.lib.add_book(d.result)
            messagebox.showinfo("Book Registered",
                f"✅  '{b.title}' added to catalogue.\nID: {b.book_id}")
            self._show(self._current)

    def _add_member(self):
        d = AddMemberDialog(self); self.wait_window(d)
        if d.result:
            m = self.lib.add_member(d.result)
            messagebox.showinfo("Member Registered",
                f"✅  {m.name} registered.\nID: {m.member_id}")
            self._show(self._current)

    def _issue_loan(self):
        avail = self.lib.available_books()
        actm  = self.lib.active_members()
        if not avail:
            messagebox.showwarning("No Books","No books available to loan."); return
        if not actm:
            messagebox.showwarning("No Members","No active members. Register one first."); return
        d = IssueLoanDialog(self, avail, actm); self.wait_window(d)
        if d.result:
            book_id, member_id = d.result
            try:
                loan = self.lib.issue_loan(book_id, member_id)
            except LibraryError as err:
                messagebox.showerror(err.title, err.message); return
            messagebox.showinfo("Loan Issued",
                f"✅  '{loan.book_title}' issued to {loan.member_name}.\n"
                f"Loan ID: {loan.loan_id}  ·  Due: {loan.due_date}")
            self._show(self._current)

    def _return_book(self):
        active = self.lib.active_loans()
        if not active:
            messagebox.showinfo("No Active Loans","Nothing to return."); return
        d = ReturnDialog(self, active); self.wait_window(d)
        if d.result:
            try:
                loan = self.lib.return_loan(d.result)
            except LibraryError as err:
                messagebox.showerror(err.title, err.message); return
            messagebox.showinfo("Returned",
                f"✅  '{loan.book_title}' returned.\nThank you, {loan.member_name}!")
            self._show(self._current)

    def _remove_book(self):
        sel = self._btree.selection() if hasattr(self,"_btree") else ()
        if not sel:
            messagebox.showinfo("No Selection","Right-click a book row first."); return
        b = self.books.get(sel[0])
        if not b: return
        # Both refusals are decided before the confirmation prompt, so a book
        # that cannot be removed is never first offered for removal. The
        # library checks them again: this is the wording, not the rule.
        if not b.available:
            messagebox.showerror("Cannot Remove",f"'{b.title}' is currently on loan."); return
        if self.db.loan_count_for_book(b.book_id):
            messagebox.showerror("Cannot Remove",
                f"'{b.title}' has loan history and cannot be removed.\n"
                "Deleting it would delete the record of who borrowed it."); return
        if messagebox.askyesno("Confirm Removal",
                f"Remove '{b.title}' from the catalogue?\nThis cannot be undone."):
            try:
                self.lib.remove_book(b.book_id)
            except LibraryError as err:
                messagebox.showerror(err.title, err.message); return
            self._show("books")

    def _deactivate_member(self):
        sel = self._mtree.selection() if hasattr(self,"_mtree") else ()
        if not sel:
            messagebox.showinfo("No Selection","Right-click a member row first."); return
        m = self.members.get(sel[0])
        if not m: return
        al = self.lib.active_loans_for_member(m.member_id)
        if al:
            messagebox.showerror("Cannot Deactivate",
                f"{m.name} has {len(al)} active loan(s). Return all books first."); return
        if messagebox.askyesno("Confirm", f"Deactivate {m.name}'s membership?"):
            try:
                self.lib.deactivate_member(m.member_id)
            except LibraryError as err:
                messagebox.showerror(err.title, err.message); return
            self._show("members")

    def _on_close(self):
        if self._clk_job is not None:
            self.after_cancel(self._clk_job)
            self._clk_job = None
        self.db.close()
        self.destroy()


def main(db_path=None):
    """Start the application. Returns the process exit status."""
    try:
        app = LibraryApp(db_path)
    except DataError as err:
        # A date in the database that cannot be read. Say which record, rather
        # than letting it raise out of a property while a page is being drawn.
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Library data cannot be read", str(err))
        root.destroy()
        return 1
    app.mainloop()
    return 0
