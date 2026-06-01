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

### Phase 3 — Haggling / Negotiation Protocol
- [ ] Agents negotiate bilaterally before hitting the order book
- [ ] Bid/ask thresholds adjust dynamically:
  - Inventory level (low stock → raise ask; high stock → lower ask)
  - Demand surge signals (competing bids push threshold up)
  - Scarcity index (market-wide supply/demand ratio)
- [ ] Negotiation rounds with counter-offer logic
- [ ] Haggling thought-process log per negotiation session

### Phase 4 — Kafka Event Pipeline
- [ ] Kafka producer: emit events for every trade, threshold adjustment, and agent state change
- [ ] Event schema: `{ event_type, agent_id, price, quantity, inventory_post, timestamp }`
- [ ] Kafka consumer: settlement audit trail
- [ ] Anomaly detection consumer: flags hoarding patterns and sell-off cascades
- [ ] Dashboard or log output showing systemic risk signals in real time

### Phase 5 — Stress Testing & Scenarios
- [ ] Scenario runner: inject supply shocks, demand surges, and agent collapses
- [ ] Metrics: price volatility, liquidity depth, Gini coefficient of wealth distribution
- [ ] Reproduce the three critical failure modes:
  1. Agent hoarding → artificial scarcity → price spike → crash
  2. Panic sell cascade → liquidity drain → price collapse
  3. Speculator feedback loop → bubble formation

---

## Simulation 2 — Hybrid NPC Market

> **The idea:** Pure archetypes are clean for analysis but unrealistic. Real traders aren't always rational or always panicking — they shift between modes depending on what's happening around them. Hybrid NPCs each carry 2–3 embedded archetypes, and market conditions vote on which one surfaces to make the decision. Think of it as mood-driven trading.

### How It Works

Each Hybrid NPC has a **personality profile** — a fixed set of 2–3 archetypes with base weights that define their character.

```
Iris   ->  Rational (50%) | Speculator (35%) | Panic (15%)
Marcus ->  Hoarder (60%)  | MarketMaker (40%)
Dex    ->  Speculator (45%) | Panic (35%) | Rational (20%)
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
| Large competitor dump detected | Spikes Panic signal for all NPCs simultaneously |

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

### Simulation 2 Roadmap

- [x] Five pure archetypes as reusable building blocks (built in Phase 2)
- [ ] `ActivationSignal` functions — one per archetype, returns 0–1 score from market + agent state
- [ ] `MoodModifier` layer — streak tracker, volatility sensor, cash pressure, contagion detector
- [ ] `PersonalityProfile` class — holds archetype weights, runs activation contest, returns winner
- [ ] `HybridNPC` class — wraps `PersonalityProfile`, delegates `think()`/`act()` to winning archetype
- [ ] Activation contest log in thought-process output (shows all scores + winner)
- [ ] Mood swing event detection — logs when dominant archetype changes between ticks
- [ ] Contagion signal — large Panic dump by one NPC boosts Panic score for all others next tick
- [ ] Named NPC roster (Iris, Marcus, Dex, ...) with distinct personality profiles
- [ ] `--sim hybrid` CLI mode
- [ ] 40+ behavioral tests for activation logic, mood modifiers, and mood swing detection

### Emergent Behaviors to Watch For

- **Mood swings** — dominant archetype displaced mid-trend (often coincides with price reversals)
- **Contagion** — one NPC's panic dump spikes Panic scores for neighbors, cascading into a sell-off
- **Suppressed rationality** — Rational persona can't get a word in during volatility; stabilizing effect only appears in calm markets
- **Personality drift** — winning streak makes a Rational-dominant NPC briefly behave like a Speculator

---

## Architecture

### Simulation 1 — Pure Archetype Market

```
Simulation Engine  ->  Order Book  ->  Kafka Event Bus
                              |
              +-----------+---+-----------+
              |           |              |
        MarketMaker  Speculator  Hoarder  Panic  Rational
          think()      think()   think()  think() think()
          act()        act()     act()    act()   act()
```

### Simulation 2 — Hybrid NPC Market

```
Simulation Engine  ->  Order Book  ->  Kafka Event Bus
                              |
                  +-----------+-----------+
                  |           |           |
              HybridNPC    HybridNPC   HybridNPC
                  |
        PersonalityProfile
         - archetype weights
         - mood modifiers
         - activation contest each tick
                  |
        winning archetype drives think() + act()
```

---

## File Structure

```
Simple-market-simulator/
|
+-- main.py                        # CLI entry point (--sim random | zoo | hybrid)
+-- requirements.txt
|
+-- market/
|   +-- models.py                  # Order, Trade, MarketState dataclasses
|   +-- order_book.py              # Bid/ask matching, price discovery
|   +-- engine.py                  # Tick loop, settlement, price history
|
+-- agents/
|   +-- base.py                    # Abstract Agent, on_trade(), net_worth()
|   +-- random_agent.py            # Baseline random agent
|   +-- market_maker.py            # Sim 1: MarketMaker archetype
|   +-- speculator.py              # Sim 1: Speculator archetype
|   +-- hoarder.py                 # Sim 1: Hoarder archetype
|   +-- panic.py                   # Sim 1: Panic archetype
|   +-- rational.py                # Sim 1: Rational archetype
|   +-- hybrid/                    # Sim 2: Hybrid NPC system
|       +-- activation.py          # Per-archetype activation signal functions
|       +-- mood.py                # Mood modifier layer
|       +-- personality.py         # PersonalityProfile + activation contest
|       +-- npc.py                 # HybridNPC class
|       +-- roster.py              # Named NPC definitions (Iris, Marcus, Dex, ...)
|
+-- logger/
|   +-- thought_logger.py          # Rich-powered thought + trade output
|
+-- tests/
    +-- test_models.py
    +-- test_order_book.py
    +-- test_base_agent.py
    +-- test_random_agent.py
    +-- test_engine.py
    +-- test_agents_zoo.py         # 42 behavioral tests for Sim 1 archetypes
    +-- test_hybrid/               # Sim 2 tests (activation, mood, NPC behavior)
```

---

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Run the random baseline simulation (4 agents, 20 ticks)
python main.py

# Run Simulation 1 — Agent Zoo (5 archetypes)
python main.py --sim zoo --ticks 30

# Run Simulation 2 — Hybrid NPCs (coming next)
python main.py --sim hybrid --ticks 30

# Run quietly (hide thought logs, show summary only)
python main.py --sim zoo --ticks 50 --quiet

# Run all tests
python -m pytest tests/ -v
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Simulation core | Python 3.11+ |
| Event pipeline | Apache Kafka (Phase 4) |
| Thought-process output | `rich` (terminal panels, tables, color) |
| Testing | `pytest` |

---

## Key Concepts

**Price Equilibrium Stress Testing** — The simulation deliberately introduces irrational agents (hoarders, panic sellers) alongside rational ones to observe when and how equilibrium breaks down.

**Haggling Protocol** — Agents don't just hit the order book blindly. They first attempt bilateral negotiation, adjusting their thresholds based on real-time scarcity and competing offers. Only unresolved orders flow to the central book. *(Phase 3)*

**Systemic Liquidity Risk** — The Kafka pipeline enables post-hoc analysis of *when* the market became fragile — which agent triggered the cascade, which tick the liquidity depth fell below safe levels, and how long recovery took. *(Phase 4)*
