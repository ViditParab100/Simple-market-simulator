"""
Phase 4 — Event Pipeline.

Every significant market action produces a typed MarketEvent.
Events are published to the EventBus, which routes them to all
registered consumers in the order they subscribed.

Design:
  - EventBus is in-process (no broker required). The schema and
    producer/consumer pattern mirror Kafka's so swapping in a real
    broker later is a one-class change.
  - Consumers subscribe by EventType; the bus calls their handle()
    method synchronously after each publish().
  - The engine holds one EventBus reference and emits events after
    every settlement step. Consumers are independent and don't
    affect simulation state.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Callable


class EventType(str, Enum):
    TRADE           = "TRADE"           # any settled trade (order book)
    HAGGLE_TRADE    = "HAGGLE_TRADE"    # bilateral pre-market trade
    TICK_SUMMARY    = "TICK_SUMMARY"    # end-of-tick market snapshot
    ANOMALY         = "ANOMALY"         # flagged by AnomalyDetector


@dataclass
class MarketEvent:
    event_type:     EventType
    tick:           int
    timestamp:      str          # ISO-8601 UTC

    # Primary actor (buyer for trades, empty for summaries)
    agent_id:       str = ""

    # Trade fields (populated for TRADE / HAGGLE_TRADE)
    counterpart_id: str   = ""
    price:          float = 0.0
    quantity:       int   = 0
    inventory_post: int   = 0    # buyer's inventory after the trade
    cash_post:      float = 0.0  # buyer's cash after the trade

    # Tick-summary fields (populated for TICK_SUMMARY)
    last_price:     float | None = None
    bid_depth:      int          = 0
    ask_depth:      int          = 0
    trades_this_tick: int        = 0

    # Anomaly / extra context
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> str:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return json.dumps(d)

    @staticmethod
    def now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()


# ── Event Bus ─────────────────────────────────────────────────────────────────

Consumer = Callable[[MarketEvent], None]


class EventBus:
    """
    In-process publish/subscribe bus.
    Consumers register a callable per EventType (or ALL to receive every event).
    """

    _ALL = "__ALL__"

    def __init__(self):
        self._handlers: dict[str, list[Consumer]] = {}

    def subscribe(self, event_type: EventType | None, handler: Consumer):
        """
        Subscribe handler to a specific EventType.
        Pass event_type=None to receive every event regardless of type.
        """
        key = self._ALL if event_type is None else event_type.value
        self._handlers.setdefault(key, []).append(handler)

    def publish(self, event: MarketEvent):
        for handler in self._handlers.get(event.event_type.value, []):
            handler(event)
        for handler in self._handlers.get(self._ALL, []):
            handler(event)


# ── Convenience factories ─────────────────────────────────────────────────────

def trade_event(trade, buyer_inventory: int, buyer_cash: float,
                tick: int, haggle: bool = False) -> MarketEvent:
    return MarketEvent(
        event_type     = EventType.HAGGLE_TRADE if haggle else EventType.TRADE,
        tick           = tick,
        timestamp      = MarketEvent.now_utc(),
        agent_id       = trade.buyer_id,
        counterpart_id = trade.seller_id,
        price          = trade.price,
        quantity       = trade.quantity,
        inventory_post = buyer_inventory,
        cash_post      = buyer_cash,
    )


def tick_summary_event(tick: int, last_price: float | None,
                       bid_depth: int, ask_depth: int,
                       trades_this_tick: int) -> MarketEvent:
    return MarketEvent(
        event_type       = EventType.TICK_SUMMARY,
        tick             = tick,
        timestamp        = MarketEvent.now_utc(),
        last_price       = last_price,
        bid_depth        = bid_depth,
        ask_depth        = ask_depth,
        trades_this_tick = trades_this_tick,
    )


def anomaly_event(tick: int, agent_id: str, description: str,
                  **metadata) -> MarketEvent:
    return MarketEvent(
        event_type = EventType.ANOMALY,
        tick       = tick,
        timestamp  = MarketEvent.now_utc(),
        agent_id   = agent_id,
        metadata   = {"description": description, **metadata},
    )
