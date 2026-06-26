from __future__ import annotations
import math
from abc import ABC, abstractmethod
from market.models import Order, OrderSide, MarketState, Trade
from market.haggle import HaggleIntent
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.auction import AuctionLot

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

        # ── Survival / death ───────────────────────────────────────────────
        self.alive: bool = True                # False once knocked out
        self.starvation_limit: int = 3         # consecutive starved ticks -> death
        self.consecutive_starved: int = 0      # current starvation streak
        self.died_tick: int | None = None      # tick the agent went out

        # ── Production (only ProducerAgent overrides this) ─────────────────
        self.produced_total: float = 0.0       # lifetime units minted into the market

        # ── Salaries / cash recirculation ─────────────────────────────────
        self.is_employer: bool = False         # employers pay wages to workers
        self.wages_received: float = 0.0       # lifetime wages received (workers)
        self.wages_paid: float = 0.0           # lifetime wages paid (employers)

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

    def auction_bid(
        self,
        lot: "AuctionLot",
        current_price: float,
        round_num: int,
        state: MarketState,
    ) -> float | None:
        """
        Return the maximum price-per-unit this agent is willing to pay for the
        auction lot at this round, or None to drop out permanently.

        Base behaviour: drop out if the lot is unaffordable; otherwise submit a
        survival bid (15 % above market) when starvation is imminent.
        Subclasses call super() first and layer strategy on top.
        """
        if self.cash < current_price * lot.quantity:
            return None
        if self.consumption_rate > 0 and self.runway() < self.survival_threshold:
            return round(lot.market_price * 1.15, 2)
        return None

    # ── Consumption / survival ─────────────────────────────────────────────

    def consume(self, tick: int | None = None) -> tuple[float, bool]:
        """
        Burn this tick's survival ration from inventory.
        Returns (units_consumed, starved) where starved is True if the agent
        could not cover its full ration. Called by the engine each tick.

        A starvation streak of `starvation_limit` consecutive ticks knocks the
        agent out (alive = False) — it can no longer trade.
        """
        if self.consumption_rate <= 0 or not self.alive:
            return 0.0, False
        want = self.consumption_rate
        got  = min(want, self.inventory)
        self.inventory -= got
        self.consumed_total += got
        starved = got < want
        if starved:
            self.starved_ticks += 1
            self.consecutive_starved += 1
            if self.consecutive_starved >= self.starvation_limit:
                self.alive = False
                self.died_tick = tick
        else:
            self.consecutive_starved = 0
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

        # Reference the cheapest available offer, not the (possibly runaway) last
        # trade price. Bidding a small premium over the current best ask is enough
        # to win supply without spiralling prices upward each tick.
        reference = state.best_ask if state.best_ask is not None else (state.last_price or _DEFAULT_PRICE)
        # urgency 0..1: 0 at the threshold, ~1 when out of stock
        urgency   = max(0.0, min(1.0, (self.survival_threshold - runway) / self.survival_threshold))
        bid_price = round(reference * (1.0 + 0.03 + 0.12 * urgency), 2)  # 3%..15% over best ask

        # Aim to top back up to a full threshold buffer
        target_units = math.ceil(self.consumption_rate * self.survival_threshold)
        need = max(1, target_units - int(self.inventory))

        affordable = int(self.cash // bid_price)
        qty = min(need, affordable)
        if qty <= 0:
            return None
        return Order(self.agent_id, OrderSide.BID, bid_price, qty, state.tick)

    def trade_remark(self, role: str, price: float, qty: int) -> str:
        """
        A short line the agent 'says' when it completes a trade.
        role is 'buyer' or 'seller'. Overridden per archetype for flavour.
        """
        if role == "buyer":
            return f"Bought {qty} @ ${price:.2f}."
        return f"Sold {qty} @ ${price:.2f}."

    def net_worth(self, market_price: float) -> float:
        return self.cash + self.inventory * market_price
