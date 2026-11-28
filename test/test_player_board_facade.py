# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest
from collections.abc import Sequence
from test.blue_test_fakes import (
    FakePlayerPowerPlants,
    FakeResourceMarket,
    FakeResourcePool,
    FakeTowns,
)

from power_grid.player_board_facade import (
    PAYMENT_TABLE,
    PlayerBoardContext,
    PlayerBoardFacade,
)
from power_grid.player_money import PlayerMoney
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import PlayerColor, RequestError, Resource


class MutatingPlayerPowerPlants(FakePlayerPowerPlants):
    def __init__(self, plants: Sequence[PowerPlant] = ()) -> None:
        super().__init__(plants)
        self.last_ppns_was_list: bool | None = None
        self.override_use_result: int | RequestError | None = None

    def can_store_resources(self, resources: Sequence[Resource]) -> bool:
        result = super().can_store_resources(resources)
        if isinstance(resources, list):
            resources.clear()
        return result

    def number_of_connectable_cities(
        self,
        resources: Sequence[Resource],
    ) -> int:
        count = super().number_of_connectable_cities(resources)
        if isinstance(resources, list):
            resources.clear()
        return count

    def remove_power_plant(
        self,
        ppn: PowerPlantNumber,
        new_resources: Sequence[Resource],
    ) -> RequestError | None:
        err = super().remove_power_plant(ppn, new_resources)
        if isinstance(new_resources, list):
            new_resources.clear()
        return err

    def use_power_plant(
        self,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> int | RequestError:
        self.last_ppns_was_list = isinstance(ppns, list)
        result = (
            self.override_use_result
            if self.override_use_result is not None
            else super().use_power_plant(ppns, resources_to_burn)
        )
        if isinstance(resources_to_burn, list):
            resources_to_burn.clear()
        return result


class NegativeTownsFake:
    def __init__(self, houses: int) -> None:
        self._houses = houses

    def get_number_of_houses(self, player: PlayerColor) -> int:
        _ = player
        return self._houses


class MutatingResourceMarket(FakeResourceMarket):
    def take_resources(self, resources: list[Resource]) -> None:
        super().take_resources(resources)
        resources.clear()


class StrictListPlayerPowerPlants:
    def __init__(self, plants: list[PowerPlant]) -> None:
        self._plants = list(plants)
        self.types_checked: list[bool] = []

    @property
    def power_plants(self) -> list[PowerPlant]:
        return list(self._plants)

    def best_power_plant(self) -> PowerPlantNumber:
        return PowerPlantNumber(
            max((plant.number.number for plant in self._plants), default=0)
        )

    def receive_power_plant(self, power_plant: PowerPlant) -> bool:
        self._plants.append(power_plant)
        return True

    def remove_power_plant(  # pylint: disable=useless-return
        self, ppn: PowerPlantNumber, new_resources: list[Resource]
    ) -> RequestError | None:
        self.types_checked.append(isinstance(new_resources, list))
        self._plants = [
            plant
            for plant in self._plants
            if plant.number.number != ppn.number
        ]
        return None

    def number_of_connectable_cities(self, resources: list[Resource]) -> int:
        self.types_checked.append(isinstance(resources, list))
        return len(resources)

    def can_store_resources(self, resources: list[Resource]) -> bool:
        self.types_checked.append(isinstance(resources, list))
        return True

    def use_power_plant(
        self,
        ppns: list[PowerPlantNumber],
        resources_to_burn: list[Resource],
    ) -> int | RequestError:
        self.types_checked.append(
            isinstance(ppns, list) and isinstance(resources_to_burn, list)
        )
        return len(ppns)


class TestPlayerBoardFacade(unittest.TestCase):
    def _coal_plant(
        self,
        number: int = 4,
        fuel: int = 2,
        cities: int = 1,
    ) -> PowerPlant:
        return PowerPlant(
            PowerPlantNumber(number), [Resource.COAL], fuel, cities
        )

    def _oil_plant(
        self,
        number: int = 3,
        fuel: int = 2,
        cities: int = 1,
    ) -> PowerPlant:
        return PowerPlant(
            PowerPlantNumber(number), [Resource.OIL], fuel, cities
        )

    def _wind_plant(self, number: int = 13, cities: int = 3) -> PowerPlant:
        return PowerPlant(PowerPlantNumber(number), [], 0, cities)

    def test_payment_table_matches_power_grid_rules(self) -> None:
        expected = (
            10, 22, 33, 44, 54, 64, 73, 82, 90, 98,
            105, 112, 118, 124, 129, 134, 138, 142, 145, 148, 150,
        )
        self.assertEqual(PlayerBoardFacade.PAYMENT_TABLE, expected)
        self.assertEqual(PAYMENT_TABLE, expected)
        self.assertEqual(len(PAYMENT_TABLE), 21)

    def test_init_validates_initial_resources_and_copies_input(self) -> None:
        plants = FakePlayerPowerPlants([self._coal_plant(4, fuel=1, cities=1)])
        context = PlayerBoardContext(FakeResourceMarket(), FakeResourcePool())
        initial = [Resource.COAL, Resource.COAL]

        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 50), plants, context, initial
        )
        initial.append(Resource.OIL)
        self.assertEqual(facade.resources, [Resource.COAL, Resource.COAL])
        self.assertEqual(facade.color, PlayerColor.RED)
        self.assertEqual(facade.best_power_plant_number().number, 4)

        with self.assertRaises(ValueError):
            PlayerBoardFacade(
                PlayerMoney(PlayerColor.RED, 50),
                plants,
                context,
                [Resource.COAL, Resource.COAL, Resource.COAL],
            )
        with self.assertRaises(ValueError):
            PlayerBoardFacade(
                PlayerMoney(PlayerColor.RED, 50),
                plants,
                context,
                [Resource.OIL],
            )

    def test_properties_return_defensive_copies(self) -> None:
        plants = FakePlayerPowerPlants([self._coal_plant(4)])
        context = PlayerBoardContext(FakeResourceMarket(), FakeResourcePool())
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.BLUE, 40),
            plants,
            context,
            [Resource.COAL],
        )

        res_copy = facade.resources
        res_copy.append(Resource.URANIUM)
        self.assertEqual(facade.resources, [Resource.COAL])

        plants_copy = facade.power_plants
        plants_copy.clear()
        self.assertEqual(len(facade.power_plants), 1)

    def test_money_edge_cases(self) -> None:
        context = PlayerBoardContext(FakeResourceMarket(), FakeResourcePool())
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.GREEN, 30),
            FakePlayerPowerPlants(),
            context,
        )

        self.assertFalse(facade.has_enough_money(-1))
        self.assertTrue(facade.has_enough_money(0))
        self.assertTrue(facade.has_enough_money(30))
        self.assertFalse(facade.has_enough_money(31))

        facade.spend_money(0)
        self.assertEqual(facade.outstanding_money(), 30)

        with self.assertRaises(ValueError):
            facade.spend_money(-5)
        self.assertEqual(facade.outstanding_money(), 30)

        with self.assertRaises(ValueError):
            facade.spend_money(31)
        self.assertEqual(facade.outstanding_money(), 30)

        facade.spend_money(30)
        self.assertEqual(facade.outstanding_money(), 0)

    def test_receive_power_plant_within_and_above_limit(self) -> None:
        plants = FakePlayerPowerPlants(max_plants=2)
        context = PlayerBoardContext(FakeResourceMarket(), FakeResourcePool())
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 50), plants, context
        )

        self.assertTrue(facade.receive_power_plant(self._coal_plant(4), 4))
        self.assertEqual(facade.outstanding_money(), 46)

        self.assertTrue(facade.receive_power_plant(self._oil_plant(6), 0))
        self.assertEqual(facade.outstanding_money(), 46)

        self.assertFalse(facade.receive_power_plant(self._wind_plant(13), 46))
        self.assertEqual(facade.outstanding_money(), 0)
        self.assertEqual(len(facade.power_plants), 3)

    def test_receive_power_plant_rejects_invalid_atomically(self) -> None:
        plants = FakePlayerPowerPlants([self._coal_plant(4)])
        context = PlayerBoardContext(FakeResourceMarket(), FakeResourcePool())
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 10), plants, context
        )

        with self.assertRaises(ValueError):
            facade.receive_power_plant(self._oil_plant(6), -1)
        self.assertEqual(len(facade.power_plants), 1)
        self.assertEqual(facade.outstanding_money(), 10)

        with self.assertRaises(ValueError):
            facade.receive_power_plant(self._oil_plant(6), 11)
        self.assertEqual(len(facade.power_plants), 1)
        self.assertEqual(facade.outstanding_money(), 10)

        with self.assertRaises(ValueError):
            facade.receive_power_plant(self._coal_plant(4), 5)
        self.assertEqual(len(facade.power_plants), 1)
        self.assertEqual(facade.outstanding_money(), 10)

    def test_remove_power_plant_returns_discarded_resources_to_pool(
        self,
    ) -> None:
        pool = FakeResourcePool()
        plants = FakePlayerPowerPlants(
            [self._coal_plant(4, fuel=1), self._oil_plant(3, fuel=1)]
        )
        context = PlayerBoardContext(FakeResourceMarket(), pool)
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 50),
            plants,
            context,
            [Resource.COAL, Resource.COAL, Resource.OIL],
        )

        err = facade.remove_power_plant(
            PowerPlantNumber(4), [Resource.COAL, Resource.COAL]
        )
        self.assertIsNone(err)
        self.assertEqual(facade.resources, [Resource.OIL])
        self.assertEqual(
            [plant.number.number for plant in facade.power_plants], [3]
        )
        self.assertEqual(pool.returned, [[Resource.COAL, Resource.COAL]])

    def test_remove_power_plant_empty_discard_skips_pool(self) -> None:
        pool = FakeResourcePool()
        plants = FakePlayerPowerPlants(
            [self._coal_plant(4), self._wind_plant(13)]
        )
        context = PlayerBoardContext(FakeResourceMarket(), pool)
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 50), plants, context
        )

        self.assertIsNone(facade.remove_power_plant(PowerPlantNumber(13), []))
        self.assertEqual(pool.returned, [])

    def test_remove_power_plant_atomic_on_errors(self) -> None:
        pool = FakeResourcePool()
        plants = FakePlayerPowerPlants(
            [self._coal_plant(4, fuel=1), self._oil_plant(3, fuel=1)]
        )
        context = PlayerBoardContext(FakeResourceMarket(), pool)
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 50),
            plants,
            context,
            [Resource.COAL, Resource.OIL],
        )

        # Does not own duplicate coal
        err1 = facade.remove_power_plant(
            PowerPlantNumber(4), [Resource.COAL, Resource.COAL]
        )
        self.assertIsInstance(err1, RequestError)

        # Plant not owned
        err2 = facade.remove_power_plant(PowerPlantNumber(99), [Resource.COAL])
        self.assertIsInstance(err2, RequestError)

        # Remaining coal does not fit on remaining oil plant
        err3 = facade.remove_power_plant(PowerPlantNumber(4), [])
        self.assertIsInstance(err3, RequestError)

        self.assertEqual(facade.resources, [Resource.COAL, Resource.OIL])
        self.assertEqual(
            [plant.number.number for plant in facade.power_plants], [4, 3]
        )
        self.assertEqual(pool.returned, [])

    def test_buy_resources_empty_and_success(self) -> None:
        market = FakeResourceMarket({Resource.COAL: 3, Resource.OIL: 4})
        plants = FakePlayerPowerPlants([self._coal_plant(4, fuel=2)])
        context = PlayerBoardContext(market, FakeResourcePool())
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 20), plants, context
        )

        self.assertIsNone(facade.buy_resources([]))
        self.assertEqual(market.taken, [])
        self.assertEqual(facade.outstanding_money(), 20)

        self.assertIsNone(
            facade.buy_resources([Resource.COAL, Resource.COAL])
        )
        self.assertEqual(facade.resources, [Resource.COAL, Resource.COAL])
        self.assertEqual(facade.outstanding_money(), 14)
        self.assertEqual(market.taken, [[Resource.COAL, Resource.COAL]])

    def test_buy_resources_atomic_on_errors(self) -> None:
        market = FakeResourceMarket(
            {Resource.COAL: 15, Resource.OIL: 5},
            unavailable={Resource.OIL},
        )
        plants = FakePlayerPowerPlants(
            [self._coal_plant(4, fuel=1), self._oil_plant(3, fuel=1)]
        )
        context = PlayerBoardContext(market, FakeResourcePool())
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 20),
            plants,
            context,
            [Resource.COAL],
        )

        # Storage full (capacity 2 coal, already owns 1, asks for 2)
        err1 = facade.buy_resources([Resource.COAL, Resource.COAL])
        self.assertIsInstance(err1, RequestError)

        # Market unavailable
        err2 = facade.buy_resources([Resource.OIL])
        self.assertIsInstance(err2, RequestError)

        # Insufficient money (cost 15, has 10)
        facade.spend_money(10)
        err3 = facade.buy_resources([Resource.COAL])
        self.assertIsInstance(err3, RequestError)

        self.assertEqual(facade.resources, [Resource.COAL])
        self.assertEqual(facade.outstanding_money(), 10)
        self.assertEqual(market.taken, [])

    def test_use_power_plants_zero_cities_pays_ten(self) -> None:
        pool = FakeResourcePool()
        towns = FakeTowns()
        towns.set_house_count(PlayerColor.RED, 3)
        context = PlayerBoardContext(FakeResourceMarket(), pool, towns)
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 5),
            FakePlayerPowerPlants([self._coal_plant(4, fuel=1, cities=2)]),
            context,
            [Resource.COAL],
        )

        self.assertIsNone(facade.use_power_plants([], []))
        self.assertEqual(facade.outstanding_money(), 15)
        self.assertEqual(facade.resources, [Resource.COAL])
        self.assertEqual(pool.returned, [])

    def test_use_power_plants_house_cap_and_zero_houses(self) -> None:
        pool = FakeResourcePool()
        towns = FakeTowns()
        towns.set_house_count(PlayerColor.RED, 0)
        context = PlayerBoardContext(FakeResourceMarket(), pool, towns)
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 0),
            FakePlayerPowerPlants([self._coal_plant(4, fuel=1, cities=4)]),
            context,
            [Resource.COAL, Resource.COAL],
        )

        # Owns 0 houses -> capped to 0 -> 10 Elektro, coal still burned
        self.assertIsNone(
            facade.use_power_plants([PowerPlantNumber(4)], [Resource.COAL])
        )
        self.assertEqual(facade.outstanding_money(), 10)
        self.assertEqual(facade.resources, [Resource.COAL])
        self.assertEqual(pool.returned, [[Resource.COAL]])

        # Owns 2 houses < 4 powered -> capped to 2 -> +33 Elektro
        towns.set_house_count(PlayerColor.RED, 2)
        self.assertIsNone(
            facade.use_power_plants([PowerPlantNumber(4)], [Resource.COAL])
        )
        self.assertEqual(facade.outstanding_money(), 43)
        self.assertEqual(facade.resources, [])
        self.assertEqual(pool.returned, [[Resource.COAL], [Resource.COAL]])

    def test_use_power_plants_owned_houses_greater_and_over_twenty(
        self,
    ) -> None:
        pool = FakeResourcePool()
        towns = FakeTowns()
        towns.set_house_count(PlayerColor.RED, 25)
        context = PlayerBoardContext(FakeResourceMarket(), pool, towns)
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 0),
            FakePlayerPowerPlants(
                [
                    self._wind_plant(13, cities=3),
                    self._wind_plant(50, cities=21),
                ]
            ),
            context,
        )

        # 3 cities powered < 25 houses -> PAYMENT_TABLE[3] = 44
        self.assertIsNone(facade.use_power_plants([PowerPlantNumber(13)], []))
        self.assertEqual(facade.outstanding_money(), 44)
        self.assertEqual(pool.returned, [])

        # 21 cities powered -> capped to index 20 -> PAYMENT_TABLE[20] = 150
        self.assertIsNone(facade.use_power_plants([PowerPlantNumber(50)], []))
        self.assertEqual(facade.outstanding_money(), 194)

    def test_use_power_plants_without_towns_and_negative_clamping(
        self,
    ) -> None:
        pool = FakeResourcePool()
        # towns=None -> pays full plant capacity (3 -> 44)
        facade_no_towns = PlayerBoardFacade(
            PlayerMoney(PlayerColor.BLUE, 0),
            FakePlayerPowerPlants([self._wind_plant(13, cities=3)]),
            PlayerBoardContext(FakeResourceMarket(), pool, None),
        )
        self.assertIsNone(
            facade_no_towns.use_power_plants([PowerPlantNumber(13)], [])
        )
        self.assertEqual(facade_no_towns.outstanding_money(), 44)

        # Negative owned houses -> clamped to 0 -> 10 (NOT PAYMENT_TABLE[-1]=150)
        facade_neg_houses = PlayerBoardFacade(
            PlayerMoney(PlayerColor.BLUE, 0),
            FakePlayerPowerPlants([self._wind_plant(13, cities=3)]),
            PlayerBoardContext(
                FakeResourceMarket(), pool, NegativeTownsFake(-2)
            ),
        )
        self.assertIsNone(
            facade_neg_houses.use_power_plants([PowerPlantNumber(13)], [])
        )
        self.assertEqual(facade_neg_houses.outstanding_money(), 10)

        # Negative return from use_power_plant -> clamped to 0 -> 10
        mut_plants = MutatingPlayerPowerPlants([self._wind_plant(13, cities=3)])
        mut_plants.override_use_result = -3
        facade_neg_use = PlayerBoardFacade(
            PlayerMoney(PlayerColor.BLUE, 0),
            mut_plants,
            PlayerBoardContext(FakeResourceMarket(), pool, None),
        )
        self.assertIsNone(
            facade_neg_use.use_power_plants([PowerPlantNumber(13)], [])
        )
        self.assertEqual(facade_neg_use.outstanding_money(), 10)

    def test_use_power_plants_atomic_on_errors(self) -> None:
        pool = FakeResourcePool()
        context = PlayerBoardContext(FakeResourceMarket(), pool)
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 25),
            FakePlayerPowerPlants([self._coal_plant(4, fuel=2, cities=2)]),
            context,
            [Resource.COAL],
        )

        # Does not own 2 coal
        err1 = facade.use_power_plants(
            [PowerPlantNumber(4)], [Resource.COAL, Resource.COAL]
        )
        self.assertIsInstance(err1, RequestError)

        # Not enough coal for plant (needs 2, passes 1)
        err2 = facade.use_power_plants([PowerPlantNumber(4)], [Resource.COAL])
        self.assertIsInstance(err2, RequestError)

        # Plant not owned
        err3 = facade.use_power_plants([PowerPlantNumber(99)], [])
        self.assertIsInstance(err3, RequestError)

        self.assertEqual(facade.outstanding_money(), 25)
        self.assertEqual(facade.resources, [Resource.COAL])
        self.assertEqual(pool.returned, [])

    def test_state_returns_valid_json(self) -> None:
        plants = FakePlayerPowerPlants(
            [self._coal_plant(4), self._wind_plant(13)]
        )
        context = PlayerBoardContext(FakeResourceMarket(), FakeResourcePool())
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.YELLOW, 77),
            plants,
            context,
            [Resource.COAL],
        )

        parsed = json.loads(facade.state())
        self.assertEqual(
            parsed,
            {
                "color": "YELLOW",
                "money": 77,
                "power_plants": [4, 13],
                "resources": ["COAL"],
            },
        )

    def test_defensive_copies_against_mutating_collaborators(self) -> None:
        pool = FakeResourcePool()
        market = MutatingResourceMarket({Resource.COAL: 2})
        plants = MutatingPlayerPowerPlants(
            [self._coal_plant(4, fuel=1, cities=2), self._wind_plant(13)]
        )
        context = PlayerBoardContext(market, pool)
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 50),
            plants,
            context,
            [Resource.COAL],
        )

        # D5: __init__ must not lose initial resources when can_store mutates arg
        self.assertEqual(facade.resources, [Resource.COAL])

        # D5: number_of_connectable_cities must not alias internal _resources
        self.assertEqual(facade.number_of_connectable_cities(), 5)
        self.assertEqual(facade.resources, [Resource.COAL])

        # D5: buy_resources must not lose bought resources if market mutates arg
        self.assertIsNone(facade.buy_resources([Resource.COAL]))
        self.assertEqual(facade.resources, [Resource.COAL, Resource.COAL])

        # D5: remove_power_plant must not lose remaining resources on mutation
        self.assertIsNone(facade.remove_power_plant(PowerPlantNumber(13), []))
        self.assertEqual(facade.resources, [Resource.COAL, Resource.COAL])

        # D4 + D5: use_power_plants must pass list(ppns) and return full burn list
        self.assertIsNone(
            facade.use_power_plants(
                (PowerPlantNumber(4),), [Resource.COAL]
            )
        )
        self.assertTrue(plants.last_ppns_was_list)
        self.assertEqual(pool.returned, [[Resource.COAL]])
        self.assertEqual(facade.resources, [Resource.COAL])

    def test_strict_list_typed_player_power_plants_protocol_compat(
        self,
    ) -> None:
        strict_plants = StrictListPlayerPowerPlants(
            [self._coal_plant(4), self._wind_plant(13)]
        )
        facade = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 50),
            strict_plants,
            PlayerBoardContext(FakeResourceMarket(), FakeResourcePool()),
            (Resource.COAL,),
        )
        self.assertEqual(facade.number_of_connectable_cities(), 1)
        self.assertIsNone(facade.remove_power_plant(PowerPlantNumber(13), ()))
        self.assertIsNone(
            facade.use_power_plants((PowerPlantNumber(4),), (Resource.COAL,))
        )
        self.assertEqual(strict_plants.types_checked, [True, True, True, True])
