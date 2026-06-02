"""
LLM client interface + a deterministic offline Mock implementation.

A client is a thin text-completion wrapper: `complete(system, user) -> str`.
Prompt building and response parsing live in `llm/prompt.py`, so clients stay
provider-agnostic.
"""
from __future__ import annotations
import json
import re
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Minimal text-completion interface every backend implements."""

    name: str = "llm"

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Return the model's text reply to a system + user prompt."""
        ...


class MockLLMClient(LLMClient):
    """
    Deterministic, offline 'model' for tests and no-network demos.

    It reads the `CONTEXT: {json}` line embedded in the user prompt and applies a
    small value/momentum/survival heuristic, returning the same JSON schema a real
    model would. Lets the whole LLM pipeline run (and be tested) with no backend.
    """

    name = "mock"

    def __init__(self, trade_size: int = 4):
        self.trade_size = trade_size

    def complete(self, system: str, user: str) -> str:
        ctx = self._extract_context(user)
        if ctx is None:
            return json.dumps({"action": "HOLD", "price": None, "quantity": 0,
                               "reasoning": "mock: no context"})
        return json.dumps(self._decide(ctx))

    @staticmethod
    def _extract_context(user: str) -> dict | None:
        m = re.search(r"CONTEXT:\s*(\{.*\})\s*$", user, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except (ValueError, TypeError):
            return None

    def _decide(self, ctx: dict) -> dict:
        price   = ctx.get("price") or 20.0
        fv      = ctx.get("fair_value") or price
        inv     = ctx.get("my_inventory", 0)
        cash    = ctx.get("my_cash", 0.0)
        runway  = ctx.get("ticks_of_food_left")
        momentum = ctx.get("momentum_pct", 0.0)

        # 1) Survival first: about to starve and can afford a unit -> buy up
        if runway is not None and runway < 2 and cash >= price:
            bid = round(price * 1.05, 2)
            qty = max(1, min(self.trade_size, int(cash // bid)))
            return {"action": "BID", "price": bid, "quantity": qty,
                    "reasoning": "mock: low on food, securing supply"}

        # 2) Value: cheap vs fair -> buy
        if price < fv * 0.97 and cash >= price:
            qty = max(1, min(self.trade_size, int(cash // price)))
            return {"action": "BID", "price": round(price, 2), "quantity": qty,
                    "reasoning": "mock: below fair value, accumulating"}

        # 3) Value: rich vs fair and holding stock -> sell
        if price > fv * 1.03 and inv > 0:
            qty = min(self.trade_size, inv)
            return {"action": "ASK", "price": round(price, 2), "quantity": qty,
                    "reasoning": "mock: above fair value, taking profit"}

        # 4) Momentum nudge
        if momentum > 3 and cash >= price:
            qty = max(1, min(self.trade_size, int(cash // price)))
            return {"action": "BID", "price": round(price * 1.02, 2), "quantity": qty,
                    "reasoning": "mock: riding upward momentum"}

        return {"action": "HOLD", "price": None, "quantity": 0,
                "reasoning": "mock: no edge, holding"}
