"""
Tests for Phase 4 — Event Pipeline.
Covers MarketEvent schema, EventBus routing, AuditConsumer, and AnomalyDetector.
"""
import json
import pytest
import tempfile
from pathlib import Path

from market.events import (
    EventType, MarketEvent, EventBus,
    trade_event, tick_summary_event, anomaly_event,
)
from market.consumers import AuditConsumer, AnomalyDetector
from market.models import Trade


# ── helpers ────────────────────────────────────────────────────────────────────

def make_trade(buyer="buyer", seller="seller", price=20.0, qty=5, tick=1) -> Trade:
    return Trade(buyer_id=buyer, seller_id=seller, price=price, quantity=qty, tick=tick)

def make_trade_event(buyer="buyer", seller="seller", price=20.0, qty=5,
                     tick=1, haggle=False) -> MarketEvent:
    t = make_trade(buyer, seller, price, qty, tick)
    return trade_event(t, buyer_inventory=10, buyer_cash=200.0, tick=tick, haggle=haggle)

def make_tick_event(tick=1, last_price=20.0, bid=50, ask=50, trades=1) -> MarketEvent:
    return tick_summary_event(tick, last_price, bid, ask, trades)

def publish_tick(bus: EventBus, tick: int, last_price: float = 20.0,
                 bid_depth: int = 50, ask_depth: int = 50, trades: int = 1):
    bus.publish(tick_summary_event(tick, last_price, bid_depth, ask_depth, trades))


# ══════════════════════════════════════════════════════════════════════════════
# MarketEvent
# ══════════════════════════════════════════════════════════════════════════════

class TestMarketEvent:

    def test_trade_event_fields(self):
        e = make_trade_event(buyer="alice", seller="bob", price=21.5, qty=3, tick=5)
        assert e.event_type     == EventType.TRADE
        assert e.agent_id       == "alice"
        assert e.counterpart_id == "bob"
        assert e.price          == 21.5
        assert e.quantity       == 3
        assert e.tick           == 5

    def test_haggle_trade_event_type(self):
        e = make_trade_event(haggle=True)
        assert e.event_type == EventType.HAGGLE_TRADE

    def test_tick_summary_event_fields(self):
        e = tick_summary_event(tick=7, last_price=22.0,
                               bid_depth=30, ask_depth=40, trades_this_tick=2)
        assert e.event_type       == EventType.TICK_SUMMARY
        assert e.tick             == 7
        assert e.last_price       == 22.0
        assert e.bid_depth        == 30
        assert e.ask_depth        == 40
        assert e.trades_this_tick == 2

    def test_anomaly_event_fields(self):
        e = anomaly_event(tick=3, agent_id="hoarder", description="PANIC CASCADE")
        assert e.event_type == EventType.ANOMALY
        assert e.agent_id   == "hoarder"
        assert "PANIC CASCADE" in e.metadata.get("description", "")

    def test_to_json_is_valid_json(self):
        e = make_trade_event()
        parsed = json.loads(e.to_json())
        assert parsed["event_type"] == "TRADE"
        assert parsed["price"]      == 20.0

    def test_to_json_contains_all_key_fields(self):
        e = make_trade_event(buyer="alice", price=19.5, qty=7)
        d = json.loads(e.to_json())
        assert "event_type" in d
        assert "tick"        in d
        assert "timestamp"   in d
        assert "agent_id"    in d
        assert "price"       in d
        assert "quantity"    in d

    def test_timestamp_is_populated(self):
        e = make_trade_event()
        assert e.timestamp != ""
        assert "T" in e.timestamp   # ISO-8601 contains T separator

    def test_metadata_extra_kwargs_stored(self):
        e = anomaly_event(1, "", "test", sellers=["a", "b"], volume=42)
        assert e.metadata["sellers"] == ["a", "b"]
        assert e.metadata["volume"]  == 42


# ══════════════════════════════════════════════════════════════════════════════
# EventBus
# ══════════════════════════════════════════════════════════════════════════════

class TestEventBus:

    def test_subscriber_receives_matching_event(self):
        bus = EventBus()
        received = []
        bus.subscribe(EventType.TRADE, received.append)
        bus.publish(make_trade_event())
        assert len(received) == 1

    def test_subscriber_does_not_receive_other_types(self):
        bus = EventBus()
        received = []
        bus.subscribe(EventType.TRADE, received.append)
        bus.publish(make_tick_event())
        assert len(received) == 0

    def test_all_subscriber_receives_every_event(self):
        bus = EventBus()
        received = []
        bus.subscribe(None, received.append)
        bus.publish(make_trade_event())
        bus.publish(make_tick_event())
        bus.publish(anomaly_event(1, "", "test"))
        assert len(received) == 3

    def test_multiple_subscribers_all_called(self):
        bus = EventBus()
        r1, r2 = [], []
        bus.subscribe(EventType.TRADE, r1.append)
        bus.subscribe(EventType.TRADE, r2.append)
        bus.publish(make_trade_event())
        assert len(r1) == 1 and len(r2) == 1

    def test_no_subscribers_no_error(self):
        bus = EventBus()
        bus.publish(make_trade_event())   # should not raise

    def test_haggle_trade_routed_separately_from_trade(self):
        bus = EventBus()
        trade_r, haggle_r = [], []
        bus.subscribe(EventType.TRADE,        trade_r.append)
        bus.subscribe(EventType.HAGGLE_TRADE, haggle_r.append)
        bus.publish(make_trade_event(haggle=False))
        bus.publish(make_trade_event(haggle=True))
        assert len(trade_r)  == 1
        assert len(haggle_r) == 1

    def test_event_type_none_also_receives_anomaly(self):
        bus = EventBus()
        received = []
        bus.subscribe(None, received.append)
        bus.publish(anomaly_event(1, "", "test"))
        assert len(received) == 1


