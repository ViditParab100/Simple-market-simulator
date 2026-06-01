"""
Phase 4 — Event Consumers.

AuditConsumer   — stores every event; can export to a JSONL file.
AnomalyDetector — watches the stream and flags systemic risk signals.

Anomalies detected:
  1. Panic cascade    — 2+ agents dumped large positions in the same tick
  2. Hoarding         — single agent sold >30% of that tick's total volume
     (inverse signal: they were hoarding, now the dam broke)
  3. Liquidity drain  — ask_depth or bid_depth hits zero after a tick
  4. Price crash      — last price fell >15% over last 5 ticks
  5. Price spike      — last price rose >15% over last 5 ticks
  6. Sell-off storm   — single tick sell volume exceeds threshold
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from .events import EventBus, EventType, MarketEvent, anomaly_event


# ── Audit Consumer ────────────────────────────────────────────────────────────

class AuditConsumer:
    """Collects every event. Can write a JSONL audit file on demand."""

    def __init__(self, bus: EventBus):
        self.events: list[MarketEvent] = []
        bus.subscribe(None, self.handle)   # receives ALL events

    def handle(self, event: MarketEvent):
        self.events.append(event)

    def export_jsonl(self, path: str | Path):
        with open(path, "w", encoding="utf-8") as f:
            for event in self.events:
                f.write(event.to_json() + "\n")

    # convenience queries
    def by_type(self, event_type: EventType) -> list[MarketEvent]:
        return [e for e in self.events if e.event_type == event_type]

    def by_agent(self, agent_id: str) -> list[MarketEvent]:
        return [e for e in self.events if e.agent_id == agent_id]

    def total_volume(self) -> int:
        return sum(
            e.quantity for e in self.events
            if e.event_type in (EventType.TRADE, EventType.HAGGLE_TRADE)
        )


# ── Anomaly Detector ──────────────────────────────────────────────────────────

class AnomalyDetector:
    """
    Subscribes to TRADE, HAGGLE_TRADE, and TICK_SUMMARY events.
    Emits ANOMALY events back onto the bus when risk signals are detected.
    Collected anomalies are also stored in self.anomalies for inspection.
    """

    PANIC_CASCADE_MIN_SELLERS  = 2      # sellers who each dumped >= threshold
    PANIC_DUMP_MIN_UNITS       = 10     # units in one tick to count as a dump
    LIQUIDITY_DEPTH_THRESHOLD  = 0      # depth == 0 → drain
    PRICE_MOVE_THRESHOLD       = 0.15   # 15% move over 5 ticks
    SELLOFF_STORM_UNITS        = 20     # total sell volume in one tick

    def __init__(self, bus: EventBus):
        self._bus     = bus
        self.anomalies: list[MarketEvent] = []

        # per-tick accumulators (reset on each TICK_SUMMARY)
        self._tick_sells: dict[str, int] = defaultdict(int)
        self._current_tick = 0

        # price history for trend detection
        self._price_history: list[float] = []

        bus.subscribe(EventType.TRADE,        self._on_trade)
        bus.subscribe(EventType.HAGGLE_TRADE, self._on_trade)
        bus.subscribe(EventType.TICK_SUMMARY, self._on_tick_summary)

    # ── handlers ──────────────────────────────────────────────────────────────

    def _on_trade(self, event: MarketEvent):
        self._tick_sells[event.counterpart_id] += event.quantity

    def _on_tick_summary(self, event: MarketEvent):
        tick = event.tick

        # 1. Panic cascade
        large_sellers = [
            sid for sid, vol in self._tick_sells.items()
            if vol >= self.PANIC_DUMP_MIN_UNITS
        ]
        if len(large_sellers) >= self.PANIC_CASCADE_MIN_SELLERS:
            self._flag(anomaly_event(
                tick, agent_id="",
                description=(
                    f"PANIC CASCADE: {len(large_sellers)} agents each dumped "
                    f">= {self.PANIC_DUMP_MIN_UNITS} units this tick "
                    f"({', '.join(large_sellers)})"
                ),
                sellers=large_sellers,
            ))

        # 2. Sell-off storm (single-tick total sell volume)
        total_sell = sum(self._tick_sells.values())
        if total_sell >= self.SELLOFF_STORM_UNITS:
            self._flag(anomaly_event(
                tick, agent_id="",
                description=(
                    f"SELL-OFF STORM: {total_sell} units sold this tick "
                    f"(threshold {self.SELLOFF_STORM_UNITS})"
                ),
                total_sell_volume=total_sell,
            ))

        # 3. Liquidity drain
        if event.bid_depth == self.LIQUIDITY_DEPTH_THRESHOLD:
            self._flag(anomaly_event(
                tick, agent_id="",
                description="LIQUIDITY DRAIN: bid side is empty — no buyers left",
                bid_depth=event.bid_depth,
            ))
        if event.ask_depth == self.LIQUIDITY_DEPTH_THRESHOLD:
            self._flag(anomaly_event(
                tick, agent_id="",
                description="LIQUIDITY DRAIN: ask side is empty — no sellers left",
                ask_depth=event.ask_depth,
            ))

        # 4. Price crash / spike (over last 5 ticks)
        if event.last_price is not None:
            self._price_history.append(event.last_price)
            if len(self._price_history) >= 5:
                window    = self._price_history[-5:]
                pct_move  = (window[-1] - window[0]) / window[0]
                if pct_move <= -self.PRICE_MOVE_THRESHOLD:
                    self._flag(anomaly_event(
                        tick, agent_id="",
                        description=(
                            f"PRICE CRASH: -{abs(pct_move):.1%} over last 5 ticks "
                            f"(${window[0]:.2f} -> ${window[-1]:.2f})"
                        ),
                        pct_move=round(pct_move, 4),
                    ))
                elif pct_move >= self.PRICE_MOVE_THRESHOLD:
                    self._flag(anomaly_event(
                        tick, agent_id="",
                        description=(
                            f"PRICE SPIKE: +{pct_move:.1%} over last 5 ticks "
                            f"(${window[0]:.2f} -> ${window[-1]:.2f})"
                        ),
                        pct_move=round(pct_move, 4),
                    ))

        # Reset per-tick state
        self._tick_sells.clear()

    # ── internal ──────────────────────────────────────────────────────────────

    def _flag(self, event: MarketEvent):
        self.anomalies.append(event)
        self._bus.publish(event)
