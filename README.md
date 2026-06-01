# Simple Market Simulator

A decentralized agent-based market simulation that models price equilibrium, autonomous negotiation, and systemic liquidity risk — with full thought-process transparency for every agent.

---

## What This Is

This simulator spins up a virtual market populated by autonomous agents. Each agent has its own inventory, cash balance, risk appetite, and decision logic. They trade with each other through a central order book.

The distinguishing feature: every agent **thinks out loud**. Before acting, each agent logs its internal reasoning — what it sees, what it infers, and why it chose to bid/ask/hold. This makes the market legible, not a black box.

Two simulations are available:

- **Simulation 1 — Agent Zoo**: Five pure archetypes, each with a single fixed personality. Clean and predictable. Good for isolating how each behavior type affects the market.
- **Simulation 2 — Hybrid NPCs**: Each NPC carries 2–3 embedded archetypes. Market conditions vote on which one surfaces each tick. Messy and emergent. Closer to how real traders behave.

---

## Project Roadmap

### Phase 1 — Core Market Engine ✅
- [x] Central order book (bid/ask matching, midpoint price discovery, self-trade prevention)
- [x] Tick-based simulation loop with per-tick market state snapshots
- [x] Agent base class: inventory, cash, `think()` + `act()` interface, `on_trade()` settlement
- [x] Trade settlement logic with cash/inventory conservation
- [x] CLI (`--sim`, `--ticks`, `--agents`, `--seed`, `--quiet` flags)
- [x] 75 unit tests covering models, order book, base agent, engine conservation laws

### Phase 2 — Agent Zoo ✅
- [x] Five distinct archetypes with full thought-process output

| Agent | Behavior | Pathology |
|---|---|---|
| `MarketMakerAgent` | Quotes both sides; widens spread under volatility; tilts inventory | Inventory imbalance during one-sided flows |
| `SpeculatorAgent` | Momentum follower; pays premium to enter, accepts discount to exit | Amplifies bubbles and crashes |
| `HoarderAgent` | Accumulates obsessively below market; releases only at steep premium | Triggers artificial scarcity + liquidity crash |
| `PanicAgent` | Calm until price drops past threshold; dumps entire position instantly | Cascades sell-offs, worsens crashes |
| `RationalAgent` | Anchors to moving-average fair value; buys low, sells high quietly | Slow to react; stabilizes market over time |

- [x] `_pending_orders` pattern — `think()` decides, `act()` executes; thought log always matches action
- [x] `initial_price_history` engine seeding so all agents activate from tick 1
- [x] 42 behavioral tests — each agent verified against purpose-built market states
- [x] `--sim zoo` CLI mode

### Phase 3 — Haggling / Negotiation Protocol ✅
- [x] `HaggleIntent` — direction + ideal price + worst-acceptable price + quantity
- [x] `HaggleSession` — N-round concession negotiation; both parties step toward their limit each round
- [x] `HaggleCoordinator` — pairs compatible buyers/sellers (deal zone must exist), one session per agent per tick; shuffled to prevent always-same pairings
- [x] Per-archetype `haggle_intent()` overrides — Hoarder lowballs, Panic dumps at threshold, Rational anchors to fair value, Speculator chases momentum, MarketMaker negotiates only when inventory-imbalanced
- [x] `HybridNPC.haggle_intent()` — delegates to winning archetype's intent
- [x] Engine pre-tick phase — bilateral trades settle and state rebuilds before the regular order book runs
- [x] Haggling thought-process log printed per session (who bid what, round-by-round)
- [x] `--haggle` CLI flag to enable bilateral negotiation
- [x] 42 tests covering `HaggleSession`, `HaggleCoordinator`, and all per-agent overrides

### Phase 4 — Event Pipeline ✅
- [x] `EventType` enum + `MarketEvent` dataclass — typed schema covering trades, tick summaries, and anomalies
- [x] `EventBus` — in-process publish/subscribe bus; consumers register by event type
- [x] `AuditConsumer` — stores full event history; exports to JSONL audit file
- [x] `AnomalyDetector` consumer — flags: panic cascades, liquidity drain, price crash/spike, sell-off storms
- [x] Engine integration — emits `TRADE`, `HAGGLE_TRADE`, and `TICK_SUMMARY` events automatically
- [x] `--events` CLI flag; anomalies print as inline red warnings during the run
- [x] `--audit <path>` flag to write the full JSONL audit trail to disk
- [x] 39 tests for event schema, bus routing, audit consumer, and anomaly detection logic

