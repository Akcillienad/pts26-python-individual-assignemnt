import json
from typing import Sequence

from power_grid.interfaces import InterfaceResourcePoolResourceMarket
from power_grid.simple_types import Resource


class ResourcePool(InterfaceResourcePoolResourceMarket):

    def __init__(
        self, resources: list[Resource], storage_space: list[Resource]
    ) -> None:
        self.resources = resources.copy()
        self.storage_space = storage_space.copy()

    # Kontrola ci mame dostatok surovin v sklade
    def can_take_resources_from_storage_space(
        self, resources: Sequence[Resource]
    ) -> bool:
        sklad = self.storage_space.copy()
        for resource in resources:
            if resource in sklad:
                sklad.remove(resource)
            else:
                return False
        return True

    # Odobratie surovin zo skladu
    def get_from_storage_space(self, resources: Sequence[Resource]) -> None:
        if self.can_take_resources_from_storage_space(resources):
            for resource in resources:
                self.storage_space.remove(resource)
        else:
            assert False, "Not enough resources"

    # Odobratie surovin z hlavnej zasoby
    def take_resources(self, resources: Sequence[Resource]) -> list[Resource]:
        vysledok: list[Resource] = []
        for resource in resources:
            if resource in self.resources:
                self.resources.remove(resource)
                vysledok.append(resource)
        return vysledok

    # Pridanie surovin do zasoby
    def put_resources(self, resources: list[Resource]) -> None:
        for resource in resources:
            self.resources.append(resource)

    # Textovy vypis zasob
    def to_string(self) -> str:
        suroviny = [resource.name for resource in self.resources]
        sklad = [resource.name for resource in self.storage_space]
        vysledok = {
            "resources": suroviny,
            "storage_space": sklad,
        }
        return json.dumps(vysledok)
