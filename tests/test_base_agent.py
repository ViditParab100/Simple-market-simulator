import pytest
from agents.base import Agent
from market.models import Order, Trade, MarketState, OrderSide


class StubAgent(Agent):
    """Minimal concrete Agent for testing the base class."""
    def think(self, state: MarketState) -> list[str]:
        return []
    def act(self, state: MarketState) -> list[Order]:
        return []


def trade(buyer: str, seller: str, price: float = 20.0, qty: int = 5, tick: int = 1) -> Trade:
    return Trade(buyer_id=buyer, seller_id=seller, price=price, quantity=qty, tick=tick)


# ── on_trade — buyer side ──────────────────────────────────────────────────────

def test_buy_increases_inventory():
    agent = StubAgent("buyer", inventory=10, cash=500.0)
    agent.on_trade(trade("buyer", "seller", price=20.0, qty=5))
    assert agent.inventory == 15

def test_buy_decreases_cash():
    agent = StubAgent("buyer", inventory=10, cash=500.0)
    agent.on_trade(trade("buyer", "seller", price=20.0, qty=5))
    assert abs(agent.cash - 400.0) < 1e-9

def test_buy_partial_quantity():
    agent = StubAgent("buyer", inventory=0, cash=1000.0)
    agent.on_trade(trade("buyer", "seller", price=50.0, qty=3))
    assert agent.inventory == 3
    assert abs(agent.cash - 850.0) < 1e-9


# ── on_trade — seller side ─────────────────────────────────────────────────────

def test_sell_decreases_inventory():
    agent = StubAgent("seller", inventory=10, cash=100.0)
    agent.on_trade(trade("buyer", "seller", price=20.0, qty=5))
    assert agent.inventory == 5

def test_sell_increases_cash():
    agent = StubAgent("seller", inventory=10, cash=100.0)
    agent.on_trade(trade("buyer", "seller", price=20.0, qty=5))
    assert abs(agent.cash - 200.0) < 1e-9


# ── on_trade — unrelated trade ─────────────────────────────────────────────────

def test_unrelated_trade_no_effect():
    agent = StubAgent("charlie", inventory=10, cash=300.0)
    agent.on_trade(trade("alice", "bob"))
    assert agent.inventory == 10
    assert agent.cash == 300.0


# ── trade_count ────────────────────────────────────────────────────────────────

def test_trade_count_increments_on_buy():
    agent = StubAgent("buyer", inventory=0, cash=1000.0)
    agent.on_trade(trade("buyer", "seller"))
    agent.on_trade(trade("buyer", "seller"))
    assert agent.trade_count == 2

def test_trade_count_increments_on_sell():
    agent = StubAgent("seller", inventory=100, cash=0.0)
    agent.on_trade(trade("buyer", "seller"))
    assert agent.trade_count == 1

def test_trade_count_unrelated_no_increment():
    agent = StubAgent("charlie", inventory=10, cash=300.0)
    agent.on_trade(trade("alice", "bob"))
    assert agent.trade_count == 0


# ── net_worth ──────────────────────────────────────────────────────────────────

def test_net_worth_cash_only():
    agent = StubAgent("a", inventory=0, cash=500.0)
    assert agent.net_worth(market_price=20.0) == 500.0

def test_net_worth_inventory_only():
    agent = StubAgent("a", inventory=10, cash=0.0)
    assert agent.net_worth(market_price=25.0) == 250.0

def test_net_worth_combined():
    agent = StubAgent("a", inventory=10, cash=200.0)
    assert agent.net_worth(market_price=20.0) == 400.0

def test_net_worth_zero():
    agent = StubAgent("a", inventory=0, cash=0.0)
    assert agent.net_worth(market_price=20.0) == 0.0