### Phase 5 — Stress Testing & Scenarios ✅
- [x] `ScenarioEvent` + `ScenarioRunner` — timed interventions that fire at specified ticks
- [x] Four intervention types: `supply_shock`, `demand_surge`, `agent_collapse`, `price_inject`
- [x] Three named failure-mode scenarios reproducing the critical pathologies:
  1. `hoarding_crash` — hoarder corners supply → artificial scarcity → price spike at tick 10 → hard crash at tick 15
  2. `panic_cascade` — sharp price inject at tick 8 breaches all panic thresholds simultaneously → liquidity drain → second leg down at tick 12
  3. `speculator_bubble` — 7 ticks of rising price injects feed Speculator momentum → hard reversal at tick 9 turns Speculator into a panic seller
- [x] `MetricsCollector` — per-tick snapshots; end-of-run `RunMetrics` with price, activity, and wealth stats
- [x] `gini()`, `price_volatility()`, `max_drawdown()` as standalone pure functions
- [x] `--scenario hoarding_crash | panic_cascade | speculator_bubble` CLI flag
- [x] `--metrics` CLI flag — shows run metrics table + per-agent PnL ranked by profit
- [x] Scenario events logged in yellow inline; anomalies logged in red inline
- [x] 59 tests (29 metrics + 30 scenarios) — all 335 tests passing

### Phase 6 — Interactive GUI ✅
- [x] `GUILogger` — drop-in for `ThoughtLogger`; fires callbacks instead of printing so any UI can subscribe
- [x] `SimulatorApp` — full Textual TUI (runs in-terminal, no browser needed) with four panels:

| Panel | What it shows |
|---|---|
| **Controls** (left) | Sim mode / scenario / speed dropdowns; START / STEP / PAUSE / RESET buttons; live speed, tick counter, price, bid, ask |
| **Agent Thoughts** (centre) | Scrollable, colour-coded reasoning log — every agent's full `think()` output, revealed one agent at a time at the chosen speed, BID/ASK orders highlighted |
| **Market State** (right) | Live price + depth readout, price sparkline (last 40 ticks), agent table with live inventory / cash / net-worth / trade count |
| **Console Log** (bottom) | Trades, haggle deal round-by-round, anomaly alerts in red, scenario injections in yellow |

- [x] Engine refactored to `prepare()` / `step()` / `finalize()` — GUI controls exact tick pace; CLI `run()` is unchanged
- [x] Semaphore-driven worker thread: STEP releases one tick; START runs ticks back-to-back; all engine work stays off the UI thread so `call_from_thread` callbacks always succeed
- [x] **Per-thought pacing** — the delay applies *after each agent's reasoning*, so thoughts appear one agent at a time instead of dumping the whole tick at once
- [x] **Five speed tiers** (Very Slow 1.2 s → Slow 0.6 s → Normal 0.25 s → Fast 0.08 s → Instant), adjustable **live** via the dropdown or the `+` / `-` keys; current speed shown in the control panel
- [x] Keyboard shortcuts: `Space` start/pause, `S` step one tick, `R` reset, `+`/`-` faster/slower, `Q` quit (all priority bindings, so they work regardless of widget focus)
- [x] `--gui` CLI flag launches the TUI; all other flags (`--sim`, `--ticks`, `--haggle`, `--scenario`) carry over

---

## Simulation 2 — Hybrid NPC Market

> **The idea:** Pure archetypes are clean for analysis but unrealistic. Real traders aren't always rational or always panicking — they shift between modes depending on what's happening around them. Hybrid NPCs each carry 2–3 embedded archetypes, and market conditions vote on which one surfaces to make the decision. Think of it as mood-driven trading.

### How It Works

Each Hybrid NPC has a **personality profile** — a fixed set of 2–3 archetypes with base weights that define their character.

