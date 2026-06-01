"""
Phase 6 — Textual GUI.

Runs the market simulation with a live terminal UI:
  - Control panel  : sim mode, scenario, speed, Start/Step/Pause/Reset
  - Thought log    : scrollable per-agent reasoning (centre panel)
  - Market panel   : live price, depth, price sparkline, agent table
  - Console log    : trades, haggle deals, anomalies, scenario events
"""
from __future__ import annotations

import threading
import time
import random
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Button, DataTable, Footer, Header,
    Label, RichLog, Select, Sparkline, Static,
)
from textual.reactive import reactive
from textual import work, on

from market.engine import SimulationEngine
from market.haggle import HaggleCoordinator
from market.events import EventBus, EventType
from market.consumers import AnomalyDetector
from market.metrics import MetricsCollector
from market.scenarios import NAMED_SCENARIOS
from market.models import Order, OrderSide, Trade

from agents.market_maker import MarketMakerAgent
from agents.speculator import SpeculatorAgent
from agents.hoarder import HoarderAgent
from agents.panic import PanicAgent
from agents.rational import RationalAgent
from agents.hybrid.roster import build_roster
from agents.random_agent import RandomAgent

from gui.logger import GUILogger

# ── Constants ─────────────────────────────────────────────────────────────────

_SEED_HISTORY = [round(19.0 + i * 0.25, 2) for i in range(10)]

_SPEED_OPTIONS = [
    Select.BLANK,
    ("Slow   (1.5 s/tick)",  "slow"),
    ("Normal (0.5 s/tick)",  "normal"),
    ("Fast   (0.1 s/tick)",  "fast"),
    ("Instant",              "instant"),
]
_SPEED_DELAY = {"slow": 1.5, "normal": 0.5, "fast": 0.1, "instant": 0.0}

_SIM_OPTIONS = [
    Select.BLANK,
    ("Agent Zoo (5 archetypes)", "zoo"),
    ("Hybrid NPCs (5 NPCs)",     "hybrid"),
    ("Random agents",            "random"),
]

_SCENARIO_OPTIONS = [
    Select.BLANK,
    ("None",                  "none"),
    ("Panic Cascade",         "panic_cascade"),
    ("Hoarding Crash",        "hoarding_crash"),
    ("Speculator Bubble",     "speculator_bubble"),
]


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
Screen {
    layout: vertical;
}

#main-row {
    layout: horizontal;
    height: 1fr;
}

#controls {
    width: 24;
    padding: 1 2;
    border: solid $primary-darken-2;
    background: $surface;
}

#controls Label {
    margin-bottom: 1;
}

#controls Select {
    margin-bottom: 1;
    width: 100%;
}

#controls Button {
    width: 100%;
    margin-bottom: 1;
}

#thought-panel {
    width: 1fr;
    border: solid $secondary-darken-1;
}

#thought-label {
    background: $secondary-darken-1;
    color: $text;
    padding: 0 1;
    text-style: bold;
}

#thought-log {
    height: 1fr;
    padding: 0 1;
}

#market-panel {
    width: 34;
    border: solid $accent-darken-1;
    padding: 0 1;
}

#market-label {
    background: $accent-darken-1;
    color: $text;
    padding: 0 1;
    text-style: bold;
}

#market-stats {
    height: auto;
    padding: 1 0;
}

#price-chart {
    height: 5;
    margin: 1 0;
}

#agent-table {
    height: 1fr;
}

#console-area {
    height: 12;
    border: solid $warning-darken-2;
}

#console-label {
    background: $warning-darken-2;
    color: $text;
    padding: 0 1;
    text-style: bold;
}

#console-log {
    height: 1fr;
    padding: 0 1;
}

#status-bar {
    height: 1;
    background: $primary-darken-3;
    padding: 0 1;
}

.section-title {
    text-style: bold underline;
    margin-bottom: 1;
    color: $text-muted;
}

.stat-label {
    color: $text-muted;
}

