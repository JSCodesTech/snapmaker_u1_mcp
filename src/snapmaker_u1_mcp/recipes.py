from __future__ import annotations

from .errors import ConfigurationError

RECIPES: dict[str, dict] = {
    "pla-draft": {
        "description": "Fast PLA draft: thicker layers, modest walls, low infill.",
        "material": "PLA",
        "overrides": {"layer_height": 0.24, "wall_loops": 2, "sparse_infill_density": 10},
    },
    "pla-strong": {
        "description": "Stronger PLA part: more walls and infill.",
        "material": "PLA",
        "overrides": {"wall_loops": 5, "sparse_infill_density": 25},
    },
    "petg-strong": {
        "description": "Mechanical PETG starting point: more walls and moderate infill.",
        "material": "PETG",
        "overrides": {"wall_loops": 5, "sparse_infill_density": 25, "brim_type": "outer_only"},
    },
    "support-check": {
        "description": "Support experiment: enable supports for comparison.",
        "overrides": {"enable_support": True},
    },
}


def u1_list_recipes() -> dict:
    return {"status": "ok", "recipes": {name: {k: v for k, v in recipe.items() if k != "overrides"} | {"overrides": recipe["overrides"]} for name, recipe in RECIPES.items()}}


def u1_get_recipe(name: str) -> dict:
    recipe = RECIPES.get(name)
    if not recipe:
        raise ConfigurationError(f"Unknown recipe {name!r}; available: {sorted(RECIPES)}")
    return {"status": "ok", "name": name, **recipe}


def u1_compare_recipes(
    model: str,
    process: str,
    filament: str,
    recipes: list[str],
    nozzle: float = 0.4,
    verbose: bool = False,
) -> dict:
    """Slice one process with multiple built-in recipe override sets."""
    if not recipes:
        raise ConfigurationError("recipes must be a non-empty list")
    variants = []
    for name in recipes:
        recipe = RECIPES.get(name)
        if not recipe:
            raise ConfigurationError(f"Unknown recipe {name!r}; available: {sorted(RECIPES)}")
        variants.append({"name": name, "process": process, "overrides": recipe["overrides"]})
    from .slicer import u1_compare_slices
    result = u1_compare_slices(model=model, filament=filament, variants=variants, nozzle=nozzle, verbose=verbose)
    result["recipe_comparison"] = True
    result["recipes"] = {name: RECIPES[name] for name in recipes}
    return result