# ══════════════════════════════════════════════════════════════════════════════
# AuditConsumer
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditConsumer:

    def test_collects_all_events(self):
        bus   = EventBus()
        audit = AuditConsumer(bus)
        bus.publish(make_trade_event())
        bus.publish(make_tick_event())
        assert len(audit.events) == 2

    def test_by_type_filters_correctly(self):
        bus   = EventBus()
        audit = AuditConsumer(bus)
        bus.publish(make_trade_event())
        bus.publish(make_tick_event())
        assert len(audit.by_type(EventType.TRADE))        == 1
        assert len(audit.by_type(EventType.TICK_SUMMARY)) == 1

    def test_by_agent_filters_correctly(self):
        bus   = EventBus()
        audit = AuditConsumer(bus)
        bus.publish(make_trade_event(buyer="alice"))
        bus.publish(make_trade_event(buyer="bob"))
        assert len(audit.by_agent("alice")) == 1
        assert len(audit.by_agent("bob"))   == 1

    def test_total_volume_sums_trade_quantities(self):
        bus   = EventBus()
        audit = AuditConsumer(bus)
        bus.publish(make_trade_event(qty=5))
        bus.publish(make_trade_event(qty=3))
        bus.publish(make_tick_event())        # should not count
        assert audit.total_volume() == 8

    def test_total_volume_includes_haggle_trades(self):
        bus   = EventBus()
        audit = AuditConsumer(bus)
        bus.publish(make_trade_event(qty=5, haggle=False))
        bus.publish(make_trade_event(qty=4, haggle=True))
        assert audit.total_volume() == 9

    def test_export_jsonl_writes_file(self):
        bus   = EventBus()
        audit = AuditConsumer(bus)
        bus.publish(make_trade_event())
        bus.publish(make_tick_event())
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        audit.export_jsonl(path)
        lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event_type"] == "TRADE"

    def test_export_jsonl_valid_json_per_line(self):
        bus   = EventBus()
        audit = AuditConsumer(bus)
        for _ in range(5):
            bus.publish(make_trade_event())
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        audit.export_jsonl(path)
        for line in Path(path).read_text(encoding="utf-8").strip().splitlines():
            obj = json.loads(line)
            assert "event_type" in obj


# ══════════════════════════════════════════════════════════════════════════════
# AnomalyDetector
# ══════════════════════════════════════════════════════════════════════════════

