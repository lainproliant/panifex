# --------------------------------------------------------------------
# poly.py: Meta-recipe aggregates for parallel and sequential recipes.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# -------------------------------------------------------------------
import asyncio
from typing import Any

from .recipes import Recipe
from .reports import Report
from .errors import AggregateError


# -------------------------------------------------------------------
class PolyRecipe(Recipe):
    def __init__(self, recipes):
        super().__init__()
        self.recipes = list(recipes)

    async def resolve(self) -> Any:
        raise NotImplementedError()

    async def clean(self) -> None:
        raise NotImplementedError()

    async def output(self) -> Any:
        return [r.output() for r in self.recipes]

    def is_done(self) -> bool:
        return all(r.is_done() for r in self.recipes)

    def succeeded(self) -> bool:
        return all(r.succeeded() for r in self.recipes)


# --------------------------------------------------------------------
class PolyRecipeReport(Report):
    def __init__(self, poly_recipe: PolyRecipe):
        self._poly_recipe = poly_recipe
        self._sub_reports = [r.report() for r in self._poly_recipe.recipes]
        self._sub_reports.sort(key=lambda x: x.started)

    def succeeded(self):
        return all(r.succeeded for r in self._sub_reports)

    def generate(self):
        return {**super().generate(), "jobs": self._sub_reports}


# -------------------------------------------------------------------
class SequentialRecipe(PolyRecipe):
    def __init__(self, *recipes):
        super().__init__(recipes)

    async def resolve(self) -> Any:
        for recipe in self.recipes:
            await recipe.resolve()

    async def clean(self) -> None:
        for recipe in self.recipes:
            await recipe.clean()

    def report(self) -> Report:
        return PolyRecipeReport(self)


# -------------------------------------------------------------------
class ParallelRecipe(PolyRecipe):
    def __init__(self, *recipes):
        super().__init__(recipes)

    async def resolve(self) -> Any:
        AggregateError.aggregate(
            *await asyncio.gather(
                *[recipe.resolve() for recipe in self.recipes], return_exceptions=True
            )
        )

    async def clean(self) -> None:
        AggregateError.aggregate(
            *await asyncio.gather(
                *[recipe.clean() for recipe in self.recipes], return_exceptions=True
            )
        )

    def report(self) -> Report:
        return PolyRecipeReport(self)


# -------------------------------------------------------------------
sequence = SequentialRecipe
parallel = ParallelRecipe
