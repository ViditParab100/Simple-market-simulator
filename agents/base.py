from __future__ import annotations
import math
from abc import ABC, abstractmethod
from market.models import Order, OrderSide, MarketState, Trade
from market.haggle import HaggleIntent

_DEFAULT_PRICE = 20.0


class Agent(ABC):
    def __init__(self, agent_id: str, inventory: int, cash: float):
        self.agent_id = agent_id
        self.inventory = inventory
        self.cash = cash
        self.trade_count = 0

        # ── Consumption / survival (opt-in; engine sets the rate) ──────────
        self.consumption_rate: float = 0.0     # units burned for survival each tick
        self.survival_threshold: int = 3       # restock when runway < this many ticks
        self.consumed_total: float = 0.0       # lifetime units consumed
        self.starved_ticks: int = 0            # ticks where ration couldn't be met

        # ── Production (only ProducerAgent overrides this) ─────────────────
        self.produced_total: float = 0.0       # lifetime units minted into the market

    @abstractmethod
    def think(self, state: MarketState) -> list[str]:
        """Return lines of internal reasoning. Runs before act() each tick."""
        ...

    @abstractmethod
    def act(self, state: MarketState) -> list[Order]:
        """Return orders to submit this tick."""
        ...

    def on_trade(self, trade: Trade):
        if trade.buyer_id == self.agent_id:
            self.trade_count += 1
            self.inventory += trade.quantity
            self.cash -= trade.price * trade.quantity
        elif trade.seller_id == self.agent_id:
            self.trade_count += 1
            self.inventory -= trade.quantity
            self.cash += trade.price * trade.quantity

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        """
        Return a pre-tick negotiation intent, or None to skip haggling.
        Override in each subclass to express archetype-specific thresholds.
        """
        return None

    # ── Consumption / survival ─────────────────────────────────────────────

    def consume(self) -> tuple[float, bool]:
        """
        Burn this tick's survival ration from inventory.
        Returns (units_consumed, starved) where starved is True if the agent
        could not cover its full ration. Called by the engine each tick.
        """
        if self.consumption_rate <= 0:
            return 0.0, False
        want = self.consumption_rate
        got  = min(want, self.inventory)
        self.inventory -= got
        self.consumed_total += got
        starved = got < want
        if starved:
            self.starved_ticks += 1
        return got, starved

    def runway(self) -> float:
        """Ticks of survival left at the current consumption rate (inf if not consuming)."""
        if self.consumption_rate <= 0:
            return float("inf")
        return self.inventory / self.consumption_rate

    def produce(self) -> float:
        """
        Mint new units into the agent's inventory. Base agents produce nothing;
        only ProducerAgent overrides this. Called by the engine each tick.
        Returns units produced.
        """
        return 0.0

    def survival_order(self, state: MarketState) -> Order | None:
        """
        When survival runway is short, bid ABOVE market to secure supply
        rather than starve. The bid escalates as starvation approaches.
        This is what keeps an otherwise-frozen market liquid. Shared by all
        archetypes; the engine appends it to each agent's regular orders.
        """
        if self.consumption_rate <= 0:
            return None
        runway = self.runway()
        if runway >= self.survival_threshold:
            return None  # comfortable buffer — no panic buying

        price = state.last_price or _DEFAULT_PRICE
        # urgency 0..1: 0 at the threshold, ~1 when out of stock
        urgency   = max(0.0, min(1.0, (self.survival_threshold - runway) / self.survival_threshold))
        bid_price = round(price * (1.0 + 0.05 + 0.20 * urgency), 2)  # 5%..25% over market

        # Aim to top back up to a full threshold buffer
        target_units = math.ceil(self.consumption_rate * self.survival_threshold)
        need = max(1, target_units - int(self.inventory))

        affordable = int(self.cash // bid_price)
        qty = min(need, affordable)
        if qty <= 0:
            return None
        return Order(self.agent_id, OrderSide.BID, bid_price, qty, state.tick)

    def net_worth(self, market_price: float) -> float:
        return self.cash + self.inventory * market_price