```
Iris   ->  Rational (50%) | Speculator (35%) | Panic (15%)
Marcus ->  Hoarder (60%)  | MarketMaker (40%)
Dex    ->  Speculator (45%) | Panic (35%) | Rational (20%)
Vera   ->  MarketMaker (55%) | Hoarder (30%) | Rational (15%)
Rex    ->  Hoarder (50%)  | Panic (30%) | Speculator (20%)
```

Every tick, each embedded archetype computes an **activation score** — how loudly that side of their personality is calling for control. The score combines the base weight with a live signal from market + personal state. The highest score wins and drives `think()` + `act()` for that tick.

```
activation_score(archetype) = base_weight x signal_strength(archetype, market_state, agent_state)
```

### Activation Signals — What Makes Each Side Take Over

| Archetype | Activates strongly when... |
|---|---|
| `Rational` | Price deviates from estimated fair value; market is calm |
| `Speculator` | Strong price momentum detected (trend up or down for N ticks) |
| `MarketMaker` | Bid-ask spread is wide; inventory is balanced |
| `Hoarder` | Scarcity index rising; personal inventory is low relative to target |
| `Panic` | Price dropped sharply; recent trades at a loss; cash critically low |

### Mood Modifiers

These factors amplify or suppress activation scores each tick, simulating stress and confidence:

| Factor | Effect |
|---|---|
| Winning streak (last 3 trades profitable) | Boosts Speculator, suppresses Panic |
| Losing streak (last 3 trades at a loss) | Boosts Panic, suppresses Rational |
| High market volatility | Amplifies whichever archetype already leads |
| Very low cash reserve | Suppresses Hoarder, amplifies Panic |
| Large competitor dump detected | Spikes Panic signal for all NPCs simultaneously (contagion) |

### Thought-Process Output — Hybrid Mode

The internal monologue shows the full activation contest before the winning archetype's voice takes over:

```
[TICK 58] HybridNPC Iris (Rational 50% | Speculator 35% | Panic 15%) thinking...
  > Inventory: 22 units | Cash: $840 | Market: $21.30 (up 9% last 5 ticks)
  > Mood modifier: winning streak (+0.15 to Speculator)

  > Activation contest:
  |  Rational    0.38  (price above fair $19.80 -- slight sell signal, not strong)
  |  Speculator  0.74  (momentum +9% over 5 ticks + winning streak boost)
  |  Panic       0.09  (no loss trigger, cash adequate)

  > DOMINANT MODE: Speculator [beat Rational by +0.36]
  > [Speculator] Trend is strong. Already up on last two buys. Ride it.
  > Decision: BID 10 units @ $21.72 (2% above market to get filled fast)

---

[TICK 71] HybridNPC Dex (Speculator 45% | Panic 35% | Rational 20%) thinking...
  > Inventory: 41 units | Cash: $120 | Market: $17.60 (down 14% last 5 ticks)
  > Mood modifier: losing streak (+0.20 to Panic) | cash critical (+0.15 to Panic)

  > Activation contest:
  |  Speculator  0.31  (downtrend -- short signal, but no shorting available)
  |  Panic       0.88  (price -14% + 2 losing trades + cash near zero -- all stacked)
  |  Rational    0.19  (fair value $19, but Dex cannot afford to wait)

  > DOMINANT MODE: Panic [beat Speculator by +0.57]
  > [Panic] Everything is going wrong at once. I need out.
  > Decision: DUMP 41 units @ $15.00 -- take whatever the market gives.
```

### Emergent Behaviors to Watch For

- **Mood swings** — dominant archetype displaced mid-trend (often coincides with price reversals)
- **Contagion** — one NPC's panic dump spikes Panic scores for neighbors, cascading into a sell-off
- **Suppressed rationality** — Rational persona can't get a word in during volatility; stabilizing effect only appears in calm markets
- **Personality drift** — winning streak makes a Rational-dominant NPC briefly behave like a Speculator

---

## Scenario Outcomes

Each named scenario deliberately reproduces a real market failure pattern. Run with `--quiet --metrics` to see the outcome without the full thought log.

### Panic Cascade (`--scenario panic_cascade`)

A sudden price shock at tick 8 (-28%) breaches PanicAgent's -10% threshold. All panic-capable agents dump simultaneously. Hoarder lowball bids absorb supply at distressed prices. Speculator, caught long, becomes a forced seller for the next 8 ticks. Liquidity drain and price crash anomalies fire automatically.

