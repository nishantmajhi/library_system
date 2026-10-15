"""Palette, fonts and the rounded-rectangle helper.

Colours and type only. Nothing here decides anything; it is separated out so
widgets.py, dialogs.py and app.py can share one definition of the look.
"""

P = {
    "bg":          "#F0F2F7",   # page background
    "surface":     "#FFFFFF",   # cards / panels
    "surface2":    "#F7F8FC",   # input fill
    "sidebar":     "#FFFFFF",   # sidebar
    "border":      "#E2E6EF",   # subtle border
    "accent":      "#4F8EF7",   # primary blue
    "accent_dark": "#3A72D8",
    "accent_bg":   "#EBF2FF",   # tinted highlight
    "success":     "#18B981",
    "success_bg":  "#E6F7F2",
    "warning":     "#F59E0B",
    "warning_bg":  "#FEF3C7",
    "danger":      "#EF4444",
    "danger_bg":   "#FEE2E2",
    "text":        "#1E2333",
    "text_muted":  "#6B7280",
    "text_dim":    "#9CA3AF",
    "white":       "#FFFFFF",
    "nav_active":  "#EBF2FF",
    "row_alt":     "#F7F9FC",
    "head_bg":     "#F3F5FB",
}

FT  = ("Segoe UI", 22, "bold")
FH  = ("Segoe UI", 13, "bold")
FS  = ("Segoe UI", 11, "bold")
FB  = ("Segoe UI", 10)
FSM = ("Segoe UI", 9)
FBD = ("Segoe UI", 8, "bold")


def rounded_rect(canvas, x1, y1, x2, y2, r=10, **kw):
    pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
           x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
    return canvas.create_polygon(pts, smooth=True, **kw)
