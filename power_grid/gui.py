from __future__ import annotations


import sys
import tkinter as tk
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

# if __package__ in (None, ""):
#     _REPO_ROOT = str(Path(__file__).resolve().parent.parent)
#     if _REPO_ROOT not in sys.path:
#         sys.path.insert(0, _REPO_ROOT)

# pylint: disable=wrong-import-position
from power_grid.factories import GameSession, create_standard_game
from power_grid.gui_presenter import GameViewState, PowerGridGuiPresenter
# pylint: enable=wrong-import-position

_PLAYER_HEX: dict[str, str] = {
    "RED": "#d94343",
    "YELLOW": "#e2b93b",
    "BLUE": "#3b7dd8",
    "GREEN": "#3b9d5d",
    "PURPLE": "#8a52c4",
    "BLACK": "#2c2f36",
}


class MapPanel:
    """Canvas panel displaying towns, connections, and built houses."""

    def __init__(
        self,
        master: tk.Misc,
        on_town_click: Callable[[str], None],
    ) -> None:
        self.frame = ttk.LabelFrame(master, text="Map")
        self._on_town_click = on_town_click
        self._canvas = tk.Canvas(
            self.frame,
            width=540,
            height=430,
            bg="#f7f4ea",
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._town_centers: dict[str, tuple[float, float]] = {}
        self._last_state: GameViewState | None = None
        self._last_selected: set[str] = set()
        self._last_presenter: PowerGridGuiPresenter | None = None
        self._canvas.bind("<Button-1>", self._handle_click)
        self._canvas.bind("<Configure>", self._handle_resize)

    def render(
        self,
        presenter: PowerGridGuiPresenter,
        selected_towns: set[str],
    ) -> None:
        self._last_presenter = presenter
        self._last_state = presenter.view_state
        self._last_selected = set(selected_towns)
        self._redraw()

    def _handle_resize(self, _event: tk.Event[tk.Canvas]) -> None:
        self._redraw()

    def _handle_click(self, event: tk.Event[tk.Canvas]) -> None:
        nearest_town: str | None = None
        nearest_dist_sq = 26.0 * 26.0
        for town, (cx, cy) in self._town_centers.items():
            dist_sq = (event.x - cx) ** 2 + (event.y - cy) ** 2
            if dist_sq <= nearest_dist_sq:
                nearest_dist_sq = dist_sq
                nearest_town = town
        if nearest_town is not None:
            self._on_town_click(nearest_town)

    def _compute_centers(
        self, presenter: PowerGridGuiPresenter
    ) -> dict[str, tuple[float, float]]:
        width = max(self._canvas.winfo_width(), 500)
        height = max(self._canvas.winfo_height(), 380)
        pad_x = 46
        pad_y = 32
        usable_w = max(width - 2 * pad_x, 100)
        usable_h = max(height - 2 * pad_y, 100)
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
            self._canvas.create_line(ax, ay, bx, by, fill="#9e9b8e", width=2)
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            self._canvas.create_oval(
                mx - 9, my - 7, mx + 9, my + 7, fill="#f7f4ea", outline=""
            )
            self._canvas.create_text(
                mx,
                my,
                text=str(cost),
                fill="#4b483d",
                font=("TkDefaultFont", 8),
            )

    def _draw_towns(
        self,
        state: GameViewState,
        centers: dict[str, tuple[float, float]],
    ) -> None:
        houses_map = state.towns.houses
        for town, (cx, cy) in centers.items():
            is_sel = town in self._last_selected
            self._canvas.create_oval(
                cx - 17,
                cy - 17,
                cx + 17,
                cy + 17,
                fill="#ffe89e" if is_sel else "#ffffff",
                outline="#111111" if is_sel else "#555247",
                width=3 if is_sel else 1,
            )
            for idx, owner in enumerate(houses_map.get(town, ())):
                dot_x = cx - 9 + idx * 9
                self._canvas.create_oval(
                    dot_x - 4,
                    cy - 4,
                    dot_x + 4,
                    cy + 4,
                    fill=_PLAYER_HEX.get(owner, "#000000"),
                    outline="#ffffff",
                )
            self._canvas.create_text(
                cx,
                cy + 24,
                text=town,
                fill="#1d1c19",
                font=("TkDefaultFont", 8, "bold" if is_sel else "normal"),
            )

    def _redraw(self) -> None:
        if self._last_presenter is None or self._last_state is None:
            return
        self._canvas.delete("all")
        centers = self._compute_centers(self._last_presenter)
        self._town_centers = centers
        self._draw_connections(self._last_presenter, centers)
        self._draw_towns(self._last_state, centers)


class MarketAndPlayersPanel:
    """Displays power plant market, resource market, and player boards."""

    def __init__(self, master: tk.Misc) -> None:
        self.frame = ttk.Frame(master)
        plant_frame = ttk.LabelFrame(self.frame, text="Power Plant Market")
        plant_frame.pack(fill=tk.X, padx=4, pady=4)
        self._plant_label = ttk.Label(
            plant_frame, text="", justify=tk.LEFT, anchor=tk.W
        )
        self._plant_label.pack(fill=tk.X, padx=6, pady=4)

        res_frame = ttk.LabelFrame(self.frame, text="Resource Market")
        res_frame.pack(fill=tk.X, padx=4, pady=4)
        self._res_label = ttk.Label(
            res_frame, text="", justify=tk.LEFT, anchor=tk.W
        )
        self._res_label.pack(fill=tk.X, padx=6, pady=4)

        players_frame = ttk.LabelFrame(self.frame, text="Players")
        players_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._players_label = ttk.Label(
            players_frame, text="", justify=tk.LEFT, anchor=tk.NW
        )
        self._players_label.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def render(self, presenter: PowerGridGuiPresenter) -> None:
        state = presenter.view_state
        self._render_plant_market(presenter, state)
        self._render_resource_market(state)
        self._render_players(presenter, state)

    def _render_plant_market(
        self, presenter: PowerGridGuiPresenter, state: GameViewState
    ) -> None:
        pm = state.power_plant_market
        row1_parts: list[str] = []
        for idx, num in enumerate(pm.row1):
            label = presenter.format_plant_spec(num)
            if idx == 0 and pm.is_first_power_plant_discounted:
                label = f"{label} [1E DISCOUNT]"
            row1_parts.append(label)
        row2_parts = [presenter.format_plant_spec(num) for num in pm.row2]
        plant_lines = [
            f"Row 1 (Buyable): {', '.join(row1_parts) or '(empty)'}",
            f"Row 2 (Future):  {', '.join(row2_parts) or '(empty)'}",
            (
                f"Deck above Step 3: {pm.deck_above_step3_count} | "
                f"Deck below Step 3: {pm.deck_below_step3_count} | "
                f"Step 3 Pending: {pm.is_step3_start}"
            ),
        ]
        self._plant_label.configure(text="\n".join(plant_lines))

    def _render_resource_market(self, state: GameViewState) -> None:
        rm = state.resource_market
        pool_counts = Counter(rm.pool_resources)
        self._res_label.configure(
            text=(
                f"Market -> Coal: {rm.coal} | Oil: {rm.oil} | "
                f"Garbage: {rm.garbage} | Uranium: {rm.uranium}\n"
                f"Pool   -> Coal: {pool_counts['COAL']} | "
                f"Oil: {pool_counts['OIL']} | "
                f"Garbage: {pool_counts['GARBAGE']} | "
                f"Uranium: {pool_counts['URANIUM']}"
            )
        )

    def _render_players(
        self, presenter: PowerGridGuiPresenter, state: GameViewState
    ) -> None:
        active_color = presenter.current_player_color
        lines: list[str] = []
        for color in state.player_order:
            board = state.players.get(color)
            if board is None:
                continue
            pid = presenter.metadata.color_to_player_id.get(color, "?")
            marker = ">> " if color == active_color else "   "
            plants_text = ", ".join(
                presenter.format_plant_spec(p) for p in board.power_plants
            )
            res_counts = Counter(board.resources)
            res_text = ", ".join(
                f"{k[0]}:{res_counts[k]}"
                for k in ("COAL", "OIL", "GARBAGE", "URANIUM")
                if res_counts[k] > 0
            )
            houses = sum(
                1 for owners in state.towns.houses.values() if color in owners
            )
            lines.append(
                f"{marker}P{pid} ({color}) | {board.money}E | "
                f"Cities: {houses} | Plants: [{plants_text or '-'}] | "
                f"Fuel: [{res_text or '-'}]"
            )
        self._players_label.configure(text="\n".join(lines))


class PowerGridApp:  # pylint: disable=too-many-instance-attributes
    """Minimalist tkinter frontend strictly wired to PowerGridRulesGameInterface."""

    def __init__(
        self,
        root: tk.Tk,
        session_factory: Callable[[int, int | None], GameSession] | None = None,
    ) -> None:
        self._root = root
        self._root.title("Power Grid - Interfaces GUI")
        self._session_factory: Callable[[int, int | None], GameSession] = (
            session_factory
            if session_factory is not None
            else lambda count, limit: create_standard_game(
                player_count=count, end_game_town_count=limit
            )
        )
        self._player_count_var = tk.IntVar(value=3)
        self._quick_game_var = tk.BooleanVar(value=True)
        self._selected_towns: list[str] = []
        self._presenter = PowerGridGuiPresenter(
            self._session_factory(3, 7)
        )

        self._status_var = tk.StringVar()
        self._error_var = tk.StringVar()
        self._plant_choice_var = tk.StringVar()
        self._bid_var = tk.StringVar(value="3")
        self._remove_plant_var = tk.StringVar()
        self._remove_res_var = tk.StringVar()
        self._buy_res_var = tk.StringVar()
        self._town_choice_var = tk.StringVar()
        self._burn_res_var = tk.StringVar()
        self._burn_plant_vars: dict[int, tk.BooleanVar] = {}

        self._build_layout()
        self._refresh_ui()

    @property
    def presenter(self) -> PowerGridGuiPresenter:
        return self._presenter

    def refresh(self) -> None:
        self._refresh_ui()

    def start_new_game(self) -> None:
        count = self._player_count_var.get()
        limit = 7 if self._quick_game_var.get() else None
        self._selected_towns.clear()
        self._presenter = PowerGridGuiPresenter(
            self._session_factory(count, limit)
        )
        self._refresh_ui()

    def _build_layout(self) -> None:
        top_bar = ttk.Frame(self._root)
        top_bar.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top_bar, text="Players:").pack(side=tk.LEFT)
        ttk.Spinbox(
            top_bar,
            from_=2,
            to=6,
            width=4,
            textvariable=self._player_count_var,
        ).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(
            top_bar,
            text="Quick Game (7 cities)",
            variable=self._quick_game_var,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            top_bar, text="New Game", command=self.start_new_game
        ).pack(side=tk.LEFT, padx=6)
        ttk.Label(
            top_bar,
            textvariable=self._status_var,
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side=tk.LEFT, padx=14)

        self._error_label = ttk.Label(
            self._root,
            textvariable=self._error_var,
            foreground="#b3261e",
            padding=(8, 2),
        )
        self._error_label.pack(fill=tk.X)

        middle = ttk.Frame(self._root)
        middle.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._map_panel = MapPanel(middle, self._on_town_clicked)
        self._map_panel.frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._info_panel = MarketAndPlayersPanel(middle)
        self._info_panel.frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self._action_frame = ttk.LabelFrame(self._root, text="Phase Actions")
        self._action_frame.pack(fill=tk.X, padx=8, pady=6)

    def _refresh_ui(self) -> None:
        state = self._presenter.view_state
        pid = self._presenter.current_player_id
        color = self._presenter.current_player_color
        turn_str = f"P{pid} ({color})" if pid is not None and color else "None"
        order_str = " -> ".join(state.player_order)
        self._status_var.set(
            f"Phase: {state.game_phase} | Step: {state.step} | "
            f"Active: {turn_str} | Order: [{order_str}]"
        )
        err = self._presenter.last_error
        self._error_var.set(f"Error: {err}" if err else "")

        self._map_panel.render(self._presenter, set(self._selected_towns))
        self._info_panel.render(self._presenter)
        self._rebuild_action_controls()

    def _rebuild_action_controls(self) -> None:
        for child in self._action_frame.winfo_children():
            child.destroy()

        state = self._presenter.view_state
        phase = state.game_phase
        if phase == "AUCTION_POWER_PLANTS":
            self._build_auction_controls(state)
        elif phase == "BUY_RESOURCES":
            self._build_buy_resources_controls()
        elif phase == "BUY_HOUSES":
            self._build_buy_houses_controls()
        elif phase == "BUREAUCRACY":
            self._build_bureaucracy_controls(state)
        else:
            ranking = ", ".join(
                f"{idx + 1}. {name}"
                for idx, name in enumerate(state.game_result)
            )
            ttk.Label(
                self._action_frame,
                text=f"Game Over! Final Ranking: {ranking}",
                font=("TkDefaultFont", 10, "bold"),
            ).pack(side=tk.LEFT, padx=8, pady=6)

    def _build_auction_controls(self, state: GameViewState) -> None:
        phase_state = state.phase_state
        stage = phase_state.stage if phase_state is not None else None
        if stage == "SELECTING":
            plants = [str(num) for num in state.power_plant_market.row1]
            if self._plant_choice_var.get() not in plants:
                self._plant_choice_var.set(plants[0] if plants else "")
            ttk.Label(self._action_frame, text="Plant:").pack(
                side=tk.LEFT, padx=4
            )
            ttk.Combobox(
                self._action_frame,
                textvariable=self._plant_choice_var,
                values=plants,
                width=6,
                state="readonly",
            ).pack(side=tk.LEFT, padx=4)
            ttk.Label(self._action_frame, text="Bid:").pack(
                side=tk.LEFT, padx=4
            )
            ttk.Entry(
                self._action_frame, textvariable=self._bid_var, width=6
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                self._action_frame,
                text="Select & Bid",
                command=self._handle_select_plant,
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                self._action_frame,
                text="Pass Selection",
                command=self._handle_pass_select,
            ).pack(side=tk.LEFT, padx=4)
        elif stage == "BIDDING" and phase_state is not None:
            info = (
                f"Plant #{phase_state.current_plant} | "
                f"Current Bid: {phase_state.current_bid}E "
                f"({phase_state.highest_bidder})"
            )
            ttk.Label(self._action_frame, text=info).pack(
                side=tk.LEFT, padx=6
            )
            ttk.Entry(
                self._action_frame, textvariable=self._bid_var, width=6
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                self._action_frame,
                text="Place Bid",
                command=self._handle_bid,
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                self._action_frame,
                text="Pass Bid",
                command=self._handle_pass_bid,
            ).pack(side=tk.LEFT, padx=4)
        elif stage == "REMOVING_PLANT":
            color = self._presenter.current_player_color
            board = state.players.get(color) if color is not None else None
            owned = [str(p) for p in board.power_plants] if board else []
            if self._remove_plant_var.get() not in owned:
                self._remove_plant_var.set(owned[0] if owned else "")
            ttk.Label(self._action_frame, text="Discard Plant:").pack(
                side=tk.LEFT, padx=4
            )
            ttk.Combobox(
                self._action_frame,
                textvariable=self._remove_plant_var,
                values=owned,
                width=6,
                state="readonly",
            ).pack(side=tk.LEFT, padx=4)
            ttk.Label(
                self._action_frame, text="Discard Fuel (C/O/G/U):"
            ).pack(side=tk.LEFT, padx=4)
            ttk.Entry(
                self._action_frame, textvariable=self._remove_res_var, width=10
            ).pack(side=tk.LEFT, padx=4)
            ttk.Button(
                self._action_frame,
                text="Remove Plant",
                command=self._handle_remove_plant,
            ).pack(side=tk.LEFT, padx=4)

    def _make_append_command(self, code: str) -> Callable[[], None]:
        def _callback() -> None:
            self._append_code(self._buy_res_var, code)

        return _callback

    def _build_buy_resources_controls(self) -> None:
        ttk.Label(
            self._action_frame, text="Resources (C/O/G/U):"
        ).pack(side=tk.LEFT, padx=4)
        ttk.Entry(
            self._action_frame, textvariable=self._buy_res_var, width=14
        ).pack(side=tk.LEFT, padx=4)
        for code in ("C", "O", "G", "U"):
            ttk.Button(
                self._action_frame,
                text=f"+{code}",
                width=3,
                command=self._make_append_command(code),
            ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            self._action_frame,
            text="Clear",
            command=lambda: self._buy_res_var.set(""),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            self._action_frame,
            text="Buy Resources",
            command=self._handle_buy_resources,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            self._action_frame,
            text="Pass / Done",
            command=lambda: self._submit_buy_resources(""),
        ).pack(side=tk.LEFT, padx=4)

    def _build_buy_houses_controls(self) -> None:
        towns = list(self._presenter.metadata.town_names)
        if self._town_choice_var.get() not in towns:
            self._town_choice_var.set(towns[0] if towns else "")
        ttk.Label(self._action_frame, text="Town:").pack(side=tk.LEFT, padx=4)
        ttk.Combobox(
            self._action_frame,
            textvariable=self._town_choice_var,
            values=towns,
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            self._action_frame,
            text="Toggle Town",
            command=lambda: self._on_town_clicked(self._town_choice_var.get()),
        ).pack(side=tk.LEFT, padx=4)
        selected_text = ", ".join(self._selected_towns) or "(none)"
        ttk.Label(
            self._action_frame, text=f"Selected: {selected_text}"
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            self._action_frame,
            text="Clear",
            command=self._clear_selected_towns,
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            self._action_frame,
            text="Buy Houses",
            command=self._handle_buy_houses,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            self._action_frame,
            text="Pass",
            command=self._handle_pass_houses,
        ).pack(side=tk.LEFT, padx=4)

    def _build_bureaucracy_controls(self, state: GameViewState) -> None:
        color = self._presenter.current_player_color
        board = state.players.get(color) if color is not None else None
        owned = board.power_plants if board is not None else ()
        self._burn_plant_vars = {}
        for plant_num in owned:
            var = tk.BooleanVar(value=True)
            self._burn_plant_vars[plant_num] = var
            ttk.Checkbutton(
                self._action_frame,
                text=self._presenter.format_plant_spec(plant_num),
                variable=var,
            ).pack(side=tk.LEFT, padx=4)

        ttk.Label(
            self._action_frame, text="Burn Fuel (C/O/G/U):"
        ).pack(side=tk.LEFT, padx=4)
        ttk.Entry(
            self._action_frame, textvariable=self._burn_res_var, width=12
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            self._action_frame,
            text="Operate Plants",
            command=self._handle_use_plants,
        ).pack(side=tk.LEFT, padx=6)

    def _on_town_clicked(self, town: str) -> None:
        if self._presenter.view_state.game_phase != "BUY_HOUSES":
            return
        if town in self._selected_towns:
            self._selected_towns.remove(town)
        else:
            self._selected_towns.append(town)
        self._refresh_ui()

    def _clear_selected_towns(self) -> None:
        self._selected_towns.clear()
        self._refresh_ui()

    @staticmethod
    def _append_code(var: tk.StringVar, code: str) -> None:
        var.set(var.get() + code)

    def _parse_int_field(self, raw: str, field_name: str) -> int | None:
        try:
            return int(raw.strip())
        except ValueError:
            self._error_var.set(f"Error: {field_name} must be an integer")
            return None

    def _active_player_id(self) -> int:
        pid = self._presenter.current_player_id
        return pid if pid is not None else 1

    def _handle_select_plant(self) -> None:
        plant_num = self._parse_int_field(
            self._plant_choice_var.get(), "Plant"
        )
        bid = self._parse_int_field(self._bid_var.get(), "Bid")
        if plant_num is None or bid is None:
            return
        self._presenter.select_power_plant(
            self._active_player_id(), plant_num, bid
        )
        self._refresh_ui()

    def _handle_pass_select(self) -> None:
        self._presenter.pass_select_power_plant(self._active_player_id())
        self._refresh_ui()

    def _handle_bid(self) -> None:
        bid = self._parse_int_field(self._bid_var.get(), "Bid")
        if bid is None:
            return
        self._presenter.bid_current_power_plant(
            self._active_player_id(), bid
        )
        self._refresh_ui()

    def _handle_pass_bid(self) -> None:
        self._presenter.pass_bid_current_power_plant(self._active_player_id())
        self._refresh_ui()

    def _handle_remove_plant(self) -> None:
        plant_num = self._parse_int_field(
            self._remove_plant_var.get(), "Plant"
        )
        if plant_num is None:
            return
        err = self._presenter.remove_power_plant(
            self._active_player_id(),
            plant_num,
            self._remove_res_var.get().strip().upper(),
        )
        if err is None:
            self._remove_res_var.set("")
        self._refresh_ui()

    def _handle_buy_resources(self) -> None:
        self._submit_buy_resources(self._buy_res_var.get().strip().upper())

    def _submit_buy_resources(self, code: str) -> None:
        err = self._presenter.buy_resources(self._active_player_id(), code)
        if err is None:
            self._buy_res_var.set("")
        self._refresh_ui()

    def _handle_buy_houses(self) -> None:
        err = self._presenter.buy_houses(
            self._active_player_id(), list(self._selected_towns)
        )
        if err is None:
            self._selected_towns.clear()
        self._refresh_ui()

    def _handle_pass_houses(self) -> None:
        err = self._presenter.buy_houses(self._active_player_id(), [])
        if err is None:
            self._selected_towns.clear()
        self._refresh_ui()

    def _handle_use_plants(self) -> None:
        chosen_plants = [
            num for num, var in self._burn_plant_vars.items() if var.get()
        ]
        err = self._presenter.use_power_plants(
            self._active_player_id(),
            chosen_plants,
            self._burn_res_var.get().strip().upper(),
        )
        if err is None:
            self._burn_res_var.set("")
        self._refresh_ui()


def main() -> None:
    root = tk.Tk()
    PowerGridApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