```
Price: $21.89 -> $12.01  (-44%)   Volatility: $4.46   Drawdown: 45%
Panic-01 PnL: -30%  (bought the spike, sold the crash)
Rational-01: -16%   (bought too early on the way down)
```

### Hoarding Crash (`--scenario hoarding_crash`)
Supply shock at tick 5 concentrates inventory with the hoarder. Price injects spike the market to $30 at tick 10, then crash to $13 at tick 15. Agents who held through the spike give back all gains on the crash.

### Speculator Bubble (`--scenario speculator_bubble`)
Seven ticks of rising price injects feed a Speculator buying frenzy. Rational sees overvaluation and sells. At tick 9, a hard reversal (-42%) flips the Speculator into a panic seller and triggers a cascade.

---

## Architecture

### Simulation 1 — Agent Zoo

```
Tick loop:
  Phase 0: Scenario interventions (price_inject, supply_shock, ...)
  Phase 1: Bilateral haggling (HaggleCoordinator)
  Phase 2: Order book matching (bid/ask)
  Phase 3: Settlement + contagion broadcast
  Phase 4: Event emission (TRADE, TICK_SUMMARY -> EventBus -> consumers)
  Phase 5: Metrics recording

Agents:  MarketMaker  Speculator  Hoarder  Panic  Rational
         think() + act() + haggle_intent() per tick
```

### Simulation 2 — Hybrid NPC Market

```
Same tick loop as Sim 1, but each HybridNPC runs internally:

  PersonalityProfile.run_contest()
    -> raw activation signal per archetype  (0-1)
    -> mood deltas (streak, volatility, cash pressure, contagion)
    -> weighted scores  ->  winner

  winner.think() + winner.act() + winner.haggle_intent()
    -> logged with full activation contest header
    -> MOOD SWING alert if dominant archetype changed vs last tick
```

---

## File Structure

```
Simple-market-simulator/
|
+-- main.py                        # CLI entry point
+-- requirements.txt
|
+-- market/
|   +-- models.py                  # Order, Trade, MarketState dataclasses
|   +-- order_book.py              # Bid/ask matching, price discovery
|   +-- engine.py                  # Tick loop (5 phases), settlement
|   +-- haggle.py                  # HaggleIntent, HaggleSession, HaggleCoordinator
|   +-- events.py                  # EventType, MarketEvent, EventBus
|   +-- consumers.py               # AuditConsumer, AnomalyDetector
|   +-- metrics.py                 # gini(), volatility(), MetricsCollector, RunMetrics
|   +-- scenarios.py               # ScenarioEvent, ScenarioRunner, named scenarios
|
+-- agents/
|   +-- base.py                    # Abstract Agent: think(), act(), haggle_intent()
|   +-- random_agent.py            # Baseline random agent
|   +-- market_maker.py            # Sim 1 archetype
|   +-- speculator.py              # Sim 1 archetype
|   +-- hoarder.py                 # Sim 1 archetype
|   +-- panic.py                   # Sim 1 archetype
|   +-- rational.py                # Sim 1 archetype
|   +-- hybrid/
|       +-- activation.py          # Per-archetype activation signal functions (0-1)
|       +-- mood.py                # Streak, volatility, cash, contagion modifiers
|       +-- personality.py         # PersonalityProfile + ContestResult
|       +-- npc.py                 # HybridNPC: delegates to winning archetype
|       +-- roster.py              # Named NPCs: Iris, Marcus, Dex, Vera, Rex
|
+-- logger/
|   +-- thought_logger.py          # Rich output: thoughts, trades, haggle, anomalies,
|                                  #              scenarios, metrics tables
|
+-- gui/
|   +-- app.py                     # Textual TUI: SimulatorApp (4-panel layout + worker)
|   +-- logger.py                  # GUILogger: callback-based bridge to UI widgets
|
+-- tests/
    +-- test_models.py             # MarketState properties, dataclass fields
    +-- test_order_book.py         # Matching, priority, self-trade, depth
    +-- test_base_agent.py         # Settlement, trade_count, net_worth
    +-- test_random_agent.py       # Determinism, think/act consistency
    +-- test_engine.py             # Conservation laws, tick counter, price history
    +-- test_agents_zoo.py         # 42 behavioral tests for all 5 archetypes
    +-- test_haggle.py             # Session, coordinator, per-agent intents
    +-- test_events.py             # Schema, bus routing, audit, anomaly detection
    +-- test_metrics.py            # gini, volatility, drawdown, MetricsCollector
    +-- test_scenarios.py          # ScenarioRunner, all actions, predefined scenarios
    +-- test_hybrid/
        +-- test_activation.py     # All 5 activation signal functions
        +-- test_mood.py           # All 4 mood modifier types
        +-- test_personality.py    # Contest logic, weight normalisation
        +-- test_npc.py            # HybridNPC interface, panic FSM, contagion
```

