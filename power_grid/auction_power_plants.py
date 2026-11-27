from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from power_grid.interfaces import (
    InterfacePlayerBoardAuction,
    InterfacePowerPlantMarketAuction,
)
from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)


class AuctionStage(Enum):
    INACTIVE = 1
    SELECTING = 2
    BIDDING = 3
    REMOVING_PLANT = 4


@dataclass
class _ActiveAuction:
    plant: PowerPlantNumber
    bid: int
    highest_bidder: PlayerColor
    active_bidders: list[PlayerColor]


@dataclass(frozen=True)
class _PendingRemoval:
    player: PlayerColor
    bought_plant: PowerPlantNumber


class AuctionPowerPlants:
    def __init__(
        self,
        power_plant_market: InterfacePowerPlantMarketAuction,
        player_boards: Mapping[PlayerColor, InterfacePlayerBoardAuction],
        *,
        is_first_round: bool = True,
    ) -> None:
        if not player_boards:
            raise ValueError("player_boards cannot be empty")
        if not isinstance(is_first_round, bool):
            raise ValueError("is_first_round must be a bool")

        self._power_plant_market = power_plant_market
        self._player_boards: dict[PlayerColor, InterfacePlayerBoardAuction] = (
            dict(player_boards)
        )
        self._is_first_round = is_first_round
        self._stage = AuctionStage.INACTIVE
        self._eligible_players: list[PlayerColor] = []
        self._active_auction: _ActiveAuction | None = None
        self._pending_removal: _PendingRemoval | None = None

    @property
    def is_first_round(self) -> bool:
        return self._is_first_round

    @property
    def is_active(self) -> bool:
        return self._stage != AuctionStage.INACTIVE

    @property
    def stage(self) -> AuctionStage:
        return self._stage

    @property
    def current_player(self) -> PlayerColor | None:
        if self._stage == AuctionStage.SELECTING and self._eligible_players:
            return self._eligible_players[0]
        if (
            self._stage == AuctionStage.BIDDING
            and self._active_auction is not None
            and self._active_auction.active_bidders
        ):
            return self._active_auction.active_bidders[0]
        if (
            self._stage == AuctionStage.REMOVING_PLANT
            and self._pending_removal is not None
        ):
            return self._pending_removal.player
        return None

    @property
    def eligible_players(self) -> list[PlayerColor]:
        return list(self._eligible_players)

    @property
    def active_bidders(self) -> list[PlayerColor]:
        if self._active_auction is None:
            return []
        return list(self._active_auction.active_bidders)

    @property
    def current_plant(self) -> PowerPlantNumber | None:
        if self._active_auction is None:
            return None
        return PowerPlantNumber(self._active_auction.plant.number)

    @property
    def current_bid(self) -> int | None:
        if self._active_auction is None:
            return None
        return self._active_auction.bid

    @property
    def highest_bidder(self) -> PlayerColor | None:
        if self._active_auction is None:
            return None
        return self._active_auction.highest_bidder

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        ordered_players = list(player_order)
        if not ordered_players:
            raise ValueError("player_order cannot be empty")
        unique_players = set(ordered_players)
        if len(unique_players) != len(ordered_players):
            raise ValueError("player_order cannot contain duplicate players")
        if unique_players != set(self._player_boards):
            raise ValueError(
                "player_order must contain exactly the registered players"
            )

        self._active_auction = None
        self._pending_removal = None
        self._eligible_players = ordered_players
        self._stage = AuctionStage.SELECTING

    def select_power_plant_to_bid(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        first_bid: int,
    ) -> PhaseStatus | RequestError:
        validated = self._validate_selection(player, ppn, first_bid)
        if isinstance(validated, RequestError):
            return validated

        contenders = [
            candidate
            for candidate in self._eligible_players[1:]
            if self._player_boards[candidate].has_enough_money(first_bid + 1)
        ]
        if not contenders:
            return self._conclude_auction(player, validated, first_bid)

        self._active_auction = _ActiveAuction(
            plant=validated,
            bid=first_bid,
            highest_bidder=player,
            active_bidders=contenders + [player],
        )
        self._stage = AuctionStage.BIDDING
        return PhaseStatus.PHASE_CONTINUES

    def do_not_want_power_plant(
        self, player: PlayerColor
    ) -> PhaseStatus | RequestError:
        turn_error = self._validate_selecting_turn(player)
        if turn_error is not None:
            return turn_error

        if self._is_first_round:
            return RequestError(
                "Players cannot pass buying a power plant in the first round"
            )

        if len(self._eligible_players) == 1:
            self._power_plant_market.remove_discounted_power_plant()
            self._set_inactive()
            return PhaseStatus.PHASE_ENDS

        self._eligible_players.pop(0)
        return PhaseStatus.PHASE_CONTINUES

    def bid_for_current_power_plant(
        self, player: PlayerColor, bid: int
    ) -> PhaseStatus | RequestError:
        auction = self._get_active_auction_for_bidder(player)
        if isinstance(auction, RequestError):
            return auction

        bid_error = self._validate_bid(player, bid, auction.bid)
        if bid_error is not None:
            return bid_error

        remaining_contenders = [
            candidate
            for candidate in auction.active_bidders[1:]
            if self._player_boards[candidate].has_enough_money(bid + 1)
        ]
        if not remaining_contenders:
            return self._conclude_auction(player, auction.plant, bid)

        auction.bid = bid
        auction.highest_bidder = player
        auction.active_bidders = remaining_contenders + [player]
        return PhaseStatus.PHASE_CONTINUES

    def do_not_bid_for_current_power_plant(
        self, player: PlayerColor
    ) -> PhaseStatus | RequestError:
        auction = self._get_active_auction_for_bidder(player)
        if isinstance(auction, RequestError):
            return auction

        if len(auction.active_bidders) == 2:
            return self._conclude_auction(
                auction.highest_bidder,
                auction.plant,
                auction.bid,
            )

        auction.active_bidders.pop(0)
        return PhaseStatus.PHASE_CONTINUES

    def remove_power_plant(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        resources: Sequence[Resource],
    ) -> PhaseStatus | RequestError:
        validation_error = self._validate_removal(player, ppn)
        if validation_error is not None:
            return validation_error

        error = self._player_boards[player].remove_power_plant(
            PowerPlantNumber(ppn.number), list(resources)
        )
        if error is not None:
            return error

        self._pending_removal = None
        if not self._eligible_players:
            self._finish_phase()
            return PhaseStatus.PHASE_ENDS

        self._stage = AuctionStage.SELECTING
        return PhaseStatus.PHASE_CONTINUES

    def get_state(self) -> str:
        current = self.current_player
        active = self._active_auction
        pending = self._pending_removal
        state: dict[str, object] = {
            "is_active": self.is_active,
            "is_first_round": self._is_first_round,
            "stage": self._stage.name,
            "current_player": current.name if current is not None else None,
            "eligible_players": [
                player.name for player in self._eligible_players
            ],
            "current_plant": (
                active.plant.number if active is not None else None
            ),
            "current_bid": active.bid if active is not None else None,
            "highest_bidder": (
                active.highest_bidder.name if active is not None else None
            ),
            "active_bidders": (
                [player.name for player in active.active_bidders]
                if active is not None
                else []
            ),
            "pending_removal_player": (
                pending.player.name if pending is not None else None
            ),
            "pending_removal_bought_plant": (
                pending.bought_plant.number if pending is not None else None
            ),
        }
        return json.dumps(state)

    def _validate_selecting_turn(
        self, player: PlayerColor
    ) -> RequestError | None:
        if self._stage != AuctionStage.SELECTING or not self._eligible_players:
            return RequestError(
                "Action is only allowed while selecting a power plant"
            )
        expected_player = self._eligible_players[0]
        if player != expected_player:
            return RequestError(
                f"It is {expected_player.name}'s turn, not {player.name}'s"
            )
        return None

    def _validate_selection(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        first_bid: int,
    ) -> PowerPlantNumber | RequestError:
        turn_error = self._validate_selecting_turn(player)
        if turn_error is not None:
            return turn_error
        if not self._is_valid_positive_int(ppn.number):
            return RequestError(f"Invalid power plant number: {ppn.number}")
        if not self._is_valid_positive_int(first_bid):
            return RequestError(f"Invalid first bid: {first_bid}")

        number = ppn.number
        market_error = self._power_plant_market.can_take_power_plant(
            PowerPlantNumber(number), first_bid
        )
        if market_error is not None:
            return market_error
        if not self._player_boards[player].has_enough_money(first_bid):
            return RequestError(
                f"{player.name} does not have enough money for bid {first_bid}"
            )
        return PowerPlantNumber(number)

    def _get_active_auction_for_bidder(
        self, player: PlayerColor
    ) -> _ActiveAuction | RequestError:
        if (
            self._stage != AuctionStage.BIDDING
            or self._active_auction is None
            or not self._active_auction.active_bidders
        ):
            return RequestError(
                "No power plant auction is currently in the bidding stage"
            )
        expected_player = self._active_auction.active_bidders[0]
        if player != expected_player:
            return RequestError(
                f"It is {expected_player.name}'s turn to bid, "
                f"not {player.name}'s"
            )
        return self._active_auction

    def _validate_bid(
        self, player: PlayerColor, bid: int, current_bid: int
    ) -> RequestError | None:
        if not self._is_valid_positive_int(bid):
            return RequestError(f"Invalid bid: {bid}")
        if bid <= current_bid:
            return RequestError(
                f"Bid {bid} must be greater than current bid {current_bid}"
            )
        if not self._player_boards[player].has_enough_money(bid):
            return RequestError(
                f"{player.name} does not have enough money for bid {bid}"
            )
        return None

    def _validate_removal(
        self, player: PlayerColor, ppn: PowerPlantNumber
    ) -> RequestError | None:
        if (
            self._stage != AuctionStage.REMOVING_PLANT
            or self._pending_removal is None
        ):
            return RequestError("No power plant removal is currently required")
        expected_player = self._pending_removal.player
        if player != expected_player:
            return RequestError(
                f"Expected {expected_player.name} to remove a power plant, "
                f"not {player.name}"
            )
        if not self._is_valid_positive_int(ppn.number):
            return RequestError(f"Invalid power plant number: {ppn.number}")
        if ppn.number == self._pending_removal.bought_plant.number:
            return RequestError(
                "Cannot remove the newly purchased power plant"
            )
        return None

    def _conclude_auction(
        self,
        winner: PlayerColor,
        ppn: PowerPlantNumber,
        price: int,
    ) -> PhaseStatus:
        plant = self._power_plant_market.take_power_plant(
            PowerPlantNumber(ppn.number)
        )
        within_limit = self._player_boards[winner].receive_power_plant(
            plant, price
        )
        self._eligible_players.remove(winner)
        self._active_auction = None

        if not within_limit:
            self._pending_removal = _PendingRemoval(
                player=winner,
                bought_plant=PowerPlantNumber(plant.number.number),
            )
            self._stage = AuctionStage.REMOVING_PLANT
            return PhaseStatus.PHASE_CONTINUES

        if not self._eligible_players:
            self._finish_phase()
            return PhaseStatus.PHASE_ENDS

        self._stage = AuctionStage.SELECTING
        return PhaseStatus.PHASE_CONTINUES

    def _finish_phase(self) -> None:
        self._set_inactive()
        self._power_plant_market.remove_discounted_power_plant()

    def _set_inactive(self) -> None:
        if self._is_first_round:
            self._is_first_round = False
        self._stage = AuctionStage.INACTIVE
        self._eligible_players = []
        self._active_auction = None
        self._pending_removal = None

    @staticmethod
    def _is_valid_positive_int(value: int) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, int)
            and value >= 1
        )
