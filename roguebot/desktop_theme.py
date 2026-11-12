"""Shared visual styles for the Windows interface."""

from tkinter import ttk

CANVAS = "#eef2f7"
SURFACE = "#ffffff"
INK = "#17263b"
MUTED = "#4e6075"
ACCENT = "#1558b8"
LINE = "#d6dfeb"
HEADER = "#10233a"


def install_theme(root):
    root.configure(background=CANVAS)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=CANVAS, foreground=INK, font=("Segoe UI", 10),
                    bordercolor=LINE, focuscolor=ACCENT, lightcolor=LINE, darkcolor=LINE)
    style.configure("TButton", background=SURFACE, padding=(13, 7), relief="flat")
    style.map("TButton", background=[("disabled", "#e6ecf4"), ("pressed", "#dbe7f8"),
                                     ("active", "#e5effd")], foreground=[("disabled", "#64748a")])
    style.configure("Primary.TButton", background=ACCENT, foreground="#ffffff", font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton", background=[("disabled", "#dce5f1"), ("pressed", "#103e80"),
                                             ("active", "#104b9d")],
              foreground=[("disabled", "#53647a"), ("!disabled", "#ffffff")])
    style.configure("Shortcut.TButton", padding=(12, 4))
    style.configure("TCombobox", fieldbackground=SURFACE, padding=5, arrowsize=13)
    # Clam otherwise uses white text for focused readonly fields, on our white background.
    style.map("TCombobox", fieldbackground=[("disabled", "#e2e8f1"), ("readonly", SURFACE)],
              foreground=[("disabled", MUTED), ("!disabled", INK)],
              selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", INK)])
    for control in ("TEntry", "TSpinbox"):
        style.configure(control, fieldbackground=SURFACE, padding=4)
    style.configure("TNotebook", borderwidth=0, tabmargins=(0, 0, 0, 1))
    style.configure("TNotebook.Tab", padding=(15, 8), font=("Segoe UI", 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", SURFACE), ("active", "#e1e9f5")],
              foreground=[("selected", ACCENT)])
    style.map("TNotebook.Tab", expand=[("selected", (0, 0, 0, 0))])
    style.configure("Header.TFrame", background=HEADER)
    style.configure("Brand.TLabel", background=HEADER, foreground="#ffffff", font=("Segoe UI", 20, "bold"))
    style.configure("HeaderNote.TLabel", background=HEADER, foreground="#b9d4ef")
    style.configure("PageTitle.TLabel", font=("Segoe UI", 20, "bold"))
    style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
    style.configure("Hint.TLabel", foreground=MUTED)
    style.configure("Rail.TFrame", background="#e1ebf8")
    style.configure("RailTitle.TLabel", background="#e1ebf8", foreground=INK, font=("Segoe UI", 12, "bold"))
    style.configure("RailHint.TLabel", background="#e1ebf8", foreground=MUTED)


def style_text(widget, *, log=False):
    widget.configure(background=HEADER if log else SURFACE, foreground="#dce9f8" if log else INK,
                     font=("Consolas", 10) if log else ("Segoe UI", 10),
                     padx=14, pady=10, relief="flat", borderwidth=0,
                     highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
                     selectbackground="#c9dffc", selectforeground=INK)
