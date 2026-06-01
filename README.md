# Simple Market Simulator

A decentralized agent-based market simulation that models price equilibrium, autonomous negotiation, and systemic liquidity risk — with full thought-process transparency for every agent.

---

## What This Is

This simulator spins up a virtual market populated by autonomous agents. Each agent has its own inventory, cash balance, risk appetite, and decision logic. They trade with each other through a central order book. The system is instrumented with an event-driven pipeline (Kafka) so every trade, price shift, and liquidity event is traceable.

The distinguishing feature: every agent **thinks out loud**. Before acting, each agent logs its internal reasoning — what it sees, what it infers, and why it chose to bid/ask/hold. This makes the market legible, not a black box.

---

## Project Roadmap

### Phase 1 — Core Market Engine
- [ ] Central order book (bid/ask matching, price discovery)
- [ ] Tick-based simulation loop
- [ ] Agent base class: inventory, cash, thresholds, `think()` + `act()` interface
- [ ] Trade settlement logic
- [ ] Basic CLI to run a simulation and print results

### Phase 2 — Agent Zoo
Build five distinct agent archetypes, each with unique decision logic and thought-process output:

| Agent | Behavior | Pathology |
|---|---|---|
| `MarketMakerAgent` | Posts both bids and asks to earn spreads | Inventory imbalance during one-sided flows |
| `SpeculatorAgent` | Momentum follower, chases price trends | Amplifies bubbles and crashes |
| `HoarderAgent` | Accumulates far beyond consumption need | Triggers artificial scarcity + liquidity crash |
| `PanicAgent` | Dumps inventory when price drops past threshold | Cascades sell-offs, worsens crashes |
| `RationalAgent` | Anchors to estimated fair value, mean-reverts | Slow to react, acts as market stabilizer |

### Phase 3 — Haggling / Negotiation Protocol
- [ ] Agents negotiate bilaterally before hitting the order book
- [ ] Bid/ask thresholds adjust dynamically based on:
  - Real-time inventory level (low stock → raise ask, high stock → lower ask)
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
- [ ] Reproduce the three critical failure modes from the pointers:
  1. Agent hoarding → artificial scarcity → price spike → crash
  2. Panic sell cascade → liquidity drain → price collapse
  3. Speculator feedback loop → bubble formation

---

## Agent Thought-Process Simulation

Every agent exposes a `think()` method that runs before `act()`. It logs a structured internal monologue. Example output:

```
[TICK 42] HoarderAgent-03 thinking...
  > Current inventory: 87 units  |  Cash: $1,204  |  Market price: $18.50
  > Scarcity index: 0.73 (HIGH) — fewer sellers than usual
  > My inventory is above threshold (80), but scarcity is rising
  > Inference: if I hold, price will climb further. Opportunity cost of selling now: high.
  > Decision: HOLD. Do not post ask. Wait for price > $22.
  > Bid posted: $17.80 (below market — fishing for a distressed seller)

[TICK 42] PanicAgent-07 thinking...
  > Current inventory: 34 units  |  Cash: $310  |  Market price: $18.50
  > Price has dropped 12% in last 5 ticks. Threshold: -10% triggers panic sell.
  > PANIC THRESHOLD BREACHED.
  > Decision: DUMP all inventory immediately. Accept any bid above $14.
  > Ask posted: $14.00 (34 units) — clearing inventory regardless of loss.
```

The thought log is the primary observability layer. It shows *why* a market event happened, not just *what* happened.

---

## Simulation 2 — Hybrid NPC Market

> **The idea:** Pure archetypes are clean for analysis but unrealistic. Real traders aren't always rational or always panicking — they shift between modes depending on what's happening around them. Hybrid NPCs each carry 2–3 embedded archetypes, and market conditions vote on which one surfaces to make the decision. Think of it as mood-driven trading.

### How It Works

Each Hybrid NPC has a **personality profile**: a fixed set of 2–3 archetypes with base weights that define their character.

```
Iris   →  Rational (50%) | Speculator (35%) | Panic (15%)
Marcus →  Hoarder (60%)  | MarketMaker (40%)
Dex    →  Speculator (45%) | Panic (35%) | Rational (20%)
```