---

## Getting Started

```bash
# (Recommended) create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# Install dependencies (rich, pytest, textual)
pip install -r requirements.txt

# Run the random baseline (4 agents, 20 ticks)
python main.py

# Run Simulation 1 -- Agent Zoo
python main.py --sim zoo --ticks 30

# Run Simulation 2 -- Hybrid NPCs
python main.py --sim hybrid --ticks 30

# Enable bilateral haggling (pre-market negotiation)
python main.py --sim zoo --ticks 20 --haggle

# Enable event pipeline + inline anomaly warnings
python main.py --sim zoo --ticks 50 --events

# Write full JSONL audit trail to disk
python main.py --sim hybrid --ticks 100 --events --audit audit.jsonl

# Stress-test with a named scenario
python main.py --sim zoo --ticks 25 --scenario panic_cascade --events --metrics --quiet
python main.py --sim zoo --ticks 25 --scenario hoarding_crash --metrics --quiet
python main.py --sim zoo --ticks 20 --scenario speculator_bubble --metrics --quiet

# Full kitchen-sink run (CLI)
python main.py --sim hybrid --ticks 30 --haggle --events --metrics --scenario panic_cascade

# Launch the interactive GUI (Textual TUI)
python main.py --gui
python main.py --gui --sim zoo --ticks 30
python main.py --gui --sim hybrid --ticks 20 --haggle
python main.py --gui --sim zoo --ticks 25 --scenario panic_cascade
python main.py --gui --sim hybrid --ticks 30 --scenario speculator_bubble --haggle

# Run all 335 tests
python -m pytest tests/ -v
```

> **Tip:** In the GUI, press `Space` to run, then tap `-` a few times to slow it down
> and watch each agent reason in turn. Speed adjusts live — no need to pause or restart.

---

## CLI Reference

| Flag | Values | Description |
|---|---|---|
| `--sim` | `random` `zoo` `hybrid` | Simulation mode (default: `random`) |
| `--ticks` | integer | Number of simulation ticks (default: 20) |
| `--agents` | integer | Number of agents in random mode (default: 4) |
| `--seed` | integer | Random seed for random mode (default: 42) |
| `--quiet` | flag | Hide per-agent thought logs |
| `--haggle` | flag | Enable pre-market bilateral haggling phase |
| `--events` | flag | Enable event pipeline + inline anomaly detection |
| `--audit` | file path | Write JSONL audit trail to disk (requires `--events`) |
| `--metrics` | flag | Show run metrics summary + per-agent PnL at end |
| `--scenario` | `hoarding_crash` `panic_cascade` `speculator_bubble` | Inject a named stress-test scenario |
| `--gui` | flag | Launch the interactive Textual TUI instead of CLI output |

### GUI keyboard shortcuts

| Key | Action |
|---|---|
| `Space` | Start / Pause |
| `S` | Step one tick |
| `R` | Reset simulation |
| `+` | Speed up one tier |
| `-` | Slow down one tier |
| `Q` | Quit |

Speed can also be changed live from the dropdown in the control panel. The five tiers (Very Slow → Slow → Normal → Fast → Instant) set how long each agent's reasoning lingers before the next agent thinks.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Simulation core | Python 3.11+ |
| Event pipeline | In-process `EventBus` (Kafka-shaped schema; swap-in ready) |
| CLI output | `rich` (terminal panels, tables, colour) |
| Interactive GUI | `textual` (Textual TUI — 4-panel live layout, worker thread) |
| Testing | `pytest` — 335 tests across 14 files |
