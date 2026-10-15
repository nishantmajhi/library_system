"""The custom Tk widgets.

None of this has anything to do with libraries -- it is a small toolkit of
rounded frames, placeholder entries, styled buttons, stat cards and a themed
Treeview that happens to live in this program.
"""

import tkinter as tk
from tkinter import ttk

from .theme import FB, FS, FSM, P, rounded_rect


class RoundedFrame(tk.Canvas):
    """A frame with rounded corners drawn via canvas."""
    def __init__(self, parent, bg=None, radius=12, border_color=None, **kwargs):
        self._bg     = bg or P["surface"]
        self._radius = radius
        self._border = border_color or P["border"]
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        super().__init__(parent, bg=parent.cget("bg") if hasattr(parent,"cget") else P["bg"], **kwargs)
        self.bind("<Configure>", self._redraw)
        self._rect = None
        self._inner = tk.Frame(self, bg=self._bg)

    def _redraw(self, e=None):
        self.delete("bg_rect")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4: return
        rounded_rect(self, 1, 1, w-1, h-1, r=self._radius,
                     fill=self._bg, outline=self._border, width=1, tags="bg_rect")
        self._inner.place(x=self._radius//2+2, y=self._radius//2+2,
                          width=w-self._radius-4, height=h-self._radius-4)

    def interior(self):
        return self._inner


class PlaceholderEntry(tk.Entry):
    def __init__(self, parent, placeholder="", **kw):
        self._tvar = kw.get("textvariable", None)
        kw.setdefault("bg", P["surface2"])
        kw.setdefault("fg", P["text"])
        kw.setdefault("insertbackground", P["accent"])
        kw.setdefault("relief", "flat")
        kw.setdefault("bd", 0)
        kw.setdefault("font", FB)
        super().__init__(parent, **kw)
        self.placeholder = placeholder
        self._ph = False
        if placeholder:
            self._show_ph()
            self.bind("<FocusIn>",  self._clear_ph)
            self.bind("<FocusOut>", self._restore_ph)

    def _show_ph(self):
        if self._tvar:
            self._tvar.set(self.placeholder)
        else:
            self.insert(0, self.placeholder)
        self.config(fg=P["text_dim"])
        self._ph = True

    def _clear_ph(self, _=None):
        if self._ph:
            if self._tvar:
                self._tvar.set("")
            else:
                self.delete(0, tk.END)
            self.config(fg=P["text"])
            self._ph = False

    def _restore_ph(self, _=None):
        val = self._tvar.get() if self._tvar else self.get()
        if not val:
            self._show_ph()

    def get_value(self):
        return "" if self._ph else self.get()


def _styled_ttk():
    """Apply a fully light ttk style — call once at startup."""
    s = ttk.Style()
    s.theme_use("clam")

    # Treeview
    s.configure("L.Treeview",
                 background=P["surface"], foreground=P["text"],
                 fieldbackground=P["surface"], borderwidth=0,
                 font=FB, rowheight=36)
    s.configure("L.Treeview.Heading",
                 background=P["head_bg"], foreground=P["text_muted"],
                 borderwidth=0, font=("Segoe UI",9,"bold"), relief="flat")
    s.map("L.Treeview",
          background=[("selected", P["accent_bg"])],
          foreground=[("selected", P["accent"])])
    s.map("L.Treeview.Heading",
          background=[("active", P["border"])])

    # Scrollbar — flat light
    s.configure("L.Vertical.TScrollbar",
                 troughcolor=P["bg"], background=P["border"],
                 borderwidth=0, arrowsize=0, relief="flat")
    s.map("L.Vertical.TScrollbar",
          background=[("active", P["text_dim"]), ("!active", P["border"])])

    # Combobox
    s.configure("L.TCombobox",
                 fieldbackground=P["surface2"], background=P["surface2"],
                 foreground=P["text"], arrowcolor=P["accent"],
                 bordercolor=P["border"], lightcolor=P["border"],
                 darkcolor=P["border"], relief="flat", padding=6)
    s.map("L.TCombobox",
          fieldbackground=[("readonly", P["surface2"])],
          selectbackground=[("readonly", P["surface2"])],
          selectforeground=[("readonly", P["text"])])


