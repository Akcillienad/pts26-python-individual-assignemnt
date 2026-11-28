from __future__ import annotations

import tkinter as tk
from collections import Counter
from collections.abc import Callable
from tkinter import ttk

from power_grid.gui_presenter import GameViewState, PowerGridGuiPresenter
from power_grid.gui_theme import PALETTE, PLAYER_FG, PLAYER_HEX, RESOURCE_HEX

_MAX_CITY_SLOTS = 3


class MapPanel:
    """Interactive map canvas displaying towns, connections, and built houses."""

    def __init__(
        self,
        master: tk.Misc,
        on_town_click: Callable[[str], None],
    ) -> None:
        self.frame = ttk.LabelFrame(
            master, text="Board Map", style="Card.TLabelframe"
        )
        self._on_town_click = on_town_click
        self._canvas = tk.Canvas(
            self.frame,
            width=580,
            height=430,
            bg=PALETTE["parchment"],
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 2))
        self._legend_var = tk.StringVar()
        ttk.Label(
            self.frame,
            textvariable=self._legend_var,
            style="Muted.TLabel",
            padding=(6, 2),
        ).pack(fill=tk.X)

        self._town_centers: dict[str, tuple[float, float]] = {}
        self._hovered_town: str | None = None
        self._render_data: (
            tuple[PowerGridGuiPresenter, GameViewState, set[str]] | None
        ) = None
        self._canvas.bind("<Button-1>", self._handle_click)
        self._canvas.bind("<Motion>", self._handle_motion)
        self._canvas.bind("<Leave>", self._handle_leave)
        self._canvas.bind("<Configure>", self._handle_resize)

    def render(
        self,
        presenter: PowerGridGuiPresenter,
        selected_towns: set[str],
    ) -> None:
        state = presenter.view_state
        self._render_data = (presenter, state, set(selected_towns))
        step = state.towns.step
        self._legend_var.set(
            f"Slots open per city: {step}/{_MAX_CITY_SLOTS} "
            "(Costs: 10E / 15E / 20E)  •  Click cities during Build Houses"
        )
        self._redraw()

    def _hit_test(self, x: float, y: float) -> str | None:
        nearest_town: str | None = None
        nearest_dist_sq = 26.0 * 26.0
        for town, (cx, cy) in self._town_centers.items():
            dist_sq = (x - cx) ** 2 + (y - cy) ** 2
            if dist_sq <= nearest_dist_sq:
                nearest_dist_sq = dist_sq
                nearest_town = town
        return nearest_town

    def _handle_resize(self, _event: tk.Event[tk.Canvas]) -> None:
        self._redraw()

    def _handle_click(self, event: tk.Event[tk.Canvas]) -> None:
        town = self._hit_test(event.x, event.y)
        if town is not None:
            self._on_town_click(town)

    def _handle_motion(self, event: tk.Event[tk.Canvas]) -> None:
        town = self._hit_test(event.x, event.y)
        is_build = (
            self._render_data is not None
            and self._render_data[1].game_phase == "BUY_HOUSES"
        )
        self._canvas.configure(
            cursor="hand2" if (town is not None and is_build) else ""
        )
        if town != self._hovered_town:
            self._hovered_town = town
            self._redraw()

    def _handle_leave(self, _event: tk.Event[tk.Canvas]) -> None:
        self._canvas.configure(cursor="")
        if self._hovered_town is not None:
            self._hovered_town = None
            self._redraw()

    def _compute_centers(
        self, presenter: PowerGridGuiPresenter
    ) -> dict[str, tuple[float, float]]:
        width = max(self._canvas.winfo_width(), 520)
        height = max(self._canvas.winfo_height(), 380)
        pad_x = 50
        pad_y = 34
        usable_w = max(width - 2 * pad_x, 120)
        usable_h = max(height - 2 * pad_y, 120)
        return {
            town: (pad_x + nx * usable_w, pad_y + ny * usable_h)
            for town, (nx, ny) in presenter.metadata.town_positions.items()
        }

    def _draw_connections(
        self,
        presenter: PowerGridGuiPresenter,
        centers: dict[str, tuple[float, float]],
    ) -> None:
        for town_a, town_b, cost in presenter.metadata.connections:
            if town_a not in centers or town_b not in centers:
                continue
            ax, ay = centers[town_a]
            bx, by = centers[town_b]
            self._canvas.create_line(
                ax, ay, bx, by, fill=PALETTE["edge"], width=2
            )
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            self._canvas.create_oval(
                mx - 10,
                my - 8,
                mx + 10,
                my + 8,
                fill=PALETTE["edge_pill"],
                outline=PALETTE["border"],
            )
            self._canvas.create_text(
                mx,
                my,
                text=str(cost),
                fill=PALETTE["text"],
                font=("TkDefaultFont", 8, "bold"),
            )

    def _draw_town_slots(
        self,
        cx: float,
        cy: float,
        step: int,
        owners: tuple[str, ...],
    ) -> None:
        for slot_idx in range(step):
            dot_x = cx - (step - 1) * 5 + slot_idx * 10
            owner = owners[slot_idx] if slot_idx < len(owners) else None
            dot_fill = (
                PLAYER_HEX.get(owner, "#000000")
                if owner is not None
                else "#e2e8f0"
            )
            self._canvas.create_oval(
                dot_x - 4,
                cy - 4,
                dot_x + 4,
                cy + 4,
                fill=dot_fill,
                outline="#ffffff" if owner is not None else "#94a3b8",
            )

    def _draw_towns(
        self,
        state: GameViewState,
        selected_towns: set[str],
        centers: dict[str, tuple[float, float]],
    ) -> None:
        houses_map = state.towns.houses
        step = state.towns.step
        for town, (cx, cy) in centers.items():
            is_sel = town in selected_towns
            is_hover = town == self._hovered_town
            self._canvas.create_oval(
                cx - 19,
                cy - 19,
                cx + 19,
                cy + 19,
                fill="#fde68a" if is_sel else (
                    "#f1f5f9" if is_hover else "#ffffff"
                ),
                outline=PALETTE["accent"] if is_sel else (
                    "#1e293b" if is_hover else "#64748b"
                ),
                width=3 if is_sel else (2 if is_hover else 1),
            )
            self._draw_town_slots(cx, cy, step, houses_map.get(town, ()))
            self._canvas.create_text(
                cx,
                cy + 26,
                text=town,
                fill=PALETTE["text"],
                font=("TkDefaultFont", 8, "bold" if is_sel else "normal"),
            )

    def _redraw(self) -> None:
        if self._render_data is None:
            return
        presenter, state, selected_towns = self._render_data
        self._canvas.delete("all")
        centers = self._compute_centers(presenter)
        self._town_centers = centers
        self._draw_connections(presenter, centers)
        self._draw_towns(state, selected_towns, centers)


