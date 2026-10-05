"""MCP server "meals": four recipe tools over the public TheMealDB API (HW5 Part 2A).

    mcp dev code/mcp_servers/meals_server.py      # MCP Inspector in the browser
    python code/mcp_servers/meals_server.py       # plain STDIO server

Uses TheMealDB's published test key "1" (no account needed). STDIO rule:
nothing is ever printed to stdout (that is the JSON-RPC stream) - all logs go
to stderr through `logging`.

No results ("meals": null) -> an empty result with message "no matches".
Network / HTTP / JSON failures -> ToolError, which the Inspector shows as a
tool error.
"""
from __future__ import annotations

import logging
import sys
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(levelname)s meals: %(message)s")
log = logging.getLogger("meals")

API_BASE = "https://www.themealdb.com/api/json/v1/1"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)

mcp = FastMCP("meals")

# Read-only calls to an external public API (TheMealDB).
READ_ONLY_WEB = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def _get(endpoint: str, params: dict[str, str] | None = None) -> list[dict] | None:
    """GET {API_BASE}/{endpoint}; returns the "meals" list, or None for no results."""
    url = f"{API_BASE}/{endpoint}"
    log.info("GET %s %s", url, params or {})
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.TimeoutException as exc:
        raise ToolError(f"TheMealDB timed out ({endpoint}): {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise ToolError(f"TheMealDB returned HTTP {exc.response.status_code} for {endpoint}") from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"Network error calling TheMealDB ({endpoint}): {exc}") from exc
    except ValueError as exc:  # json.JSONDecodeError
        raise ToolError(f"TheMealDB returned invalid JSON for {endpoint}") from exc
    if not isinstance(payload, dict) or "meals" not in payload:
        raise ToolError(f"Unexpected TheMealDB response shape for {endpoint}")
    return payload["meals"]


def _ingredients(meal: dict) -> list[dict[str, str]]:
    out = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        if name:
            out.append({"name": name, "measure": (meal.get(f"strMeasure{i}") or "").strip()})
    return out


def _details(meal: dict) -> dict[str, Any]:
    return {
        "id": meal["idMeal"],
        "name": meal["strMeal"],
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource") or None,
        "youtube": meal.get("strYoutube") or None,
        "ingredients": _ingredients(meal),
    }


@mcp.tool(annotations=READ_ONLY_WEB)
async def search_meals_by_name(
    query: Annotated[str, Field(min_length=1, description="Meal name or part of it, e.g. 'Arrabiata'")],
    limit: Annotated[int, Field(ge=1, le=25, description="Max meals to return (1-25)")] = 5,
) -> dict[str, Any]:
    """Search meals by name. Returns up to `limit` meals: id, name, area, category, thumb."""
    meals = await _get("search.php", {"s": query})
    if not meals:
        return {"count": 0, "results": [], "message": f"no matches for '{query}'"}
    results = [
        {"id": m["idMeal"], "name": m["strMeal"], "area": m.get("strArea"),
         "category": m.get("strCategory"), "thumb": m.get("strMealThumb")}
        for m in meals[:limit]
    ]
    return {"count": len(results), "results": results, "message": None}


@mcp.tool(annotations=READ_ONLY_WEB)
async def meals_by_ingredient(
    ingredient: Annotated[str, Field(min_length=1, description="Main ingredient, e.g. 'chicken'")],
    limit: Annotated[int, Field(ge=1, le=100, description="Max meals to return")] = 12,
) -> dict[str, Any]:
    """Filter meals by main ingredient. Returns small cards: id, name, thumb."""
    meals = await _get("filter.php", {"i": ingredient})
    if not meals:
        return {"count": 0, "results": [], "message": f"no matches for ingredient '{ingredient}'"}
    results = [{"id": m["idMeal"], "name": m["strMeal"], "thumb": m.get("strMealThumb")} for m in meals[:limit]]
    return {"count": len(results), "results": results, "message": None}


@mcp.tool(annotations=READ_ONLY_WEB)
async def meal_details(
    id: Annotated[str | int, Field(description="TheMealDB meal id, e.g. 52771")],
) -> dict[str, Any]:
    """Full recipe for one meal id: id, name, category, area, instructions, image,
    source, youtube, ingredients [{name, measure}]."""
    meal_id = str(id).strip()
    if not meal_id.isdigit():
        raise ToolError(f"id must be a numeric TheMealDB id, got {id!r}")
    meals = await _get("lookup.php", {"i": meal_id})
    if not meals:
        return {"id": meal_id, "message": "no matches"}
    return _details(meals[0])


@mcp.tool(annotations=READ_ONLY_WEB)
async def random_meal() -> dict[str, Any]:
    """One random meal, same shape as meal_details."""
    meals = await _get("random.php")
    if not meals:
        return {"message": "no matches"}
    return _details(meals[0])


if __name__ == "__main__":
    log.info("starting meals MCP server over STDIO")
    mcp.run()  # transport="stdio"
