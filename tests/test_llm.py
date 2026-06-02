"""
Tests for the LLM backend: prompt building, response parsing, the Mock client,
the registry, and LLMAgent behaviour (including graceful fallback).
No network or real model is required.
"""
import json
import pytest

from market.models import MarketState, OrderSide
from market.engine import SimulationEngine
from logger.thought_logger import ThoughtLogger

from llm.client import LLMClient, MockLLMClient
from llm.prompt import build_context, build_decision_prompt, parse_decision, fair_value
from llm.registry import make_client, make_clients
from llm.providers import OllamaClient, OpenAIClient, AnthropicClient, LLMError
from agents.llm_agent import LLMAgent, build_llm_roster


# ── helpers ──────────────────────────────────────────────────────────────────

def state(last_price=20.0, price_history=None, bid=None, ask=None,
          bid_depth=50, ask_depth=50):
    return MarketState(
        tick=1, last_price=last_price,
        best_bid=bid if bid is not None else last_price - 0.5,
        best_ask=ask if ask is not None else last_price + 0.5,
        bid_depth=bid_depth, ask_depth=ask_depth,
        price_history=price_history or [20.0] * 5,
    )

class ScriptedClient(LLMClient):
    """Returns a fixed raw string, for testing the parsing/validation path."""
    name = "scripted"
    def __init__(self, reply): self.reply = reply
    def complete(self, system, user): return self.reply

class BrokenClient(LLMClient):
    name = "broken"
    def complete(self, system, user): raise LLMError("no model here")


# ── prompt parsing ───────────────────────────────────────────────────────────

def test_parse_clean_json():
    d = parse_decision('{"action":"BID","price":21.5,"quantity":3,"reasoning":"cheap"}')
    assert d["action"] == "BID" and d["price"] == 21.5 and d["quantity"] == 3

def test_parse_with_code_fence():
    d = parse_decision('```json\n{"action":"ASK","price":22,"quantity":2,"reasoning":"rich"}\n```')
    assert d["action"] == "ASK" and d["quantity"] == 2

def test_parse_with_surrounding_prose():
    raw = 'Sure! Here is my decision:\n{"action":"HOLD","price":null,"quantity":0,"reasoning":"wait"}\nThanks!'
    d = parse_decision(raw)
    assert d["action"] == "HOLD"

def test_parse_garbage_falls_back_to_hold():
    d = parse_decision("I think I will buy some maybe")
    assert d["action"] == "HOLD"

def test_parse_empty_falls_back():
    assert parse_decision("")["action"] == "HOLD"

def test_parse_invalid_action_coerced_to_hold():
    d = parse_decision('{"action":"YOLO","price":5,"quantity":1,"reasoning":"x"}')
    assert d["action"] == "HOLD"

def test_parse_non_numeric_price():
    d = parse_decision('{"action":"BID","price":"cheap","quantity":2,"reasoning":"x"}')
    assert d["price"] is None
    assert d["quantity"] == 2


# ── context / prompt building ────────────────────────────────────────────────

def test_fair_value_from_history():
    assert fair_value(state(price_history=[10, 20, 30])) == pytest.approx(20.0)

def test_build_context_keys():
    a = LLMAgent("A", 5, 600.0, MockLLMClient(), "Ava", "value")
    ctx = build_context(state(), a)
    for key in ("price", "fair_value", "my_inventory", "my_cash", "momentum_pct", "scarcity"):
        assert key in ctx

def test_prompt_embeds_context_json():
    a = LLMAgent("A", 5, 600.0, MockLLMClient(), "Ava", "value")
    ctx = build_context(state(), a)
    _, user = build_decision_prompt("Ava", "value investor", ctx)
    assert "CONTEXT:" in user
    # the embedded blob must be valid json
    blob = user.split("CONTEXT:")[1].strip()
    assert json.loads(blob)["my_inventory"] == 5


# ── MockLLMClient heuristics ─────────────────────────────────────────────────

def _mock_decision(ctx_overrides):
    base = {"tick": 1, "price": 20.0, "fair_value": 20.0, "best_bid": 19.5,
            "best_ask": 20.5, "momentum_pct": 0.0, "scarcity": 0.5,
            "my_inventory": 10, "my_cash": 500.0, "consumption_per_tick": 0,
            "ticks_of_food_left": None}
    base.update(ctx_overrides)
    user = f"...\nCONTEXT: {json.dumps(base)}"
    return parse_decision(MockLLMClient().complete("sys", user))

def test_mock_buys_when_undervalued():
    d = _mock_decision({"price": 16.0, "fair_value": 20.0})
    assert d["action"] == "BID"

def test_mock_sells_when_overvalued():
    d = _mock_decision({"price": 24.0, "fair_value": 20.0, "my_inventory": 10})
    assert d["action"] == "ASK"

def test_mock_survival_buy_when_starving():
    d = _mock_decision({"ticks_of_food_left": 1.0, "my_cash": 500.0})
    assert d["action"] == "BID"

def test_mock_holds_when_no_edge():
    d = _mock_decision({"price": 20.0, "fair_value": 20.0})
    assert d["action"] == "HOLD"

def test_mock_no_context_holds():
    d = parse_decision(MockLLMClient().complete("sys", "no context line here"))
    assert d["action"] == "HOLD"


