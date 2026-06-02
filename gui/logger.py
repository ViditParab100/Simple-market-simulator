"""
GUILogger — same interface as ThoughtLogger but fires callbacks
instead of printing.  The Textual app registers its widgets here.
"""
from __future__ import annotations
from typing import Callable, Optional
from market.models import Order, Trade


class GUILogger:
    """
    Drop-in replacement for ThoughtLogger that routes every event to
    registered callbacks so the Textual GUI can display them live.

    All callbacks are optional; unset callbacks are silently skipped.
    """

    def __init__(self):
        self.on_header:       Optional[Callable] = None
        self.on_thought:      Optional[Callable] = None
        self.on_trade:        Optional[Callable] = None
        self.on_tick_summary: Optional[Callable] = None
        self.on_haggle:       Optional[Callable] = None
        self.on_scenario:     Optional[Callable] = None
        self.on_anomaly:      Optional[Callable] = None
        self.on_production:   Optional[Callable] = None
        self.on_consumption:  Optional[Callable] = None
        self.on_payroll:      Optional[Callable] = None
        self.on_death:        Optional[Callable] = None
        self.on_final_state:  Optional[Callable] = None
        self.on_metrics:      Optional[Callable] = None

    # ── ThoughtLogger interface ────────────────────────────────────────

    def log_header(self, num_agents: int, ticks: int):
        if self.on_header:
            self.on_header(num_agents, ticks)

    def log_tick_start(self, tick: int):
        pass  # tick number shown via tick_summary

    def log_thought(self, tick: int, agent_id: str,
                    thoughts: list[str], orders: list[Order]):
        if self.on_thought:
            self.on_thought(tick, agent_id, thoughts, orders)

    def log_trade(self, trade: Trade):
        if self.on_trade:
            self.on_trade(trade)

    def log_tick_summary(self, tick: int, last_price: Optional[float],
                         best_bid: Optional[float], best_ask: Optional[float],
                         num_trades: int):
        if self.on_tick_summary:
            self.on_tick_summary(tick, last_price, best_bid, best_ask, num_trades)

    def log_haggle_session(self, log: list[str]):
        if self.on_haggle:
            self.on_haggle(log)

    def log_scenario_event(self, tick: int, description: str):
        if self.on_scenario:
            self.on_scenario(tick, description)

    def log_anomaly(self, description: str, tick: int):
        if self.on_anomaly:
            self.on_anomaly(description, tick)

    def log_production(self, tick: int, total_produced: float):
        if self.on_production:
            self.on_production(tick, total_produced)

    def log_consumption(self, tick: int, total_consumed: float, starving: list[str]):
        if self.on_consumption:
            self.on_consumption(tick, total_consumed, starving)

    def log_payroll(self, tick: int, wage: float, num_workers: int):
        if self.on_payroll:
            self.on_payroll(tick, wage, num_workers)

    def log_death(self, agent_id: str, tick: int):
        if self.on_death:
            self.on_death(agent_id, tick)

    def log_final_state(self, agents: list[Agent], last_price: Optional[float]):
        if self.on_final_state:
            self.on_final_state(agents, last_price)

    def log_metrics_summary(self, metrics: RunMetrics):
        if self.on_metrics:
            self.on_metrics(metrics)
