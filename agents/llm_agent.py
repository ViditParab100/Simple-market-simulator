from __future__ import annotations
from .base import Agent
from .rational import RationalAgent
from .producer import ProducerAgent
from market.models import Order, OrderSide, MarketState
from llm.client import LLMClient
from llm.prompt import build_context, build_decision_prompt, parse_decision
from llm.registry import make_clients

_DEFAULT_PRICE = 20.0

# Five distinct trading personas given to LLM-backed agents.
LLM_PERSONAS = [
    ("Ava",   "A disciplined value investor: buy below fair value, sell above, ignore hype."),
    ("Bryce", "An aggressive momentum trader: chase rising prices, cut losers fast."),
    ("Cleo",  "A hoarder who fears shortages: accumulate relentlessly, sell only at a steep premium."),
    ("Dane",  "A nervous, risk-averse trader: protect cash, sell quickly when prices fall."),
    ("Eve",   "A market maker: trade around fair value to earn the spread, stay balanced."),
]


class LLMAgent(Agent):
    """
    An agent whose decisions come from a language model.

    Each tick it builds a market-context prompt, asks the model for a JSON
    decision (BID / ASK / HOLD + price + quantity + reasoning), validates it
    against its cash/inventory, and submits the order. The model's reasoning
    becomes the agent's thought log.

    If the model is unreachable or returns garbage, the agent falls back to a
    rule-based RationalAgent so the simulation never stalls.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        client: LLMClient,
        persona_name: str,
        persona_style: str,
        max_trade: int = 8,
    ):
        super().__init__(agent_id, inventory, cash)
        self.client        = client
        self.persona_name  = persona_name
        self.persona_style = persona_style
        self.max_trade     = max_trade
        self._fallback     = RationalAgent(agent_id, inventory, cash)
        self._pending_orders: list[Order] = []
        self.last_reasoning: str = ""
        self.last_model: str = client.name

    # ── Agent interface ─────────────────────────────────────────────────────

    def think(self, state: MarketState) -> list[str]:
        ctx = build_context(state, self)
        system, user = build_decision_prompt(self.persona_name, self.persona_style, ctx)

        try:
            raw = self.client.complete(system, user)
            decision = parse_decision(raw)
        except Exception as e:  # model unavailable / network / etc.
            return self._use_fallback(state, reason=str(e))

        return self._decision_to_thoughts(decision, state, ctx)

    def act(self, state: MarketState) -> list[Order]:
        return self._pending_orders

    def trade_remark(self, role: str, price: float, qty: int) -> str:
        verb = "Bought" if role == "buyer" else "Sold"
        why  = self.last_reasoning or "model call"
        return f"{verb} {qty} @ ${price:.2f} — {why}"

    # ── Internals ───────────────────────────────────────────────────────────

    def _decision_to_thoughts(self, decision: dict, state: MarketState, ctx: dict) -> list[str]:
        action   = decision["action"]
        reasoning = decision["reasoning"]
        self.last_reasoning = reasoning

        header = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${ctx['price']:.2f}",
            f"[{self.client.name}] persona: {self.persona_name}",
            f"Model says: {action} -- \"{reasoning}\"",
        ]

        price = decision.get("price")
        qty   = decision.get("quantity") or 0

        if action == "HOLD" or qty <= 0:
            self._pending_orders = []
            header.append("Decision: HOLD.")
            return header

        if price is None or price <= 0:
            price = ctx["price"]

        if action == "BID":
            affordable = int(self.cash // price)
            qty = max(0, min(qty, self.max_trade, affordable))
            if qty <= 0:
                self._pending_orders = []
                header.append("Wanted to BID but can't afford it. Holding.")
                return header
            self._pending_orders = [Order(self.agent_id, OrderSide.BID, round(price, 2), qty, state.tick)]
            header.append(f"Decision: BID {qty} @ ${price:.2f}")
        else:  # ASK
            qty = max(0, min(qty, self.max_trade, int(self.inventory)))
            if qty <= 0:
                self._pending_orders = []
                header.append("Wanted to ASK but holds no inventory. Holding.")
                return header
            self._pending_orders = [Order(self.agent_id, OrderSide.ASK, round(price, 2), qty, state.tick)]
            header.append(f"Decision: ASK {qty} @ ${price:.2f}")

        return header

    def _use_fallback(self, state: MarketState, reason: str) -> list[str]:
        self._fallback.inventory = self.inventory
        self._fallback.cash      = self.cash
        self.last_reasoning = "rule-based fallback"
        fb_thoughts = self._fallback.think(state)
        self._pending_orders = self._fallback.act(state)
        return [
            f"[{self.client.name} unavailable: {reason}]",
            "Falling back to rule-based logic:",
        ] + [f"  {t}" for t in fb_thoughts]


def build_llm_roster(spec: str, timeout: float = 60.0) -> list:
    """
    Build a market of LLM-backed traders plus a rule-based Producer (supply).

    `spec` is one or more comma-separated model specs (e.g. "ollama:llama3.2" or
    "ollama:llama3.2,openai:gpt-4o-mini"). Multiple specs are assigned to personas
    round-robin so you can watch different models trade head-to-head.
    """
    clients = make_clients(spec, timeout)
    multi   = len(clients) > 1

    agents: list = [
        ProducerAgent("Producer", inventory=12, cash=200.0, production_rate=25),
    ]
    for i, (name, style) in enumerate(LLM_PERSONAS):
        client = clients[i % len(clients)]
        tag    = client.name.split(":")[-1]
        agent_id = f"{name}[{tag}]" if multi else name
        agents.append(LLMAgent(
            agent_id, inventory=5, cash=600.0,
            client=client, persona_name=name, persona_style=style,
        ))
    return agents