class MarketPanel:
    """Displays clickable Power Plant Market cards and Resource Market stock."""

    def __init__(
        self,
        master: tk.Misc,
        on_plant_click: Callable[[int], None],
    ) -> None:
        self._on_plant_click = on_plant_click
        self.frame = ttk.Frame(master, style="App.TFrame")

        plant_box = ttk.LabelFrame(
            self.frame, text="Power Plant Market", style="Card.TLabelframe"
        )
        plant_box.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(
            plant_box, text="Row 1 — Buyable", style="SectionTitle.TLabel"
        ).pack(anchor=tk.W, padx=6, pady=(4, 2))
        self._row1_frame = ttk.Frame(plant_box, style="Card.TFrame")
        self._row1_frame.pack(fill=tk.X, padx=6, pady=2)

        ttk.Label(
            plant_box, text="Row 2 — Future", style="Muted.TLabel"
        ).pack(anchor=tk.W, padx=6, pady=(4, 2))
        self._row2_frame = ttk.Frame(plant_box, style="Card.TFrame")
        self._row2_frame.pack(fill=tk.X, padx=6, pady=2)

        self._deck_var = tk.StringVar()
        ttk.Label(
            plant_box,
            textvariable=self._deck_var,
            style="Muted.TLabel",
            padding=(6, 4),
        ).pack(anchor=tk.W)

        res_box = ttk.LabelFrame(
            self.frame, text="Resource Market & Pool", style="Card.TLabelframe"
        )
        res_box.pack(fill=tk.X, pady=(0, 6))
        self._res_row = ttk.Frame(res_box, style="Card.TFrame")
        self._res_row.pack(fill=tk.X, padx=6, pady=6)

    def render(
        self,
        presenter: PowerGridGuiPresenter,
        selected_plant: int | None,
    ) -> None:
        state = presenter.view_state
        self._render_row(
            self._row1_frame,
            presenter,
            state.power_plant_market.row1,
            buyable=True,
            selected_plant=selected_plant,
        )
        self._render_row(
            self._row2_frame,
            presenter,
            state.power_plant_market.row2,
            buyable=False,
            selected_plant=None,
        )
        pm = state.power_plant_market
        pending_str = "Yes" if pm.is_step3_start else "No"
        self._deck_var.set(
            f"Deck above Step 3: {pm.deck_above_step3_count}  •  "
            f"Deck below Step 3: {pm.deck_below_step3_count}  •  "
            f"Step 3 Pending: {pending_str}"
        )
        self._render_resources(state)

    def _render_row(
        self,
        container: ttk.Frame,
        presenter: PowerGridGuiPresenter,
        plants: tuple[int, ...],
        *,
        buyable: bool,
        selected_plant: int | None,
    ) -> None:
        for child in container.winfo_children():
            child.destroy()

        if not plants:
            ttk.Label(
                container, text="(empty)", style="Muted.TLabel"
            ).pack(anchor=tk.W, pady=4)
            return

        pm = presenter.view_state.power_plant_market
        can_click = buyable and presenter.can_select_plant
        for idx, num in enumerate(plants):
            is_discounted = (
                buyable and idx == 0 and pm.is_first_power_plant_discounted
            )
            is_selected = buyable and selected_plant == num
            self._create_plant_card(
                container=container,
                presenter=presenter,
                plant_num=num,
                is_discounted=is_discounted,
                is_selected=is_selected,
                clickable=can_click,
            )

    @staticmethod
    def _plant_fuel_display(
        presenter: PowerGridGuiPresenter, plant_num: int
    ) -> tuple[str, str, str]:
        spec = presenter.metadata.plant_catalog.get(plant_num)
        if spec is None:
            return "ECO", "?", RESOURCE_HEX["ECO"]
        cities_text = f"{spec.number_of_cities}C"
        if spec.resource_amount <= 0 or not spec.accepted_resources:
            return "ECO", cities_text, RESOURCE_HEX["ECO"]
        fuel_color = RESOURCE_HEX.get(
            spec.accepted_resources[0], PALETTE["muted"]
        )
        joined = "/".join(res[0] for res in spec.accepted_resources)
        return f"{spec.resource_amount}{joined}", cities_text, fuel_color

    def _bind_plant_click(
        self, widgets: list[tk.Widget], plant_num: int
    ) -> None:
        handler = self._make_plant_click_handler(plant_num)
        for widget in widgets:
            widget.bind("<Button-1>", handler)

    def _create_plant_card(  # pylint: disable=too-many-arguments
        self,
        *,
        container: ttk.Frame,
        presenter: PowerGridGuiPresenter,
        plant_num: int,
        is_discounted: bool,
        is_selected: bool,
        clickable: bool,
    ) -> None:
        bg = "#eff6ff" if is_selected else (
            PALETTE["discount_bg"] if is_discounted else PALETTE["surface_alt"]
        )
        card = tk.Frame(
            container,
            bg=bg,
            highlightbackground=(
                PALETTE["accent"] if is_selected else PALETTE["border"]
            ),
            highlightthickness=2 if is_selected else 1,
            padx=6,
            pady=4,
            cursor="hand2" if clickable else "",
        )
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)

        fuel_text, cities_text, fuel_color = self._plant_fuel_display(
            presenter, plant_num
        )
        widgets: list[tk.Widget] = [
            card,
            tk.Label(
                card,
                text=f"#{plant_num}",
                bg=bg,
                fg=PALETTE["text"],
                font=("TkDefaultFont", 10, "bold"),
            ),
            tk.Label(
                card,
                text=f"{fuel_text} -> {cities_text}",
                bg=bg,
                fg=fuel_color,
                font=("TkDefaultFont", 8, "bold"),
            ),
        ]
        for lbl in widgets[1:]:
            lbl.pack(anchor=tk.W)

        if is_discounted:
            badge = tk.Label(
                card,
                text="1E DISCOUNT",
                bg=PALETTE["discount_bg"],
                fg=PALETTE["discount_fg"],
                font=("TkDefaultFont", 7, "bold"),
            )
            badge.pack(anchor=tk.W)
            widgets.append(badge)

        if clickable:
            self._bind_plant_click(widgets, plant_num)

    def _make_plant_click_handler(
        self, plant_num: int
    ) -> Callable[[tk.Event[tk.Misc]], None]:
        def _handler(_event: tk.Event[tk.Misc]) -> None:
            self._on_plant_click(plant_num)

        return _handler

    def _render_resources(self, state: GameViewState) -> None:
        for child in self._res_row.winfo_children():
            child.destroy()

        rm = state.resource_market
        pool_counts = Counter(rm.pool_resources)
        entries = (
            ("Coal", rm.coal, pool_counts["COAL"], RESOURCE_HEX["COAL"]),
            ("Oil", rm.oil, pool_counts["OIL"], RESOURCE_HEX["OIL"]),
            (
                "Garbage",
                rm.garbage,
                pool_counts["GARBAGE"],
                RESOURCE_HEX["GARBAGE"],
            ),
            (
                "Uranium",
                rm.uranium,
                pool_counts["URANIUM"],
                RESOURCE_HEX["URANIUM"],
            ),
        )
        for name, market_qty, pool_qty, accent in entries:
            pill = tk.Frame(
                self._res_row,
                bg=PALETTE["surface_alt"],
                highlightbackground=PALETTE["border"],
                highlightthickness=1,
                padx=8,
                pady=4,
            )
            pill.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            tk.Label(
                pill,
                text=name,
                bg=PALETTE["surface_alt"],
                fg=accent,
                font=("TkDefaultFont", 8, "bold"),
            ).pack(anchor=tk.W)
            tk.Label(
                pill,
                text=f"Mkt: {market_qty} | Pool: {pool_qty}",
                bg=PALETTE["surface_alt"],
                fg=PALETTE["text"],
                font=("TkDefaultFont", 8),
            ).pack(anchor=tk.W)


