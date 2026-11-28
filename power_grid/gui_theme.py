from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PALETTE: dict[str, str] = {
    "bg": "#eef2f6",
    "surface": "#ffffff",
    "surface_alt": "#f8fafc",
    "border": "#cbd5e1",
    "header_bg": "#1e293b",
    "header_fg": "#f8fafc",
    "muted": "#475569",
    "text": "#0f172a",
    "accent": "#2563eb",
    "accent_active": "#1d4ed8",
    "parchment": "#f4f1e6",
    "edge": "#94a3b8",
    "edge_pill": "#ede8d8",
    "discount_bg": "#fef3c7",
    "discount_fg": "#92400e",
    "error_bg": "#fee2e2",
    "error_fg": "#991b1b",
    "info_bg": "#ecfdf5",
    "info_fg": "#065f46",
    "hint_bg": "#e0f2fe",
    "hint_fg": "#075985",
}

PLAYER_HEX: dict[str, str] = {
    "RED": "#dc2626",
    "YELLOW": "#eab308",
    "BLUE": "#2563eb",
    "GREEN": "#16a34a",
    "PURPLE": "#9333ea",
    "BLACK": "#334155",
}

PLAYER_FG: dict[str, str] = {
    "RED": "#ffffff",
    "YELLOW": "#1e293b",
    "BLUE": "#ffffff",
    "GREEN": "#ffffff",
    "PURPLE": "#ffffff",
    "BLACK": "#ffffff",
}

RESOURCE_HEX: dict[str, str] = {
    "COAL": "#5c4033",
    "OIL": "#334155",
    "GARBAGE": "#b45309",
    "URANIUM": "#b91c1c",
    "ECO": "#15803d",
}

PHASE_HEX: dict[str, str] = {
    "AUCTION_POWER_PLANTS": "#2563eb",
    "BUY_RESOURCES": "#0f766e",
    "BUY_HOUSES": "#b45309",
    "BUREAUCRACY": "#6d28d9",
    "GAME_END": "#15803d",
}


def configure_styles(root: tk.Tk) -> ttk.Style:
    """Configure a cohesive tabletop ttk theme without external packages."""
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(background=PALETTE["bg"])
    style.configure("App.TFrame", background=PALETTE["bg"])
    style.configure("Header.TFrame", background=PALETTE["header_bg"])
    style.configure(
        "HeaderTitle.TLabel",
        background=PALETTE["header_bg"],
        foreground=PALETTE["header_fg"],
        font=("TkDefaultFont", 12, "bold"),
    )
    style.configure(
        "HeaderText.TLabel",
        background=PALETTE["header_bg"],
        foreground=PALETTE["header_fg"],
        font=("TkDefaultFont", 9),
    )
    style.configure(
        "Header.TCheckbutton",
        background=PALETTE["header_bg"],
        foreground=PALETTE["header_fg"],
    )
    style.map(
        "Header.TCheckbutton",
        background=[("active", PALETTE["header_bg"])],
    )

    style.configure("Card.TFrame", background=PALETTE["surface"])
    style.configure(
        "Card.TLabelframe",
        background=PALETTE["surface"],
        bordercolor=PALETTE["border"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=PALETTE["surface"],
        foreground=PALETTE["text"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "SectionTitle.TLabel",
        background=PALETTE["surface"],
        foreground=PALETTE["text"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "CardText.TLabel",
        background=PALETTE["surface"],
        foreground=PALETTE["text"],
        font=("TkDefaultFont", 9),
    )
    style.configure(
        "Muted.TLabel",
        background=PALETTE["surface"],
        foreground=PALETTE["muted"],
        font=("TkDefaultFont", 8),
    )

    style.configure(
        "Primary.TButton",
        background=PALETTE["accent"],
        foreground="#ffffff",
        padding=(10, 4),
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[
            ("disabled", "#cbd5e1"),
            ("active", PALETTE["accent_active"]),
        ],
        foreground=[("disabled", "#64748b"), ("!disabled", "#ffffff")],
    )

    style.configure(
        "Secondary.TButton",
        background="#e2e8f0",
        foreground=PALETTE["text"],
        padding=(8, 4),
        font=("TkDefaultFont", 9),
    )
    style.map(
        "Secondary.TButton",
        background=[("disabled", "#f1f5f9"), ("active", "#cbd5e1")],
        foreground=[("disabled", "#94a3b8"), ("!disabled", PALETTE["text"])],
    )

    style.configure(
        "Chip.TButton",
        background="#f1f5f9",
        foreground=PALETTE["text"],
        padding=(6, 2),
        font=("TkDefaultFont", 8, "bold"),
    )
    style.map(
        "Chip.TButton",
        background=[("disabled", "#f8fafc"), ("active", "#e2e8f0")],
        foreground=[("disabled", "#94a3b8"), ("!disabled", PALETTE["text"])],
    )
    return style