# ─────────────────────────────────────────────
#  BUTTON HELPERS
# ─────────────────────────────────────────────

def _btn(parent, text, cmd, bg, fg, hover, **kw):
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                  activebackground=hover, activeforeground=fg,
                  font=FS, relief="flat", bd=0, cursor="hand2",
                  padx=12, pady=4, **kw)
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b

def PBtn(parent, text, cmd=None, **kw):
    return _btn(parent, text, cmd, P["accent"],   P["white"], P["accent_dark"], **kw)
def SBtn(parent, text, cmd=None, **kw):
    return _btn(parent, text, cmd, P["success"],  P["white"], "#15A272", **kw)
def DBtn(parent, text, cmd=None, **kw):
    return _btn(parent, text, cmd, P["danger"],   P["white"], "#D43232", **kw)
def GBtn(parent, text, cmd=None, **kw):
    return _btn(parent, text, cmd, P["surface2"], P["text_muted"], P["border"], **kw)


def Sep(parent, **kw):
    return tk.Frame(parent, bg=P["border"], height=1, **kw)


# ─────────────────────────────────────────────
#  STAT CARD
# ─────────────────────────────────────────────

class StatCard(tk.Frame):
    def __init__(self, parent, label, value, color, bg_color, icon=""):
        super().__init__(parent, bg=P["surface"],
                         highlightbackground=P["border"], highlightthickness=1)
        # left accent bar
        tk.Frame(self, bg=color, width=4).pack(side="left", fill="y")
        body = tk.Frame(self, bg=P["surface"])
        body.pack(side="left", fill="both", expand=True, padx=16, pady=16)

        top = tk.Frame(body, bg=P["surface"])
        top.pack(fill="x")

        icon_bg = tk.Frame(top, bg=bg_color, padx=8, pady=6)
        icon_bg.pack(side="left")
        tk.Label(icon_bg, text=icon, bg=bg_color, fg=color, font=("Segoe UI",16)).pack()

        self._val = tk.Label(top, text=str(value), bg=P["surface"],
                             fg=P["text"], font=("Segoe UI",26,"bold"))
        self._val.pack(side="right", anchor="e")

        tk.Label(body, text=label, bg=P["surface"],
                 fg=P["text_muted"], font=FSM).pack(anchor="w", pady=(6,0))

    def set_value(self, v):
        """Change the figure. Deliberately not called `update`: that is
        `tk.Misc.update`, and overriding it with a method that needs an
        argument leaves a widget whose standard redraw call raises TypeError."""
        self._val.config(text=str(v))


# ─────────────────────────────────────────────
#  TREEVIEW WRAPPER
# ─────────────────────────────────────────────

class LTree(ttk.Treeview):
    def __init__(self, parent, columns, headings, col_widths=None, **kw):
        super().__init__(parent, columns=columns, show="headings",
                         style="L.Treeview", **kw)
        for i,(col,hd) in enumerate(zip(columns, headings)):
            self.heading(col, text=hd, anchor="w")
            w = (col_widths[i] if col_widths else 100)
            self.column(col, anchor="w", width=w, minwidth=40)
        self.tag_configure("alt",     background=P["row_alt"])
        self.tag_configure("overdue", background=P["danger_bg"],  foreground=P["danger"])
        self.tag_configure("on_loan", foreground=P["warning"])
        self.tag_configure("muted",   foreground=P["text_muted"])

    def refill(self, rows, tag_fn=None):
        self.delete(*self.get_children())
        for i, (iid, vals) in enumerate(rows):
            tag = tag_fn(vals, i) if tag_fn else ("alt" if i%2 else "")
            self.insert("", "end", iid=iid, values=vals, tags=(tag,))

