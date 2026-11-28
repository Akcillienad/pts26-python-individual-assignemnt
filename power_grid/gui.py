from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from power_grid.factories import GameSession, create_standard_game
from power_grid.gui_panels import (
    LogPanel,
    MapPanel,
    MarketPanel,
    PlayersPanel,
)
from power_grid.gui_presenter import GameViewState, PowerGridGuiPresenter
from power_grid.gui_theme import (
    PALETTE,
    PHASE_HEX,
    PLAYER_FG,
    PLAYER_HEX,
    configure_styles,
)


class PowerGridApp:  # pylint: disable=too-many-instance-attributes
    """Polished tkinter frontend strictly wired to PowerGridRulesGameInterface."""

    def __init__(
        self,
        root: tk.Tk,
        session_factory: Callable[[int, int | None], GameSession] | None = None,
    ) -> None:
        self._root = root
        self._root.title("Power Grid — Recharged")
        self._root.geometry("1280x820")
        self._root.minsize(980, 660)
        configure_styles(root)

        self._session_factory = session_factory
        self._player_count_var = tk.IntVar(value=3)
        self._quick_game_var = tk.BooleanVar(value=True)
        self._random_order_var = tk.BooleanVar(value=False)
        self._selected_towns: list[str] = []
        self._local_error: str | None = None
        self._presenter = PowerGridGuiPresenter(self._create_session(3, 7))

        self._banner_var = tk.StringVar()
        self._plant_choice_var = tk.StringVar()
        self._bid_var = tk.StringVar(value="1")
        self._remove_plant_var = tk.StringVar()
        self._remove_res_var = tk.StringVar()
        self._buy_res_var = tk.StringVar()
        self._town_choice_var = tk.StringVar()
        self._burn_res_var = tk.StringVar()
        self._burn_plant_vars: dict[int, tk.BooleanVar] = {}
        self._control_buttons: dict[str, ttk.Button] = {}
        self._primary_action: Callable[[], None] | None = None

        self._buy_res_var.trace_add("write", self._on_resource_var_changed)
        self._burn_res_var.trace_add("write", self._on_resource_var_changed)

        (
            self._phase_pill,
            self._step_pill,
            self._player_pill,
        ) = self._build_header()
        self._banner_frame, self._banner_label = self._build_banner()
        self._build_workspace()
        self._bind_shortcuts()
        self._refresh_ui()

    @property
    def presenter(self) -> PowerGridGuiPresenter:
        return self._presenter

    @property
    def suggested_bid(self) -> str:
        return self._bid_var.get()

    @property
    def error_banner_text(self) -> str:
        if self._local_error is not None:
            return f"Error: {self._local_error}"
        if self._presenter.last_error is not None:
            return f"Error: {self._presenter.last_error}"
        return ""

    @property
    def status_banner_text(self) -> str:
        return self._banner_var.get()

    def action_button_states(self) -> dict[str, bool]:
        return {
            name: not button.instate(["disabled"])
            for name, button in self._control_buttons.items()
        }

    def refresh(self) -> None:
        self._refresh_ui()

    def start_new_game(self) -> None:
        try:
            count = int(self._player_count_var.get())
        except (ValueError, tk.TclError):
            self._set_local_error("Players must be an integer between 2 and 6")
            return
        if count < 2 or count > 6:
            self._set_local_error("Players must be between 2 and 6")
            return

        limit = 7 if self._quick_game_var.get() else None
        self._selected_towns.clear()
        self._local_error = None
        self._buy_res_var.set("")
        self._burn_res_var.set("")
        self._remove_res_var.set("")
        self._presenter = PowerGridGuiPresenter(
            self._create_session(count, limit)
        )
        self._refresh_ui()

    def select_market_plant(self, plant_number: int) -> None:
        if not self._presenter.can_select_plant:
            return
        if plant_number not in self._presenter.view_state.power_plant_market.row1:
            return
        self._plant_choice_var.set(str(plant_number))
        self._local_error = None
        self._bid_var.set(
            self._suggested_selecting_bid(self._presenter.view_state)
        )
        self._refresh_ui()

    def trigger_primary_action(self) -> None:
        if self._primary_action is None:
            return
        self._primary_action()

    def clear_current_inputs(self) -> None:
        phase = self._presenter.view_state.game_phase
        if phase == "BUY_HOUSES":
            self._clear_selected_towns()
        elif phase == "BUY_RESOURCES":
            self._buy_res_var.set("")
            self._sync_clear_button("clear_buy_res", self._buy_res_var)
        elif phase == "BUREAUCRACY":
            self._burn_res_var.set("")
            self._sync_clear_button("clear_burn_res", self._burn_res_var)
        elif phase == "AUCTION_POWER_PLANTS":
            self._remove_res_var.set("")

    def _create_session(
        self, count: int, limit: int | None
    ) -> GameSession:
        if self._session_factory is not None:
            return self._session_factory(count, limit)
        return create_standard_game(
            player_count=count,
            end_game_town_count=limit,
            randomize_player_order=self._random_order_var.get(),
        )

    def _build_workspace(self) -> None:
        body = ttk.PanedWindow(self._root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 6))

        self._map_panel = MapPanel(body, self.toggle_town)
        body.add(self._map_panel.frame, weight=3)

        right_col = ttk.Frame(body, style="App.TFrame")
        self._market_panel = MarketPanel(right_col, self.select_market_plant)
        self._market_panel.frame.pack(fill=tk.X)
        self._players_panel = PlayersPanel(right_col)
        self._players_panel.frame.pack(fill=tk.BOTH, expand=True)
        body.add(right_col, weight=2)

        bottom = ttk.Frame(self._root, style="App.TFrame")
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))
        bottom.columnconfigure(0, weight=3)
        bottom.columnconfigure(1, weight=2)

        self._action_frame = ttk.LabelFrame(
            bottom, text="Phase Actions", style="Card.TLabelframe"
        )
        self._action_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self._log_panel = LogPanel(bottom)
        self._log_panel.frame.grid(row=0, column=1, sticky="nsew")

    def _build_header(self) -> tuple[tk.Label, tk.Label, tk.Label]:
        header = ttk.Frame(self._root, style="Header.TFrame", padding=(12, 8))
        header.pack(fill=tk.X)

        left = ttk.Frame(header, style="Header.TFrame")
        left.pack(side=tk.LEFT)
        ttk.Label(
            left, text="POWER GRID", style="HeaderTitle.TLabel"
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(left, text="Players:", style="HeaderText.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Spinbox(
            left,
            from_=2,
            to=6,
            width=3,
            textvariable=self._player_count_var,
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Checkbutton(
            left,
            text="Quick (7 cities)",
            variable=self._quick_game_var,
            style="Header.TCheckbutton",
        ).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(
            left,
            text="Random Order",
            variable=self._random_order_var,
            style="Header.TCheckbutton",
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            left,
            text="New Game",
            command=self.start_new_game,
            style="Secondary.TButton",
        ).pack(side=tk.LEFT, padx=(8, 0))

        right = ttk.Frame(header, style="Header.TFrame")
        right.pack(side=tk.RIGHT)
        phase_pill = tk.Label(
            right,
            text="",
            padx=10,
            pady=3,
            font=("TkDefaultFont", 9, "bold"),
        )
        phase_pill.pack(side=tk.LEFT, padx=4)
        step_pill = tk.Label(
            right,
            text="",
            bg="#334155",
            fg="#f8fafc",
            padx=8,
            pady=3,
            font=("TkDefaultFont", 9, "bold"),
        )
        step_pill.pack(side=tk.LEFT, padx=4)
        player_pill = tk.Label(
            right,
            text="",
            padx=10,
            pady=3,
            font=("TkDefaultFont", 9, "bold"),
        )
        player_pill.pack(side=tk.LEFT, padx=4)
        return phase_pill, step_pill, player_pill

    def _build_banner(self) -> tuple[tk.Frame, tk.Label]:
        banner_frame = tk.Frame(self._root, padx=12, pady=5)
        banner_frame.pack(fill=tk.X)
        banner_label = tk.Label(
            banner_frame,
            textvariable=self._banner_var,
            anchor=tk.W,
            font=("TkDefaultFont", 9, "bold"),
        )
        banner_label.pack(fill=tk.X)
        return banner_frame, banner_label

    def _bind_shortcuts(self) -> None:
        self._root.bind("<Return>", self._handle_return_key)
        self._root.bind("<Escape>", self._handle_escape_key)
        self._root.bind("<Control-n>", self._handle_new_game_key)
        self._root.bind("<Control-N>", self._handle_new_game_key)

    def _handle_return_key(self, event: tk.Event[tk.Misc]) -> None:
        if isinstance(event.widget, ttk.Spinbox):
            return
        self.trigger_primary_action()

    def _handle_escape_key(self, _event: tk.Event[tk.Misc]) -> None:
        self.clear_current_inputs()

    def _handle_new_game_key(self, _event: tk.Event[tk.Misc]) -> None:
        self.start_new_game()

    def _refresh_ui(self) -> None:
        state = self._presenter.view_state
        self._render_header_pills(state)
        self._render_banner(state)
        selected_plant = self._selected_plant_int()
        self._map_panel.render(self._presenter, set(self._selected_towns))
        self._market_panel.render(self._presenter, selected_plant)
        self._players_panel.render(self._presenter)
        self._log_panel.render(self._presenter.action_log)
        self._rebuild_action_controls()

    def _render_header_pills(self, state: GameViewState) -> None:
        phase_bg = PHASE_HEX.get(state.game_phase, PALETTE["accent"])
        self._phase_pill.configure(
            text=self._presenter.phase_display_name(),
            bg=phase_bg,
            fg="#ffffff",
        )
        self._step_pill.configure(text=f"Step {state.step}")
        pid = self._presenter.current_player_id
        color = self._presenter.current_player_color
        if pid is not None and color is not None:
            self._player_pill.configure(
                text=f"Turn: P{pid} {color}",
                bg=PLAYER_HEX.get(color, "#334155"),
                fg=PLAYER_FG.get(color, "#ffffff"),
            )
        else:
            self._player_pill.configure(
                text="Game Finished", bg="#475569", fg="#ffffff"
            )

    def _render_banner(self, state: GameViewState) -> None:
        err = self._local_error or self._presenter.last_error
        if err is not None:
            text, bg, fg = (
                f"Error: {err}",
                PALETTE["error_bg"],
                PALETTE["error_fg"],
            )
        elif self._presenter.last_status is not None:
            text, bg, fg = (
                self._presenter.last_status,
                PALETTE["info_bg"],
                PALETTE["info_fg"],
            )
        else:
            text, bg, fg = (
                self._phase_hint(state),
                PALETTE["hint_bg"],
                PALETTE["hint_fg"],
            )
        self._banner_var.set(text)
        self._banner_frame.configure(bg=bg)
        self._banner_label.configure(bg=bg, fg=fg)

    @staticmethod
    def _phase_hint(state: GameViewState) -> str:
        phase = state.game_phase
        if phase == "AUCTION_POWER_PLANTS":
            stage = state.phase_state.stage if state.phase_state else None
            stage_hints = {
                "BIDDING": (
                    "Auction in progress — place a higher bid (Enter) "
                    "or pass this auction."
                ),
                "REMOVING_PLANT": (
                    "Plant limit exceeded — select an older plant to discard "
                    "along with any excess fuel."
                ),
            }
            if stage in stage_hints:
                return stage_hints[stage]
            if state.phase_state and state.phase_state.is_first_round:
                return (
                    "Round 1: Click a Row 1 card or choose from the dropdown "
                    "and submit an opening bid (Enter)."
                )
            return (
                "Choose a Row 1 plant to auction or pass selection for "
                "this round."
            )
        static_hints = {
            "BUY_RESOURCES": (
                "Use fuel chips (+C/+O/+G/+U) to buy resources or Pass / Done."
            ),
            "BUY_HOUSES": (
                "Click cities on the map (Esc to clear), then Buy Houses "
                "or Pass."
            ),
            "BUREAUCRACY": (
                "Select plants to power and fuel to burn, then Operate Plants."
            ),
        }
        return static_hints.get(
            phase,
            "Final ranking complete. Press Ctrl+N or click New Game.",
        )

    def _set_local_error(self, message: str) -> None:
        self._local_error = message
        self._render_banner(self._presenter.view_state)

    def _selected_plant_int(self) -> int | None:
        raw = self._plant_choice_var.get().strip()
        return int(raw) if raw.isdigit() else None

    def _rebuild_action_controls(self) -> None:
        for child in self._action_frame.winfo_children():
            child.destroy()
        self._control_buttons = {}
        self._primary_action = None

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
            self._build_game_end_controls(state)

    def _add_button(  # pylint: disable=too-many-arguments
        self,
        parent: tk.Misc,
        *,
        key: str,
        text: str,
        command: Callable[[], None],
        style: str = "Secondary.TButton",
        enabled: bool = True,
        width: int | None = None,
    ) -> ttk.Button:
        btn = ttk.Button(
            parent,
            text=text,
            command=command,
            style=style,
            state=tk.NORMAL if enabled else tk.DISABLED,
        )
        if width is not None:
            btn.configure(width=width)
        btn.pack(side=tk.LEFT, padx=3)
        self._control_buttons[key] = btn
        return btn

    def _suggested_selecting_bid(self, state: GameViewState) -> str:
        raw = self._plant_choice_var.get().strip()
        if not raw.isdigit():
            return "1"
        plant_num = int(raw)
        pm = state.power_plant_market
        if (
            pm.is_first_power_plant_discounted
            and pm.row1
            and pm.row1[0] == plant_num
        ):
            return "1"
        return str(plant_num)

    def _on_plant_choice_changed(
        self, _event: tk.Event[ttk.Combobox]
    ) -> None:
        self._local_error = None
        self._bid_var.set(
            self._suggested_selecting_bid(self._presenter.view_state)
        )
        self._refresh_ui()

    def _build_auction_controls(self, state: GameViewState) -> None:
        phase_state = state.phase_state
        stage = phase_state.stage if phase_state is not None else None
        row = ttk.Frame(self._action_frame, style="Card.TFrame")
        row.pack(fill=tk.X, padx=8, pady=8)

        if stage == "SELECTING":
            self._build_selecting_row(row, state)
        elif stage == "BIDDING" and phase_state is not None:
            self._build_bidding_row(
                row,
                phase_state.current_plant,
                phase_state.current_bid,
                phase_state.highest_bidder,
            )
        elif stage == "REMOVING_PLANT":
            self._build_removing_row(row, state)

    def _build_selecting_row(
        self, row: ttk.Frame, state: GameViewState
    ) -> None:
        plants = [str(num) for num in state.power_plant_market.row1]
        if self._plant_choice_var.get() not in plants:
            self._plant_choice_var.set(plants[0] if plants else "")
        if self._presenter.last_error is None and self._local_error is None:
            self._bid_var.set(self._suggested_selecting_bid(state))

        ttk.Label(row, text="Plant:", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        combo = ttk.Combobox(
            row,
            textvariable=self._plant_choice_var,
            values=plants,
            width=6,
            state="readonly" if plants else tk.DISABLED,
        )
        combo.bind("<<ComboboxSelected>>", self._on_plant_choice_changed)
        combo.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(row, text="Opening Bid (E):", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Entry(row, textvariable=self._bid_var, width=6).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self._add_button(
            row,
            key="select_bid",
            text="Select & Bid",
            command=self._handle_select_plant,
            style="Primary.TButton",
            enabled=self._presenter.can_select_plant,
        )
        self._add_button(
            row,
            key="pass_select",
            text="Pass Selection",
            command=self._handle_pass_select,
            style="Secondary.TButton",
            enabled=self._presenter.can_pass_selection,
        )
        if self._presenter.can_select_plant:
            self._primary_action = self._handle_select_plant

    def _build_bidding_row(
        self,
        row: ttk.Frame,
        plant_num: int | None,
        current_bid: int | None,
        highest_bidder: str | None,
    ) -> None:
        if (
            self._presenter.last_error is None
            and self._local_error is None
            and current_bid is not None
        ):
            self._bid_var.set(str(current_bid + 1))

        info = (
            f"Bidding on #{plant_num}  •  "
            f"Current: {current_bid}E ({highest_bidder})"
        )
        ttk.Label(row, text=info, style="SectionTitle.TLabel").pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Label(row, text="Your Bid (E):", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Entry(row, textvariable=self._bid_var, width=6).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self._add_button(
            row,
            key="place_bid",
            text="Place Bid",
            command=self._handle_bid,
            style="Primary.TButton",
        )
        self._add_button(
            row,
            key="pass_bid",
            text="Pass Bid",
            command=self._handle_pass_bid,
            style="Secondary.TButton",
        )
        self._primary_action = self._handle_bid

    def _build_removing_row(
        self, row: ttk.Frame, state: GameViewState
    ) -> None:
        discardable = [str(p) for p in self._presenter.discardable_owned_plants]
        if self._remove_plant_var.get() not in discardable:
            self._remove_plant_var.set(discardable[0] if discardable else "")

        bought = (
            state.phase_state.pending_removal_bought_plant
            if state.phase_state is not None
            else None
        )
        ttk.Label(
            row,
            text=f"Discard Old Plant (keeping #{bought}):",
            style="CardText.TLabel",
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(
            row,
            textvariable=self._remove_plant_var,
            values=discardable,
            width=6,
            state="readonly" if discardable else tk.DISABLED,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(row, text="Drop Fuel (C/O/G/U):", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Entry(row, textvariable=self._remove_res_var, width=10).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        can_remove = bool(discardable)
        self._add_button(
            row,
            key="remove_plant",
            text="Remove Plant",
            command=self._handle_remove_plant,
            style="Primary.TButton",
            enabled=can_remove,
        )
        if can_remove:
            self._primary_action = self._handle_remove_plant

    def _make_append_command(
        self, var: tk.StringVar, code: str
    ) -> Callable[[], None]:
        def _callback() -> None:
            var.set(var.get() + code)

        return _callback

    def _on_resource_var_changed(self, *_args: object) -> None:
        self._sync_clear_button("clear_buy_res", self._buy_res_var)
        self._sync_clear_button("clear_burn_res", self._burn_res_var)

    def _sync_clear_button(self, key: str, var: tk.StringVar) -> None:
        btn = self._control_buttons.get(key)
        if btn is not None and btn.winfo_exists():
            btn.configure(
                state=tk.NORMAL if var.get().strip() else tk.DISABLED
            )

    def _build_buy_resources_controls(self) -> None:
        row = ttk.Frame(self._action_frame, style="Card.TFrame")
        row.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(row, text="Fuel (C/O/G/U):", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Entry(row, textvariable=self._buy_res_var, width=12).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        available = self._presenter.available_market_resource_codes
        for code in ("C", "O", "G", "U"):
            self._add_button(
                row,
                key=f"add_buy_{code}",
                text=f"+{code}",
                width=3,
                command=self._make_append_command(self._buy_res_var, code),
                style="Chip.TButton",
                enabled=code in available,
            )
        self._add_button(
            row,
            key="clear_buy_res",
            text="Clear",
            command=self.clear_current_inputs,
            style="Secondary.TButton",
            enabled=bool(self._buy_res_var.get().strip()),
        )
        self._add_button(
            row,
            key="buy_resources",
            text="Buy Resources",
            command=self._handle_buy_resources,
            style="Primary.TButton",
        )
        self._add_button(
            row,
            key="pass_resources",
            text="Pass / Done",
            command=lambda: self._submit_buy_resources(""),
            style="Secondary.TButton",
        )
        self._primary_action = self._handle_buy_resources

    def _build_buy_houses_controls(self) -> None:
        row = ttk.Frame(self._action_frame, style="Card.TFrame")
        row.pack(fill=tk.X, padx=8, pady=8)

        towns = list(self._presenter.metadata.town_names)
        if self._town_choice_var.get() not in towns:
            self._town_choice_var.set(towns[0] if towns else "")

        ttk.Label(row, text="City:", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Combobox(
            row,
            textvariable=self._town_choice_var,
            values=towns,
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(0, 4))
        self._add_button(
            row,
            key="toggle_town",
            text="Toggle City",
            command=lambda: self.toggle_town(self._town_choice_var.get()),
            style="Secondary.TButton",
        )
        selected_text = ", ".join(self._selected_towns) or "(none)"
        ttk.Label(
            row,
            text=f"Selected: {selected_text}",
            style="CardText.TLabel",
        ).pack(side=tk.LEFT, padx=8)
        has_selection = bool(self._selected_towns)
        self._add_button(
            row,
            key="clear_houses",
            text="Clear",
            command=self._clear_selected_towns,
            style="Secondary.TButton",
            enabled=has_selection,
        )
        self._add_button(
            row,
            key="buy_houses",
            text="Buy Houses",
            command=self._handle_buy_houses,
            style="Primary.TButton",
            enabled=has_selection,
        )
        self._add_button(
            row,
            key="pass_houses",
            text="Pass",
            command=self._handle_pass_houses,
            style="Secondary.TButton",
        )
        self._primary_action = (
            self._handle_buy_houses if has_selection else None
        )

    def _build_bureaucracy_controls(self, state: GameViewState) -> None:
        row = ttk.Frame(self._action_frame, style="Card.TFrame")
        row.pack(fill=tk.X, padx=8, pady=8)

        color = self._presenter.current_player_color
        board = state.players.get(color) if color is not None else None
        owned = board.power_plants if board is not None else ()
        self._burn_plant_vars = {}
        for plant_num in owned:
            var = tk.BooleanVar(value=True)
            self._burn_plant_vars[plant_num] = var
            ttk.Checkbutton(
                row,
                text=self._presenter.format_plant_spec(plant_num),
                variable=var,
            ).pack(side=tk.LEFT, padx=4)

        ttk.Label(row, text="Burn Fuel:", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=(6, 4)
        )
        ttk.Entry(row, textvariable=self._burn_res_var, width=10).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        owned_codes = self._presenter.owned_resource_codes
        for code in ("C", "O", "G", "U"):
            self._add_button(
                row,
                key=f"add_burn_{code}",
                text=f"+{code}",
                width=3,
                command=self._make_append_command(self._burn_res_var, code),
                style="Chip.TButton",
                enabled=code in owned_codes,
            )
        self._add_button(
            row,
            key="clear_burn_res",
            text="Clear",
            command=self.clear_current_inputs,
            style="Secondary.TButton",
            enabled=bool(self._burn_res_var.get().strip()),
        )
        self._add_button(
            row,
            key="operate_plants",
            text="Operate Plants",
            command=self._handle_use_plants,
            style="Primary.TButton",
            enabled=bool(owned),
        )
        self._add_button(
            row,
            key="skip_bureaucracy",
            text="Skip (+10E)",
            command=self._handle_skip_bureaucracy,
            style="Secondary.TButton",
        )
        self._primary_action = (
            self._handle_use_plants if owned else self._handle_skip_bureaucracy
        )

    def _build_game_end_controls(self, state: GameViewState) -> None:
        row = ttk.Frame(self._action_frame, style="Card.TFrame")
        row.pack(fill=tk.X, padx=8, pady=8)

        ranking = "   •   ".join(
            f"#{idx + 1} {name}"
            for idx, name in enumerate(state.game_result)
        )
        ttk.Label(
            row,
            text=f"Game Over — Final Ranking: {ranking}",
            style="SectionTitle.TLabel",
        ).pack(side=tk.LEFT, padx=(0, 12))
        self._add_button(
            row,
            key="new_game_end",
            text="Start New Game",
            command=self.start_new_game,
            style="Primary.TButton",
        )
        self._primary_action = self.start_new_game

    def toggle_town(self, town: str) -> None:
        if self._presenter.view_state.game_phase != "BUY_HOUSES":
            return
        self._local_error = None
        if town in self._selected_towns:
            self._selected_towns.remove(town)
        else:
            self._selected_towns.append(town)
        self._refresh_ui()

    def _clear_selected_towns(self) -> None:
        self._selected_towns.clear()
        self._local_error = None
        self._refresh_ui()

    def _parse_int_field(self, raw: str, field_name: str) -> int | None:
        try:
            return int(raw.strip())
        except ValueError:
            self._set_local_error(f"{field_name} must be an integer")
            return None

    def _active_player_id(self) -> int:
        pid = self._presenter.current_player_id
        return pid if pid is not None else 1

    def _handle_select_plant(self) -> None:
        if not self._presenter.can_select_plant:
            return
        plant_num = self._parse_int_field(
            self._plant_choice_var.get(), "Plant"
        )
        bid = self._parse_int_field(self._bid_var.get(), "Bid")
        if plant_num is None or bid is None:
            return
        self._local_error = None
        self._presenter.select_power_plant(
            self._active_player_id(), plant_num, bid
        )
        self._refresh_ui()

    def _handle_pass_select(self) -> None:
        if not self._presenter.can_pass_selection:
            return
        self._local_error = None
        self._presenter.pass_select_power_plant(self._active_player_id())
        self._refresh_ui()

    def _handle_bid(self) -> None:
        bid = self._parse_int_field(self._bid_var.get(), "Bid")
        if bid is None:
            return
        self._local_error = None
        self._presenter.bid_current_power_plant(
            self._active_player_id(), bid
        )
        self._refresh_ui()

    def _handle_pass_bid(self) -> None:
        self._local_error = None
        self._presenter.pass_bid_current_power_plant(self._active_player_id())
        self._refresh_ui()

    def _handle_remove_plant(self) -> None:
        plant_num = self._parse_int_field(
            self._remove_plant_var.get(), "Plant"
        )
        if plant_num is None:
            return
        self._local_error = None
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
        self._local_error = None
        err = self._presenter.buy_resources(self._active_player_id(), code)
        if err is None:
            self._buy_res_var.set("")
        self._refresh_ui()

    def _handle_buy_houses(self) -> None:
        if not self._selected_towns:
            return
        self._local_error = None
        err = self._presenter.buy_houses(
            self._active_player_id(), list(self._selected_towns)
        )
        if err is None:
            self._selected_towns.clear()
        self._refresh_ui()

    def _handle_pass_houses(self) -> None:
        self._local_error = None
        err = self._presenter.buy_houses(self._active_player_id(), [])
        if err is None:
            self._selected_towns.clear()
        self._refresh_ui()

    def _handle_use_plants(self) -> None:
        self._local_error = None
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

    def _handle_skip_bureaucracy(self) -> None:
        self._local_error = None
        err = self._presenter.use_power_plants(
            self._active_player_id(), [], ""
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