# ── registry ─────────────────────────────────────────────────────────────────

def test_make_client_mock():
    assert isinstance(make_client("mock"), MockLLMClient)

def test_make_client_empty_is_mock():
    assert isinstance(make_client(""), MockLLMClient)

def test_make_client_ollama():
    c = make_client("ollama:llama3.2")
    assert isinstance(c, OllamaClient) and c.model == "llama3.2"

def test_make_client_ollama_default_model():
    assert make_client("ollama").model == "llama3.2"

def test_make_client_openai():
    assert isinstance(make_client("openai:gpt-4o-mini"), OpenAIClient)

def test_make_client_anthropic():
    assert isinstance(make_client("anthropic:claude-haiku-4-5"), AnthropicClient)

def test_make_client_unknown_raises():
    with pytest.raises(ValueError):
        make_client("frobnicator:x")

def test_make_clients_multiple():
    cs = make_clients("mock,ollama:llama3.2")
    assert len(cs) == 2

def test_make_clients_empty_defaults_to_mock():
    cs = make_clients("")
    assert len(cs) == 1 and isinstance(cs[0], MockLLMClient)


# ── provider error handling (no network needed) ──────────────────────────────

def test_openai_without_key_raises():
    import os
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(LLMError):
            OpenAIClient().complete("s", "u")
    finally:
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved

def test_anthropic_without_key_raises():
    import os
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        with pytest.raises(LLMError):
            AnthropicClient().complete("s", "u")
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


# ── LLMAgent ─────────────────────────────────────────────────────────────────

def test_llm_agent_bid_decision():
    client = ScriptedClient('{"action":"BID","price":21.0,"quantity":3,"reasoning":"cheap"}')
    a = LLMAgent("A", inventory=5, cash=600.0, client=client,
                 persona_name="Ava", persona_style="value")
    thoughts = a.think(state())
    orders = a.act(state())
    assert len(orders) == 1
    assert orders[0].side == OrderSide.BID
    assert orders[0].quantity == 3
    assert any("cheap" in t for t in thoughts)

def test_llm_agent_ask_decision():
    client = ScriptedClient('{"action":"ASK","price":23.0,"quantity":2,"reasoning":"rich"}')
    a = LLMAgent("A", inventory=10, cash=100.0, client=client,
                 persona_name="Eve", persona_style="mm")
    a.think(state()); orders = a.act(state())
    assert orders[0].side == OrderSide.ASK and orders[0].quantity == 2

def test_llm_agent_hold_decision():
    client = ScriptedClient('{"action":"HOLD","price":null,"quantity":0,"reasoning":"wait"}')
    a = LLMAgent("A", 5, 600.0, client, "Ava", "value")
    a.think(state())
    assert a.act(state()) == []

def test_llm_agent_clamps_bid_to_affordable():
    # Wants 100 units but can only afford a few
    client = ScriptedClient('{"action":"BID","price":50.0,"quantity":100,"reasoning":"greedy"}')
    a = LLMAgent("A", inventory=0, cash=100.0, client=client,
                 persona_name="Ava", persona_style="value", max_trade=8)
    a.think(state()); orders = a.act(state())
    if orders:
        assert orders[0].quantity <= 2   # 100 cash / 50 price = 2

def test_llm_agent_ask_clamped_to_inventory():
    client = ScriptedClient('{"action":"ASK","price":20.0,"quantity":100,"reasoning":"dump"}')
    a = LLMAgent("A", inventory=3, cash=100.0, client=client,
                 persona_name="Dane", persona_style="panic")
    a.think(state()); orders = a.act(state())
    assert all(o.quantity <= 3 for o in orders)

def test_llm_agent_falls_back_when_model_broken():
    a = LLMAgent("A", inventory=5, cash=600.0, client=BrokenClient(),
                 persona_name="Ava", persona_style="value")
    thoughts = a.think(state(price_history=[20.0] * 5))
    # Should not raise; should mention fallback
    assert any("unavailable" in t.lower() or "fallback" in t.lower() for t in thoughts)
    assert isinstance(a.act(state()), list)


# ── roster + engine integration ──────────────────────────────────────────────

def test_build_llm_roster_has_producer_and_personas():
    roster = build_llm_roster("mock")
    ids = [a.agent_id for a in roster]
    assert "Producer" in ids
    assert "Ava" in ids and "Eve" in ids
    assert len(roster) == 6

def test_build_llm_roster_multi_model_tags_ids():
    roster = build_llm_roster("mock,ollama:llama3.2")
    consumer_ids = [a.agent_id for a in roster if a.agent_id != "Producer"]
    # multi-model => ids carry a [tag]
    assert all("[" in i for i in consumer_ids)

def test_llm_market_runs_end_to_end():
    roster = build_llm_roster("mock")
    eng = SimulationEngine(
        agents=roster, logger=ThoughtLogger(verbose=False),
        initial_price_history=[round(19.0 + i * 0.25, 2) for i in range(10)],
        consumption_rate=3.0, salary=70.0,
    )
    eng.run(10)
    assert eng.tick == 10
    # The mock-driven market should have produced some trades
    assert sum(a.trade_count for a in roster) > 0