Every tick, each embedded archetype computes an **activation score** — how loudly that side of their personality is calling for control. The score combines the base weight with a live signal from market + personal state. The highest score wins, and that archetype's `think()` + `act()` logic runs for that tick.

```
activation_score(archetype) = base_weight × signal_strength(archetype, market_state, agent_state)
```

### Activation Signals — What Makes Each Side Take Over

| Archetype | Activates strongly when... |
|---|---|
| `Rational` | Price deviates from estimated fair value; market is calm |
| `Speculator` | Strong price momentum detected (trend up or down for N ticks) |
| `MarketMaker` | Bid-ask spread is wide; inventory is balanced |
| `Hoarder` | Scarcity index rising; personal inventory is low |
| `Panic` | Price dropped sharply; recent trades are at a loss; cash is critically low |

### Additional Mood Modifiers

These environmental factors can amplify or suppress activation scores across all archetypes, simulating stress and confidence:

| Factor | Effect |
|---|---|
| Winning streak (last 3 trades profitable) | Boosts Speculator, suppresses Panic |
| Losing streak (last 3 trades at a loss) | Boosts Panic, suppresses Rational |
| High market volatility | Amplifies whichever archetype already leads |
| Very low cash reserve | Suppresses Hoarder, amplifies Panic |
| Inventory far above personal average | Triggers Hoarder → sell-off or MarketMaker ask |
| Competitor just dumped large volume | Spikes Panic signal for all NPCs simultaneously |

### Thought-Process Output — Hybrid Mode

The internal monologue first shows the activation contest, then switches into the winning archetype's reasoning voice:

```
[TICK 58] HybridNPC Iris (Rational 50% | Speculator 35% | Panic 15%) thinking...
  > State: inventory=22 units | cash=$840 | market price=$21.30 (up 9% last 4 ticks)
  > Mood modifier: winning streak active (+0.15 to Speculator signal)

  > Activation contest:
  |  Rational    score: 0.38  (price is above fair value estimate of $19.80 — slight sell signal, but not strong)
  |  Speculator  score: 0.74  (momentum: +9% trend over 4 ticks + winning streak boost)
  |  Panic       score: 0.09  (no loss trigger, cash adequate)

  > DOMINANT MODE: Speculator [won by +0.36 over Rational]

  > [Speculator voice] Trend is strong. I'm already up on my last two buys. Ride it.
  > Fair value warnings noted but overruled — momentum beats fundamentals right now.
  > Decision: BID $21.80 for 10 units (above market — willing to pay to get in)

---

[TICK 71] HybridNPC Dex (Speculator 45% | Panic 35% | Rational 20%) thinking...
  > State: inventory=41 units | cash=$120 | market price=$17.60 (down 14% last 6 ticks)
  > Mood modifier: losing streak active (+0.20 to Panic signal) | cash critically low (+0.15 to Panic)

  > Activation contest:
  |  Speculator  score: 0.31  (downtrend — technically a short signal, but no shorting available)
  |  Panic       score: 0.88  (price -14%, 2 losing trades, cash near zero — all triggers stacked)
  |  Rational    score: 0.19  (fair value suggests $19, but Dex can't afford to wait)

  > DOMINANT MODE: Panic [won by +0.57 over Speculator]

  > [Panic voice] Everything is going wrong at once. Cash is gone. Price is falling.
  > I need out. Rational says wait for $19 but I physically cannot hold this position.
  > Decision: DUMP 41 units — ask $15.00. Take whatever the market gives.
```

### Emergent Behaviors to Watch For

- **Mood swing events** — a tick where a dominant archetype is displaced by a challenger (e.g., Speculator → Panic mid-trend). These often coincide with market turning points.
- **Contagion** — a large dump by one Panic-dominant NPC spikes the Panic signal for all other NPCs simultaneously, potentially triggering a cascade.
- **Suppressed rationality** — NPCs with Rational in their profile but low weight rarely get to act on it, especially during volatile periods. Their stabilizing effect only shows in calm markets.
- **Personality drift** — mood modifiers from winning/losing streaks can temporarily invert an NPC's effective personality (a Rational-dominant NPC behaving like a Speculator after 3 wins in a row).