Button.-success { background: $success-darken-1; }
Button.-warning { background: $warning-darken-1; }
Button.-error   { background: $error-darken-1;   }
"""


# ── App ───────────────────────────────────────────────────────────────────────

class SimulatorApp(App):
    """Simple Market Simulator — Textual GUI."""

    CSS = CSS
    TITLE = "Simple Market Simulator"
    BINDINGS = [
        ("space", "toggle_run",  "Start / Pause"),
        ("s",     "step_once",   "Step"),
        ("r",     "reset",       "Reset"),
        ("q",     "quit",        "Quit"),
    ]

    # Reactive state
    tick        = reactive(0)
    total_ticks = reactive(20)
    last_price  = reactive(0.0)
    sim_running = reactive(False)

    def __init__(self, sim_mode: str = "zoo", scenario: str = "none",
                 ticks: int = 20, speed: str = "normal",
                 haggle: bool = False):
        super().__init__()
        self._sim_mode  = sim_mode
        self._scenario  = scenario
        self._ticks     = ticks
        self._speed     = speed
        self._haggle    = haggle

        # Simulation control
        self._engine:  Optional[SimulationEngine] = None
        self._logger   = GUILogger()
        self._run_flag = threading.Event()   # set = running, clear = paused
        self._stop_flag= threading.Event()   # set = stop worker

        # Price history for sparkline
        self._prices: list[float] = list(_SEED_HISTORY)

        # Agent row keys (for DataTable updates)
        self._agent_rows: dict[str, str] = {}

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="main-row"):

            # Left: controls
            with Vertical(id="controls"):
                yield Label("Simulation", classes="section-title")
                yield Select(_SIM_OPTIONS,      id="sel-sim",      prompt="Sim mode")
                yield Select(_SCENARIO_OPTIONS, id="sel-scenario",  prompt="Scenario")
                yield Select(_SPEED_OPTIONS,    id="sel-speed",     prompt="Speed")

                yield Label("", id="lbl-sep")
                yield Button("START",  id="btn-start",  variant="success")
                yield Button("STEP",   id="btn-step",   variant="primary")
                yield Button("PAUSE",  id="btn-pause",  variant="warning")
                yield Button("RESET",  id="btn-reset",  variant="error")

                yield Label("", id="lbl-sep2")
                yield Label("Tick:  0 / 20",  id="lbl-tick")
                yield Label("Price: --",      id="lbl-price")
                yield Label("Bid:   --",      id="lbl-bid")
                yield Label("Ask:   --",      id="lbl-ask")
                yield Label("Trades: 0",      id="lbl-trades")

            # Centre: agent thought log
            with Vertical(id="thought-panel"):
                yield Label(" Agent Thought Process", id="thought-label")
                yield RichLog(id="thought-log", highlight=True, markup=True,
                              wrap=True, auto_scroll=True)

            # Right: market state + agent table
            with Vertical(id="market-panel"):
                yield Label(" Market State", id="market-label")
                yield Static("", id="market-stats")
                yield Sparkline([], id="price-chart", summary_function=max)
                yield Label("Agents", classes="section-title")
                yield DataTable(id="agent-table", show_cursor=False)

        # Bottom: console log
        with Vertical(id="console-area"):
            yield Label(" Console Log  (trades | haggle | anomalies | scenarios)",
                        id="console-label")
            yield RichLog(id="console-log", highlight=True, markup=True,
                          auto_scroll=True)

        yield Footer()

    # ── Mount ─────────────────────────────────────────────────────────────────

    def on_mount(self):
        # Pre-populate selects with defaults
        self.query_one("#sel-sim",      Select).value = self._sim_mode
        self.query_one("#sel-scenario", Select).value = self._scenario if self._scenario else "none"
        self.query_one("#sel-speed",    Select).value = self._speed

        # Build agent table columns
        table = self.query_one("#agent-table", DataTable)
        table.add_columns("Agent", "Inv", "Cash", "Net Worth", "Trades")

        # Wire logger callbacks
        self._wire_logger()

        # Build the initial simulation
        self._build_simulation()

        self.query_one("#console-log", RichLog).write(
            "[dim]Simulation ready. Press START or SPACE to begin.[/dim]"
        )

    # ── Logger wiring ──────────────────────────────────────────────────────────

    def _wire_logger(self):
        lg = self._logger

        lg.on_thought = lambda tick, agent_id, thoughts, orders: \
            self.call_from_thread(self._show_thought, tick, agent_id, thoughts, orders)

        lg.on_trade = lambda trade: \
            self.call_from_thread(self._show_trade, trade)

        lg.on_tick_summary = lambda tick, lp, bb, ba, nt: \
            self.call_from_thread(self._show_tick_summary, tick, lp, bb, ba, nt)

        lg.on_haggle = lambda log_lines: \
            self.call_from_thread(self._show_haggle, log_lines)

        lg.on_scenario = lambda tick, desc: \
            self.call_from_thread(self._show_scenario, tick, desc)

        lg.on_anomaly = lambda desc, tick: \
            self.call_from_thread(self._show_anomaly, desc, tick)

        lg.on_final_state = lambda agents, lp: \
            self.call_from_thread(self._show_final_state, agents, lp)

        lg.on_metrics = lambda m: \
            self.call_from_thread(self._show_metrics, m)

    # ── Simulation build ───────────────────────────────────────────────────────

    def _build_simulation(self):
        """Construct fresh agents + engine from current settings."""
        sim_mode = str(self.query_one("#sel-sim", Select).value)
        scenario_key = str(self.query_one("#sel-scenario", Select).value)

        agents = self._make_agents(sim_mode)
        scenario = NAMED_SCENARIOS.get(scenario_key)

        seed_history = _SEED_HISTORY if sim_mode in ("zoo", "hybrid") else None
        coordinator  = HaggleCoordinator() if self._haggle else None

        bus = EventBus()
        AnomalyDetector(bus)
        bus.subscribe(EventType.ANOMALY,
                      lambda e: self.call_from_thread(
                          self._show_anomaly,
                          e.metadata.get("description", ""), e.tick))

        self._engine = SimulationEngine(
            agents=agents,
            logger=self._logger,
            initial_price_history=list(seed_history or []),
            haggle_coordinator=coordinator,
            event_bus=bus,
            scenario_runner=scenario,
            metrics_collector=MetricsCollector(),
        )

        self._prices = list(seed_history or [20.0])
        self.tick        = 0
        self.total_ticks = self._ticks
        self.last_price  = self._prices[-1] if self._prices else 20.0

        # Rebuild agent table
        self._agent_rows.clear()
        table = self.query_one("#agent-table", DataTable)
        table.clear()
        for i, agent in enumerate(agents):
            row_key = str(i)
            table.add_row(
                agent.agent_id[:14],
                str(agent.inventory),
                f"${agent.cash:.0f}",
                f"${agent.net_worth(self.last_price):.0f}",
                "0",
                key=row_key,
            )
            self._agent_rows[agent.agent_id] = row_key

        self._update_status_labels()
        self._update_market_stats()

    def _make_agents(self, sim_mode: str) -> list:
        if sim_mode == "hybrid":
            return build_roster()
        if sim_mode == "random":
            rng = random.Random(42)
            return [
                RandomAgent(f"Random-{i+1:02d}",
                            inventory=rng.randint(10, 50),
                            cash=round(rng.uniform(200, 600), 2),
                            seed=42 + i)
                for i in range(4)
            ]
        # Default: zoo
        return [
            MarketMakerAgent("MarketMaker", inventory=30, cash=800.0),
            SpeculatorAgent("Speculator",   inventory=10, cash=600.0),
            HoarderAgent("Hoarder",         inventory=20, cash=1000.0, hoard_target=60),
            PanicAgent("Panic",             inventory=40, cash=300.0),
            RationalAgent("Rational",       inventory=25, cash=500.0),
        ]

    # ── Button / Select handlers ───────────────────────────────────────────────

    @on(Button.Pressed, "#btn-start")
    def action_toggle_run(self):
        if not self._engine:
            return
        if self.sim_running:
            return
        self._start_run()

    @on(Button.Pressed, "#btn-step")
    def action_step_once(self):
        if not self._engine:
            return
        if self.sim_running:
            return
        if self._engine.tick == 0:
            self._engine.prepare(self._ticks)
        self._do_step()

    @on(Button.Pressed, "#btn-pause")
    def action_pause(self):
        self._run_flag.clear()
        self.sim_running = False

    @on(Button.Pressed, "#btn-reset")
    def action_reset(self):
        self._stop_flag.set()
        self._run_flag.clear()
        self.sim_running = False
        self._stop_flag.clear()
        # Clear UI
        self.query_one("#thought-log", RichLog).clear()
        self.query_one("#console-log", RichLog).clear()
        self._build_simulation()
        self.query_one("#console-log", RichLog).write(
            "[dim]Reset. Press START to run again.[/dim]"
        )

    @on(Select.Changed, "#sel-sim")
    @on(Select.Changed, "#sel-scenario")
    @on(Select.Changed, "#sel-speed")
    def on_select_changed(self, event: Select.Changed):
        if event.select.id == "sel-speed" and event.value != Select.BLANK:
            self._speed = str(event.value)
        else:
            # Rebuild on mode/scenario change only if not running
            if not self.sim_running:
                self._build_simulation()

    # ── Keyboard bindings ──────────────────────────────────────────────────────

    def action_toggle_run(self):
        if self.sim_running:
            self._run_flag.clear()
            self.sim_running = False
        else:
            self._start_run()

    def action_step_once(self):
        if not self.sim_running and self._engine:
            if self._engine.tick == 0:
                self._engine.prepare(self._ticks)
            self._do_step()

    # ── Run control ────────────────────────────────────────────────────────────

    def _start_run(self):
        if self._engine.tick == 0:
            self._engine.prepare(self._ticks)
        self._run_flag.set()
        self.sim_running = True
        self._stop_flag.clear()
        self._run_worker()

    def _do_step(self):
        """Run exactly one tick synchronously (for the Step button)."""
        if self._engine.tick >= self._ticks:
            return
        has_more = self._engine.step()
        if not has_more:
            self._engine.finalize()

    @work(thread=True)
    def _run_worker(self):
        """Background worker: steps the engine at the chosen speed."""
        while not self._stop_flag.is_set():
            if not self._run_flag.is_set():
                time.sleep(0.05)
                continue

            if self._engine.tick >= self._ticks:
                break

            has_more = self._engine.step()

            delay = _SPEED_DELAY.get(self._speed, 0.5)
            if delay > 0:
                time.sleep(delay)

            if not has_more:
                break

        self.call_from_thread(self._on_run_finished)

    def _on_run_finished(self):
        self.sim_running = False
        self._run_flag.clear()
        if self._engine.tick >= self._ticks:
            self._engine.finalize()
            self.query_one("#console-log", RichLog).write(
                "[bold green]Simulation complete.[/bold green]"
            )

    # ── UI update helpers (always called on main thread) ──────────────────────

    def _show_thought(self, tick: int, agent_id: str,
                      thoughts: list[str], orders: list[Order]):
        log = self.query_one("#thought-log", RichLog)
        log.write(f"\n[bold yellow]>> {agent_id}[/bold yellow]  [dim]tick {tick}[/dim]")
        for t in thoughts:
            log.write(f"  [dim]>[/dim] {t}")
        if orders:
            for o in orders:
                if o.side == OrderSide.BID:
                    log.write(f"  [bold green]BID[/bold green] {o.quantity} @ [green]${o.price:.2f}[/green]")
                else:
                    log.write(f"  [bold red]ASK[/bold red] {o.quantity} @ [red]${o.price:.2f}[/red]")
        else:
            log.write("  [dim]-- HOLD --[/dim]")

    def _show_trade(self, trade: Trade):
        self.query_one("#console-log", RichLog).write(
            f"[dim]\\[{trade.tick:02d}][/dim] [bold green]TRADE[/bold green]  "
            f"[cyan]{trade.buyer_id}[/cyan] bought {trade.quantity} "
            f"from [magenta]{trade.seller_id}[/magenta] "
            f"@ [bold green]${trade.price:.2f}[/bold green]"
        )

    def _show_tick_summary(self, tick: int, last_price: Optional[float],
                           best_bid: Optional[float], best_ask: Optional[float],
                           num_trades: int):
        self.tick = tick
        if last_price is not None:
            self.last_price = last_price
            self._prices.append(last_price)

        self._update_status_labels(best_bid, best_ask, num_trades)
        self._update_market_stats(best_bid, best_ask, num_trades)
        self._update_agent_table()
        self._update_sparkline()

    def _show_haggle(self, log_lines: list[str]):
        clog = self.query_one("#console-log", RichLog)
        clog.write(f"[bold magenta]HAGGLE[/bold magenta]  {log_lines[0] if log_lines else ''}")
        for line in log_lines[1:]:
            if "DEAL" in line:
                clog.write(f"  [green]{line.strip()}[/green]")
            elif "NO DEAL" in line:
                clog.write(f"  [red]{line.strip()}[/red]")
            else:
                clog.write(f"  [dim]{line.strip()}[/dim]")

    def _show_scenario(self, tick: int, description: str):
        self.query_one("#console-log", RichLog).write(
            f"[dim]\\[{tick:02d}][/dim] [bold yellow]SCENARIO[/bold yellow]  {description}"
        )

    def _show_anomaly(self, description: str, tick: int):
        self.query_one("#console-log", RichLog).write(
            f"[dim]\\[{tick:02d}][/dim] [bold red]ANOMALY[/bold red]   {description}"
        )

    def _show_final_state(self, agents, last_price):
        clog = self.query_one("#console-log", RichLog)
        clog.write("\n[bold cyan]--- Final State ---[/bold cyan]")
        price = last_price or 0.0
        for a in agents:
            nw = a.net_worth(price)
            clog.write(
                f"  [bold]{a.agent_id}[/bold]  "
                f"inv={a.inventory}  cash=${a.cash:.2f}  "
                f"net_worth=[cyan]${nw:.2f}[/cyan]  trades={a.trade_count}"
            )

    def _show_metrics(self, metrics):
        clog = self.query_one("#console-log", RichLog)
        clog.write(
            f"\n[bold cyan]--- Metrics ---[/bold cyan]  "
            f"Price {metrics.price_start:.2f}->{metrics.price_end:.2f} "
            f"({metrics.price_change_pct:+.1%})  "
            f"Vol={metrics.volatility:.2f}  "
            f"Drawdown={metrics.max_drawdown_pct:.1%}  "
            f"Gini {metrics.gini_start:.2f}->{metrics.gini_end:.2f}"
        )

    # ── Widget refresh helpers ─────────────────────────────────────────────────

    def _update_status_labels(self, best_bid=None, best_ask=None, num_trades=None):
        self.query_one("#lbl-tick",   Label).update(
            f"Tick:   {self.tick} / {self._ticks}")
        price_str = f"${self.last_price:.2f}" if self.last_price else "--"
        self.query_one("#lbl-price",  Label).update(f"Price:  {price_str}")
        bid_str  = f"${best_bid:.2f}"  if best_bid  else "--"
        ask_str  = f"${best_ask:.2f}"  if best_ask  else "--"
        self.query_one("#lbl-bid",    Label).update(f"Bid:    {bid_str}")
        self.query_one("#lbl-ask",    Label).update(f"Ask:    {ask_str}")
        if num_trades is not None:
            self.query_one("#lbl-trades", Label).update(f"Trades: {num_trades}")

    def _update_market_stats(self, best_bid=None, best_ask=None, num_trades=None):
        if not self._engine:
            return
        ob = self._engine.order_book
        lp = ob.last_price or self.last_price
        bb = best_bid or ob.best_bid()
        ba = best_ask or ob.best_ask()
        bd = ob.bid_depth()
        ad = ob.ask_depth()

        lines = [
            f"[bold]Price[/bold]  [green]${lp:.2f}[/green]",
            f"[bold]Bid[/bold]    [green]${bb:.2f}[/green]" if bb else "[bold]Bid[/bold]    --",
            f"[bold]Ask[/bold]    [red]${ba:.2f}[/red]"   if ba else "[bold]Ask[/bold]    --",
            f"[bold]Depth[/bold]  {bd} bid / {ad} ask",
            f"[bold]Tick[/bold]   {self.tick} / {self._ticks}",
        ]
        self.query_one("#market-stats", Static).update("\n".join(lines))

    def _update_agent_table(self):
        if not self._engine:
            return
        table = self.query_one("#agent-table", DataTable)
        lp = self._engine.order_book.last_price or self.last_price or 20.0
        col_keys = list(table.columns.keys())
        for agent in self._engine.agents:
            row_key = self._agent_rows.get(agent.agent_id)
            if row_key is None:
                continue
            nw = agent.net_worth(lp)
            try:
                table.update_cell(row_key, col_keys[1], str(agent.inventory))
                table.update_cell(row_key, col_keys[2], f"${agent.cash:.0f}")
                table.update_cell(row_key, col_keys[3], f"${nw:.0f}")
                table.update_cell(row_key, col_keys[4], str(agent.trade_count))
            except Exception:
                pass  # row may not exist yet during first tick

    def _update_sparkline(self):
        chart = self.query_one("#price-chart", Sparkline)
        recent = self._prices[-40:] if len(self._prices) > 40 else self._prices
        chart.data = recent


# ── Entry point ───────────────────────────────────────────────────────────────

def launch(sim_mode: str = "zoo", scenario: str = "none",
           ticks: int = 20, speed: str = "normal", haggle: bool = False):
    app = SimulatorApp(
        sim_mode=sim_mode,
        scenario=scenario,
        ticks=ticks,
        speed=speed,
        haggle=haggle,
    )
    app.run()
