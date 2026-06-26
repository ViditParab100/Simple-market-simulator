"""
Prompt construction and response parsing for LLM-backed agents.

A decision prompt gives the model a compact market snapshot plus the agent's
persona, and asks for a single JSON object:

    {"action": "BID"|"ASK"|"HOLD", "price": <number>, "quantity": <int>,
     "reasoning": "<short>"}

The user message also carries a machine-readable `CONTEXT: {json}` line so the
offline MockLLMClient can make a sensible heuristic decision without a real model.
"""
from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.models import MarketState


def fair_value(state: "MarketState") -> float:
    ph = state.price_history
    if not ph:
        return state.last_price or 20.0
    window = ph[-10:]
    return sum(window) / len(window)


def build_context(state: "MarketState", agent) -> dict:
    """Compact, model-readable view of the market + the agent's own position."""
    price = state.last_price or 20.0
    fv    = round(fair_value(state), 2)
    runway = agent.runway()
    return {
        "tick":        state.tick,
        "price":       round(price, 2),
        "fair_value":  fv,
        "best_bid":    round(state.best_bid, 2) if state.best_bid else None,
        "best_ask":    round(state.best_ask, 2) if state.best_ask else None,
        "momentum_pct": round(state.price_momentum * 100, 1),
        "scarcity":    round(state.scarcity_index, 2),
        "my_inventory": int(agent.inventory),
        "my_cash":     round(agent.cash, 2),
        "consumption_per_tick": agent.consumption_rate,
        "ticks_of_food_left": None if runway == float("inf") else round(runway, 1),
    }


_SYSTEM_TEMPLATE = (
    "Trader {name}. Style: {style}\n"
    "One order per tick. Eat {consume} unit(s)/tick or starve.\n"
    'Reply ONLY with JSON: {{"action":"BID"|"ASK"|"HOLD","price":<n>,"quantity":<int>,"reasoning":"<10 words max>"}}'
)


def build_decision_prompt(name: str, style: str, ctx: dict) -> tuple[str, str]:
    system = _SYSTEM_TEMPLATE.format(
        name=name, style=style, consume=ctx.get("consumption_per_tick", 0)
    )
    inv  = ctx["my_inventory"]
    cash = ctx["my_cash"]
    p    = ctx["price"]
    fv   = ctx["fair_value"]
    mom  = ctx["momentum_pct"]
    bid  = ctx["best_bid"]
    ask  = ctx["best_ask"]
    food = ctx["ticks_of_food_left"]
    human = (
        f"t{ctx['tick']} p${p:.2f} fv${fv:.2f} mom{mom:+.1f}% "
        f"bid={bid} ask={ask} inv={inv} cash=${cash:.0f} food={food}\n"
        f"CONTEXT:{json.dumps(ctx)}"
    )
    return system, human


_VALID_ACTIONS = {"BID", "ASK", "HOLD"}


def parse_decision(text: str) -> dict:
    """
    Extract the decision JSON from a model's reply. Tolerates code fences and
    surrounding prose. Returns a normalised dict; falls back to HOLD on failure.
    """
    fallback = {"action": "HOLD", "price": None, "quantity": 0,
                "reasoning": "unparseable model response"}
    if not text:
        return fallback

    # Strip ```json ... ``` fences if present
    cleaned = re.sub(r"```(?:json)?", "", text).strip()

    # Grab the first {...} block
    start = cleaned.find("{")
    end   = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return fallback
    blob = cleaned[start:end + 1]

    try:
        data = json.loads(blob)
    except (ValueError, TypeError):
        return fallback

    action = str(data.get("action", "HOLD")).upper().strip()
    if action not in _VALID_ACTIONS:
        action = "HOLD"

    price = data.get("price")
    try:
        price = float(price) if price is not None else None
    except (ValueError, TypeError):
        price = None

    try:
        quantity = int(float(data.get("quantity", 0)))
    except (ValueError, TypeError):
        quantity = 0

    reasoning = str(data.get("reasoning", "")).strip() or "(no reasoning given)"

    return {"action": action, "price": price, "quantity": quantity, "reasoning": reasoning}
