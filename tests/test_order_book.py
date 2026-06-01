import pytest
from market.order_book import OrderBook
from market.models import Order, OrderSide


def bid(agent_id: str, price: float, qty: int, tick: int = 1) -> Order:
    return Order(agent_id=agent_id, side=OrderSide.BID, price=price, quantity=qty, tick=tick)

def ask(agent_id: str, price: float, qty: int, tick: int = 1) -> Order:
    return Order(agent_id=agent_id, side=OrderSide.ASK, price=price, quantity=qty, tick=tick)


# ── add_order ──────────────────────────────────────────────────────────────────

def test_bid_added_to_bids():
    ob = OrderBook()
    ob.add_order(bid("A", 20.0, 5))
    assert len(ob.bids) == 1
    assert len(ob.asks) == 0

def test_ask_added_to_asks():
    ob = OrderBook()
    ob.add_order(ask("A", 20.0, 5))
    assert len(ob.asks) == 1
    assert len(ob.bids) == 0


# ── best_bid / best_ask ────────────────────────────────────────────────────────

def test_best_bid_empty():
    assert OrderBook().best_bid() is None

def test_best_ask_empty():
    assert OrderBook().best_ask() is None

def test_best_bid_returns_highest():
    ob = OrderBook()
    ob.add_order(bid("A", 18.0, 1))
    ob.add_order(bid("B", 22.0, 1))
    ob.add_order(bid("C", 20.0, 1))
    assert ob.best_bid() == 22.0

def test_best_ask_returns_lowest():
    ob = OrderBook()
    ob.add_order(ask("A", 22.0, 1))
    ob.add_order(ask("B", 18.0, 1))
    ob.add_order(ask("C", 20.0, 1))
    assert ob.best_ask() == 18.0


# ── depth ──────────────────────────────────────────────────────────────────────

def test_bid_depth_sums_quantities():
    ob = OrderBook()
    ob.add_order(bid("A", 20.0, 5))
    ob.add_order(bid("B", 21.0, 3))
    assert ob.bid_depth() == 8

def test_ask_depth_sums_quantities():
    ob = OrderBook()
    ob.add_order(ask("A", 20.0, 7))
    ob.add_order(ask("B", 21.0, 2))
    assert ob.ask_depth() == 9

def test_depth_empty():
    ob = OrderBook()
    assert ob.bid_depth() == 0
    assert ob.ask_depth() == 0


# ── clear ──────────────────────────────────────────────────────────────────────

def test_clear_removes_all_orders():
    ob = OrderBook()
    ob.add_order(bid("A", 20.0, 5))
    ob.add_order(ask("B", 21.0, 3))
    ob.clear()
    assert ob.bids == []
    assert ob.asks == []

def test_clear_does_not_reset_last_price():
    ob = OrderBook()
    ob.add_order(bid("buyer", 21.0, 5))
    ob.add_order(ask("seller", 19.0, 5))
    ob.match(tick=1)
    ob.clear()
    assert ob.last_price is not None  # last_price persists across ticks


# ── match ──────────────────────────────────────────────────────────────────────

def test_match_basic_trade():
    ob = OrderBook()
    ob.add_order(bid("buyer", 21.0, 5))
    ob.add_order(ask("seller", 19.0, 5))
    trades = ob.match(tick=1)
    assert len(trades) == 1
    assert trades[0].buyer_id == "buyer"
    assert trades[0].seller_id == "seller"
    assert trades[0].quantity == 5

def test_match_price_is_midpoint():
    ob = OrderBook()
    ob.add_order(bid("buyer", 22.0, 5))
    ob.add_order(ask("seller", 18.0, 5))
    trades = ob.match(tick=1)
    assert trades[0].price == 20.0  # (22 + 18) / 2

def test_match_no_overlap_produces_no_trades():
    ob = OrderBook()
    ob.add_order(bid("buyer", 18.0, 5))
    ob.add_order(ask("seller", 22.0, 5))
    trades = ob.match(tick=1)
    assert len(trades) == 0

def test_match_partial_fill():
    ob = OrderBook()
    ob.add_order(bid("buyer", 21.0, 10))
    ob.add_order(ask("seller", 19.0, 3))
    trades = ob.match(tick=1)
    assert len(trades) == 1
    assert trades[0].quantity == 3  # limited by the ask

def test_match_one_bid_many_asks():
    ob = OrderBook()
    ob.add_order(bid("buyer", 25.0, 10))
    ob.add_order(ask("s1", 19.0, 4))
    ob.add_order(ask("s2", 20.0, 4))
    trades = ob.match(tick=1)
    assert len(trades) == 2
    assert sum(t.quantity for t in trades) == 8

def test_match_self_trade_prevented():
    ob = OrderBook()
    ob.add_order(bid("alice", 21.0, 5))
    ob.add_order(ask("alice", 19.0, 5))
    trades = ob.match(tick=1)
    assert len(trades) == 0

def test_match_price_priority_highest_bid_first():
    ob = OrderBook()
    ob.add_order(bid("b_high", 25.0, 1))
    ob.add_order(bid("b_low",  20.0, 1))
    ob.add_order(ask("seller", 19.0, 1))
    trades = ob.match(tick=1)
    assert len(trades) == 1
    assert trades[0].buyer_id == "b_high"

def test_match_price_priority_lowest_ask_first():
    ob = OrderBook()
    ob.add_order(bid("buyer",   25.0, 1))
    ob.add_order(ask("s_low",  18.0, 1))
    ob.add_order(ask("s_high", 22.0, 1))
    trades = ob.match(tick=1)
    assert len(trades) == 1
    assert trades[0].seller_id == "s_low"

def test_match_updates_last_price():
    ob = OrderBook()
    ob.add_order(bid("buyer", 22.0, 5))
    ob.add_order(ask("seller", 18.0, 5))
    ob.match(tick=1)
    assert ob.last_price == 20.0

def test_match_no_trade_leaves_last_price_unchanged():
    ob = OrderBook()
    ob.last_price = 15.0
    ob.add_order(bid("buyer", 10.0, 5))
    ob.add_order(ask("seller", 20.0, 5))
    ob.match(tick=1)
    assert ob.last_price == 15.0

def test_match_tick_recorded_on_trade():
    ob = OrderBook()
    ob.add_order(bid("buyer", 21.0, 1))
    ob.add_order(ask("seller", 19.0, 1))
    trades = ob.match(tick=42)
    assert trades[0].tick == 42