class TestAnomalyDetector:

    def _setup(self):
        bus      = EventBus()
        detector = AnomalyDetector(bus)
        return bus, detector

    def _publish_trade(self, bus, seller="s", qty=5, tick=1):
        t = make_trade(buyer="b", seller=seller, qty=qty, tick=tick)
        bus.publish(trade_event(t, 10, 100.0, tick=tick))

    # ── panic cascade ──────────────────────────────────────────────────

    def test_panic_cascade_detected(self):
        bus, det = self._setup()
        # Two sellers each dump >= 10 units
        self._publish_trade(bus, seller="s1", qty=10, tick=1)
        self._publish_trade(bus, seller="s2", qty=12, tick=1)
        publish_tick(bus, tick=1)
        cascades = [a for a in det.anomalies if "CASCADE" in a.metadata.get("description","")]
        assert len(cascades) >= 1

    def test_panic_cascade_not_triggered_by_single_seller(self):
        bus, det = self._setup()
        self._publish_trade(bus, seller="s1", qty=15, tick=1)
        publish_tick(bus, tick=1)
        cascades = [a for a in det.anomalies if "CASCADE" in a.metadata.get("description","")]
        assert len(cascades) == 0

    def test_panic_cascade_not_triggered_by_small_volumes(self):
        bus, det = self._setup()
        self._publish_trade(bus, seller="s1", qty=3, tick=1)
        self._publish_trade(bus, seller="s2", qty=4, tick=1)
        publish_tick(bus, tick=1)
        cascades = [a for a in det.anomalies if "CASCADE" in a.metadata.get("description","")]
        assert len(cascades) == 0

    # ── sell-off storm ─────────────────────────────────────────────────

    def test_selloff_storm_detected(self):
        bus, det = self._setup()
        for i in range(5):
            self._publish_trade(bus, seller=f"s{i}", qty=5, tick=1)  # total = 25
        publish_tick(bus, tick=1)
        storms = [a for a in det.anomalies if "STORM" in a.metadata.get("description","")]
        assert len(storms) >= 1

    def test_selloff_storm_not_triggered_below_threshold(self):
        bus, det = self._setup()
        self._publish_trade(bus, qty=3, tick=1)
        publish_tick(bus, tick=1)
        storms = [a for a in det.anomalies if "STORM" in a.metadata.get("description","")]
        assert len(storms) == 0

    # ── liquidity drain ────────────────────────────────────────────────

    def test_liquidity_drain_bid_side(self):
        bus, det = self._setup()
        publish_tick(bus, tick=1, bid_depth=0, ask_depth=50)
        drains = [a for a in det.anomalies if "DRAIN" in a.metadata.get("description","")]
        assert len(drains) >= 1

    def test_liquidity_drain_ask_side(self):
        bus, det = self._setup()
        publish_tick(bus, tick=1, bid_depth=50, ask_depth=0)
        drains = [a for a in det.anomalies if "DRAIN" in a.metadata.get("description","")]
        assert len(drains) >= 1

    def test_no_liquidity_drain_when_both_sides_present(self):
        bus, det = self._setup()
        publish_tick(bus, tick=1, bid_depth=10, ask_depth=10)
        drains = [a for a in det.anomalies if "DRAIN" in a.metadata.get("description","")]
        assert len(drains) == 0

    # ── price crash / spike ────────────────────────────────────────────

    def test_price_crash_detected(self):
        bus, det = self._setup()
        prices = [20.0, 19.0, 17.0, 16.0, 16.0]   # -20% over 5 ticks
        for i, p in enumerate(prices):
            publish_tick(bus, tick=i+1, last_price=p)
        crashes = [a for a in det.anomalies if "CRASH" in a.metadata.get("description","")]
        assert len(crashes) >= 1

    def test_price_spike_detected(self):
        bus, det = self._setup()
        prices = [20.0, 21.0, 23.0, 24.0, 24.0]   # +20% over 5 ticks
        for i, p in enumerate(prices):
            publish_tick(bus, tick=i+1, last_price=p)
        spikes = [a for a in det.anomalies if "SPIKE" in a.metadata.get("description","")]
        assert len(spikes) >= 1

    def test_no_price_anomaly_on_flat_market(self):
        bus, det = self._setup()
        for i in range(6):
            publish_tick(bus, tick=i+1, last_price=20.0)
        price_anomalies = [
            a for a in det.anomalies
            if "CRASH" in a.metadata.get("description","") or
               "SPIKE" in a.metadata.get("description","")
        ]
        assert len(price_anomalies) == 0

    def test_no_price_anomaly_with_fewer_than_5_ticks(self):
        bus, det = self._setup()
        publish_tick(bus, tick=1, last_price=20.0)
        publish_tick(bus, tick=2, last_price=10.0)   # only 2 data points
        price_anomalies = [
            a for a in det.anomalies
            if "CRASH" in a.metadata.get("description","")
        ]
        assert len(price_anomalies) == 0

    # ── anomaly event structure ────────────────────────────────────────

    def test_anomaly_events_published_to_bus(self):
        bus, det = self._setup()
        received = []
        bus.subscribe(EventType.ANOMALY, received.append)
        publish_tick(bus, tick=1, bid_depth=0)
        assert len(received) >= 1

    def test_anomaly_events_stored_in_detector(self):
        bus, det = self._setup()
        publish_tick(bus, tick=1, bid_depth=0)
        assert len(det.anomalies) >= 1

    def test_anomaly_has_event_type_anomaly(self):
        bus, det = self._setup()
        publish_tick(bus, tick=1, bid_depth=0)
        assert all(a.event_type == EventType.ANOMALY for a in det.anomalies)

    def test_anomaly_description_is_non_empty(self):
        bus, det = self._setup()
        publish_tick(bus, tick=1, bid_depth=0)
        for a in det.anomalies:
            assert a.metadata.get("description", "") != ""

    # ── tick state resets ──────────────────────────────────────────────

    def test_sells_reset_between_ticks(self):
        bus, det = self._setup()
        # Tick 1: only one large seller — no cascade
        self._publish_trade(bus, seller="s1", qty=15, tick=1)
        publish_tick(bus, tick=1)
        cascades_t1 = len([a for a in det.anomalies if "CASCADE" in a.metadata.get("description","")])
        # Tick 2: again only one seller — still no cascade
        self._publish_trade(bus, seller="s2", qty=15, tick=2)
        publish_tick(bus, tick=2)
        cascades_t2 = len([a for a in det.anomalies if "CASCADE" in a.metadata.get("description","")])
        assert cascades_t2 == cascades_t1   # no new cascades added
