from __future__ import annotations
from .order_book import OrderBook
from .models import MarketState, Trade
from .haggle import HaggleCoordinator
from .events import EventBus, trade_event, tick_summary_event
from .metrics import MetricsCollector
from .scenarios import ScenarioRunner
from agents.base import Agent
from logger.thought_logger import ThoughtLogger

_CONTAGION_DUMP_THRESHOLD = 10
_CONTAGION_PULSE_STRENGTH = 0.20


class SimulationEngine:
    def __init__(
        self,
        agents:                list[Agent],
        logger:                ThoughtLogger,
        initial_price_history: list[float]      | None = None,
        haggle_coordinator:    HaggleCoordinator | None = None,
        event_bus:             EventBus          | None = None,
        scenario_runner:       ScenarioRunner    | None = None,
        metrics_collector:     MetricsCollector  | None = None,
        consumption_rate:      float                    = 0.0,
        salary:                float                    = 0.0,
    ):
        self.agents             = agents
        self.order_book         = OrderBook()
        self.logger             = logger
        self.haggle_coordinator = haggle_coordinator
        self.event_bus          = event_bus
        self.scenario_runner    = scenario_runner
        self.metrics_collector  = metrics_collector
        self.consumption_rate   = consumption_rate
        self.salary             = salary
        self.tick               = 0
        self._total_ticks       = 0
        self.price_history: list[float] = list(initial_price_history or [])
        self._agent_map: dict[str, Agent] = {a.agent_id: a for a in agents}

        # Apply a uniform survival consumption rate to every agent (opt-in)
        if consumption_rate > 0:
            for agent in agents:
                agent.consumption_rate = consumption_rate

        if self.price_history:
            self.order_book.last_price = self.price_history[-1]

    # ------------------------------------------------------------------
    # Step-by-step API (used by GUI)
    # ------------------------------------------------------------------

    def prepare(self, ticks: int):
        """Initialise a run. Call once before the first step()."""
        self._total_ticks = ticks
        self.logger.log_header(len(self.agents), ticks)
        if self.metrics_collector:
            self.metrics_collector.record_initial(
                self.agents, self.order_book.last_price or 20.0
            )

    def step(self) -> bool:
        """
        Execute one tick.  Returns True while more ticks remain,
        False after the final tick has been executed.
        """
        if self.tick >= self._total_ticks:
            return False
        self._execute_tick()
        return self.tick < self._total_ticks

    def finalize(self):
        """Emit end-of-run output. Call after the last step()."""
        self.logger.log_final_state(self.agents, self.order_book.last_price)
        if self.metrics_collector:
            metrics = self.metrics_collector.compute(
                self.agents, self.order_book.last_price
            )
            self.logger.log_metrics_summary(metrics)

    # ------------------------------------------------------------------
    # Convenience: run all ticks in one call (CLI path)
    # ------------------------------------------------------------------

    def run(self, ticks: int):
        self.prepare(ticks)
        while self.step():
            pass
        self.finalize()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_tick(self):
        self.tick += 1
        self.order_book.clear()
        self._clear_contagion()
        tick_trades: list[Trade] = []

        self.logger.log_tick_start(self.tick)

        # Phase -1: Production — producers mint new supply into the market
        self._run_production()

        # Phase -0.5: Payroll — employers pay wages so workers stay solvent
        if self.salary > 0:
            self._run_payroll()

        state = self._build_market_state()

        # Phase 0: Scenario interventions
        if self.scenario_runner:
            fired = self.scenario_runner.apply(
                self.tick, self.agents, self.order_book, self.price_history
            )
            for description in fired:
                self.logger.log_scenario_event(self.tick, description)
            if fired:
                state = self._build_market_state()

        # Phase 1: Bilateral haggling (alive agents only)
        if self.haggle_coordinator:
            haggle_results = self.haggle_coordinator.run(
                [a for a in self.agents if a.alive], state, self.tick
            )
            for trade, log in haggle_results:
                self.logger.log_haggle_session(log)
                self._settle([trade], haggle=True)
                self.price_history.append(trade.price)
                self.order_book.last_price = trade.price
                self.logger.log_trade(trade)
                tick_trades.append(trade)
            if haggle_results:
                state = self._build_market_state()

        # Phase 2: Regular order-book market (alive agents only)
        for agent in self.agents:
            if not agent.alive:
                continue
            thoughts = agent.think(state)
            orders   = list(agent.act(state))
            # Survival pressure: starving agents bid above market to restock
            if self.consumption_rate > 0:
                survival = agent.survival_order(state)
                if survival is not None:
                    orders.append(survival)
                    thoughts = list(thoughts) + [
                        f"SURVIVAL: runway {agent.runway():.1f} ticks -- "
                        f"bidding {survival.quantity} @ ${survival.price:.2f} to avoid starvation"
                    ]
            self.logger.log_thought(self.tick, agent.agent_id, thoughts, orders)
            for order in orders:
                self.order_book.add_order(order)

        trades = self.order_book.match(self.tick)
        self._settle(trades, haggle=False)
        self._broadcast_contagion(trades)
        tick_trades.extend(trades)

        if trades:
            self.price_history.append(trades[-1].price)
            for trade in trades:
                self.logger.log_trade(trade)

        # Phase 3: Consumption — every agent burns its survival ration
        if self.consumption_rate > 0:
            self._run_consumption()

        tick_volume = sum(t.quantity for t in tick_trades)

        self.logger.log_tick_summary(
            self.tick,
            self.order_book.last_price,
            self.order_book.best_bid(),
            self.order_book.best_ask(),
            len(tick_trades),
        )

        if self.event_bus:
            self.event_bus.publish(tick_summary_event(
                tick=self.tick,
                last_price=self.order_book.last_price,
                bid_depth=self.order_book.bid_depth(),
                ask_depth=self.order_book.ask_depth(),
                trades_this_tick=len(tick_trades),
            ))

        if self.metrics_collector:
            self.metrics_collector.record_tick(
                tick=self.tick,
                last_price=self.order_book.last_price,
                bid_depth=self.order_book.bid_depth(),
                ask_depth=self.order_book.ask_depth(),
                trade_count=len(tick_trades),
                volume=tick_volume,
            )

    def _build_market_state(self) -> MarketState:
        return MarketState(
            tick=self.tick,
            last_price=self.order_book.last_price,
            best_bid=self.order_book.best_bid(),
            best_ask=self.order_book.best_ask(),
            bid_depth=self.order_book.bid_depth(),
            ask_depth=self.order_book.ask_depth(),
            price_history=self.price_history.copy(),
        )

    def _run_production(self):
        """Living producers mint new supply. Logs total produced if anything was made."""
        total_produced = 0.0
        for agent in self.agents:
            if agent.alive:
                total_produced += agent.produce()
        if total_produced > 0:
            self.logger.log_production(self.tick, total_produced)

    def _run_payroll(self):
        """
        Employers pay each living worker a wage, recirculating cash so workers
        can keep buying food. If employers can't cover the full wage bill, the
        affordable amount is split evenly and drawn from employers in proportion
        to their cash.
        """
        employers = [a for a in self.agents if a.alive and a.is_employer]
        workers   = [a for a in self.agents if a.alive and not a.is_employer]
        if not employers or not workers:
            return

        pool = sum(e.cash for e in employers)
        if pool <= 0:
            return

        wage_bill = self.salary * len(workers)
        payable   = min(wage_bill, pool)
        wage      = payable / len(workers)
        if wage <= 0:
            return

        # Draw the total from employers in proportion to their cash
        total_paid = wage * len(workers)
        for e in employers:
            share = (e.cash / pool) * total_paid
            e.cash       -= share
            e.wages_paid += share
        for w in workers:
            w.cash           += wage
            w.wages_received += wage

        self.logger.log_payroll(self.tick, wage, len(workers))

    def _run_consumption(self):
        """
        Every living agent burns its survival ration. Agents that starve past
        their limit are knocked out. Logs total consumed, who starved, who died.
        """
        total_consumed = 0.0
        starving: list[str] = []
        died: list[str] = []
        for agent in self.agents:
            if not agent.alive:
                continue
            consumed, starved = agent.consume(self.tick)
            total_consumed += consumed
            if starved:
                starving.append(agent.agent_id)
            if not agent.alive:          # transitioned to dead this tick
                died.append(agent.agent_id)
        self.logger.log_consumption(self.tick, total_consumed, starving)
        for agent_id in died:
            self.logger.log_death(agent_id, self.tick)

    def _settle(self, trades: list[Trade], haggle: bool = False):
        for trade in trades:
            if trade.buyer_id in self._agent_map:
                self._agent_map[trade.buyer_id].on_trade(trade)
            if trade.seller_id in self._agent_map:
                self._agent_map[trade.seller_id].on_trade(trade)
            if self.event_bus:
                buyer = self._agent_map.get(trade.buyer_id)
                self.event_bus.publish(trade_event(
                    trade,
                    buyer_inventory=buyer.inventory if buyer else 0,
                    buyer_cash=buyer.cash if buyer else 0.0,
                    tick=self.tick,
                    haggle=haggle,
                ))

    def _broadcast_contagion(self, trades: list[Trade]):
        from agents.hybrid.npc import HybridNPC
        sold_by: dict[str, int] = {}
        for t in trades:
            sold_by[t.seller_id] = sold_by.get(t.seller_id, 0) + t.quantity
        if not any(v >= _CONTAGION_DUMP_THRESHOLD for v in sold_by.values()):
            return
        for agent in self.agents:
            if isinstance(agent, HybridNPC):
                agent.mood.contagion_pulse = _CONTAGION_PULSE_STRENGTH

    def _clear_contagion(self):
        from agents.hybrid.npc import HybridNPC
        for agent in self.agents:
            if isinstance(agent, HybridNPC):
                agent.mood.contagion_pulse = 0.0