class PlayersPanel:
    """Displays structured player status cards in current player order."""

    def __init__(self, master: tk.Misc) -> None:
        self.frame = ttk.LabelFrame(
            master, text="Players", style="Card.TLabelframe"
        )
        self._list_frame = ttk.Frame(self.frame, style="Card.TFrame")
        self._list_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def render(self, presenter: PowerGridGuiPresenter) -> None:
        for child in self._list_frame.winfo_children():
            child.destroy()

        state = presenter.view_state
        for color in state.player_order:
            if color in state.players:
                self._render_player_card(presenter, state, color)

    def _render_player_card(
        self,
        presenter: PowerGridGuiPresenter,
        state: GameViewState,
        color: str,
    ) -> None:
        board = state.players[color]
        pid = presenter.metadata.color_to_player_id.get(color, 0)
        is_active = color == presenter.current_player_color
        bg = "#eff6ff" if is_active else PALETTE["surface_alt"]
        card = tk.Frame(
            self._list_frame,
            bg=bg,
            highlightbackground=(
                PALETTE["accent"] if is_active else PALETTE["border"]
            ),
            highlightthickness=2 if is_active else 1,
            padx=8,
            pady=4,
        )
        card.pack(fill=tk.X, pady=2)

        top_row = tk.Frame(card, bg=bg)
        top_row.pack(fill=tk.X)
        tk.Label(
            top_row,
            text=f" P{pid} {color} ",
            bg=PLAYER_HEX.get(color, "#334155"),
            fg=PLAYER_FG.get(color, "#ffffff"),
            font=("TkDefaultFont", 8, "bold"),
        ).pack(side=tk.LEFT)
        if is_active:
            tk.Label(
                top_row,
                text="ACTIVE",
                bg=PALETTE["accent"],
                fg="#ffffff",
                font=("TkDefaultFont", 7, "bold"),
                padx=4,
            ).pack(side=tk.LEFT, padx=6)

        houses = sum(
            1 for owners in state.towns.houses.values() if color in owners
        )
        target = presenter.metadata.end_game_town_count
        tk.Label(
            top_row,
            text=f"{board.money}E   •   Cities: {houses}/{target}",
            bg=bg,
            fg=PALETTE["text"],
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side=tk.RIGHT)

        plants_text = ", ".join(
            presenter.format_plant_spec(p) for p in board.power_plants
        )
        res_counts = Counter(board.resources)
        res_text = ", ".join(
            f"{k[0]}:{res_counts[k]}"
            for k in ("COAL", "OIL", "GARBAGE", "URANIUM")
            if res_counts[k] > 0
        )
        tk.Label(
            card,
            text=(
                f"Plants: [{plants_text or '-'}]  |  "
                f"Fuel: [{res_text or '-'}]"
            ),
            bg=bg,
            fg=PALETTE["muted"],
            font=("TkDefaultFont", 8),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(2, 0))


class LogPanel:
    """Compact scrollable action and error history panel."""

    def __init__(self, master: tk.Misc) -> None:
        self.frame = ttk.LabelFrame(
            master, text="Action History", style="Card.TLabelframe"
        )
        inner = ttk.Frame(self.frame, style="Card.TFrame")
        inner.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        self._text = tk.Text(
            inner,
            height=4,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=PALETTE["surface_alt"],
            fg=PALETTE["text"],
            relief=tk.FLAT,
            font=("TkDefaultFont", 8),
        )
        scroll = ttk.Scrollbar(
            inner, orient=tk.VERTICAL, command=self._text.yview
        )
        self._text.configure(yscrollcommand=scroll.set)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._text.tag_configure("info", foreground=PALETTE["text"])
        self._text.tag_configure("error", foreground=PALETTE["error_fg"])

    def render(self, entries: tuple[tuple[str, str], ...]) -> None:
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        for level, message in entries:
            tag = "error" if level == "error" else "info"
            self._text.insert(tk.END, f"• {message}\n", tag)
        self._text.see(tk.END)
        self._text.configure(state=tk.DISABLED)