### Simulation 2 Roadmap

- [ ] `PersonalityProfile` class — stores archetype weights and computes activation scores each tick
- [ ] Per-archetype `activation_signal()` functions reading market + agent state
- [ ] Mood modifier layer — streak tracker, volatility reader, cash pressure sensor
- [ ] `HybridNPC` class wrapping `PersonalityProfile` + delegating `think()`/`act()` to the winning archetype
- [ ] Activation contest log in the thought-process output
- [ ] "Mood swing" event detection — log when the dominant archetype changes between ticks
- [ ] Contagion tracker — measure how one NPC's Panic activation raises the Panic signal for its neighbors
- [ ] Comparative run: same market, same starting conditions — Sim 1 (pure archetypes) vs Sim 2 (hybrid NPCs)

---

## Architecture

### Simulation 1 — Pure Archetype Market

```
┌─────────────────────────────────────────────────────┐
│                   Simulation Engine                  │
│  (tick loop, scenario injection, metrics collection) │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │      Order Book         │
          │  (bid/ask matching,     │
          │   price discovery)      │
          └────────────┬────────────┘
                       │ trade events
          ┌────────────▼────────────┐
          │    Kafka Event Bus       │
          │  (settlement, anomaly   │
          │   detection consumers)  │
          └─────────────────────────┘
                       ▲
         Agents emit state-change events

┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│  Market  │  │Speculator│  │  Hoarder │  │  Panic   │  │ Rational │
│  Maker   │  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │
│ think()  │  │ think()  │  │ think()  │  │ think()  │  │ think()  │
│  act()   │  │  act()   │  │  act()   │  │  act()   │  │  act()   │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

### Simulation 2 — Hybrid NPC Market

```
┌─────────────────────────────────────────────────────┐
│                   Simulation Engine                  │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │      Order Book         │
          └────────────┬────────────┘
                       │ trade events
          ┌────────────▼────────────┐
          │    Kafka Event Bus       │
          └─────────────────────────┘

Each NPC runs this internal loop every tick:

┌─────────────────────────────────────────────────────────────┐
│                        HybridNPC                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │               PersonalityProfile                     │  │
│  │  archetype weights + mood modifiers                   │  │
│  └──────────┬──────────────┬──────────────┬─────────────┘  │
│             │              │              │                  │
│    activation_signal() per embedded archetype               │
│             │              │              │                  │
│  ┌──────────▼──┐  ┌────────▼──┐  ┌───────▼───┐            │
│  │  Archetype A│  │Archetype B│  │Archetype C│            │
│  │  score: 0.74│  │score: 0.38│  │score: 0.09│            │
│  └──────────┬──┘  └───────────┘  └───────────┘            │
│             │   WINNER — takes control this tick            │
│  ┌──────────▼──────────┐                                   │
│  │  think() → act()    │  ← logs activation contest first  │
│  └─────────────────────┘                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Simulation core | Python |
| Event pipeline | Apache Kafka (via `confluent-kafka` or `kafka-python`) |
| Thought-process output | Structured logging (`loguru` or `structlog`) |
| CLI / visualization | `rich` (terminal tables, live price feed display) |
| Testing | `pytest` + scenario fixtures |

---

## Getting Started

> Setup instructions will be added as Phase 1 is implemented.

---

## Key Concepts

**Price Equilibrium Stress Testing** — The simulation deliberately introduces irrational agents (hoarders, panic sellers) alongside rational ones to observe when and how equilibrium breaks down.

**Haggling Protocol** — Agents don't just hit the order book blindly. They first attempt bilateral negotiation, adjusting their thresholds based on real-time scarcity and competing offers. Only unresolved orders flow to the central book.

**Systemic Liquidity Risk** — The Kafka pipeline enables post-hoc analysis of *when* the market became fragile — which agent triggered the cascade, which tick the liquidity depth fell below safe levels, and how long recovery took.
