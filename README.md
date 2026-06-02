<div align="center">

# 📊 Simple Market Simulator

### *A decentralized, agent-based market where every trader thinks out loud.*

Model price equilibrium, autonomous haggling, systemic liquidity risk, and a full
**survival economy** — consumption, starvation, production, wages — with complete
thought-process transparency for every agent.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-424%20passing-2ea44f?logo=pytest&logoColor=white)
![CLI](https://img.shields.io/badge/CLI-rich-ff69b4)
![GUI](https://img.shields.io/badge/TUI-textual-5A3FD6)
![LLM](https://img.shields.io/badge/LLM-Ollama%20%7C%20OpenAI%20%7C%20Anthropic-000000?logo=ollama&logoColor=white)
![Status](https://img.shields.io/badge/phases-10%2F10%20complete-success)

</div>

---

## 🧭 Table of Contents

| | | |
|---|---|---|
| [✨ Highlights](#-highlights) | [🚀 Quick Start](#-quick-start) | [🎮 The GUI](#-the-gui) |
| [🧠 The Agent Zoo](#-the-agent-zoo) | [🎭 Hybrid NPCs](#-hybrid-npcs-simulation-2) | [🤖 LLM-Backed Agents](#-llm-backed-agents) |
| [🔄 The Survival Economy](#-the-survival-economy) | [💥 Failure Scenarios](#-failure-scenarios) | [🏗️ Architecture](#️-architecture) |
| [🗺️ Roadmap](#️-roadmap) | [📁 Project Structure](#-project-structure) | [🎛️ CLI Reference](#️-cli-reference) |

---

## ✨ Highlights

> **Every agent thinks out loud.** Before acting, each one logs *what it sees, what it
> infers, and why* it chose to bid, ask, or hold. The market is legible — not a black box.

- 🧠 **Two simulations** — pure-archetype "Agent Zoo" and mood-driven "Hybrid NPCs"
- 🤖 **Real LLM brains** — back agents with **Ollama** (free/local), **OpenAI**, or **Anthropic**; run multiple models head-to-head
- 🤝 **Bilateral haggling** — agents negotiate round-by-round before hitting the order book
- 📡 **Event pipeline** — Kafka-shaped `EventBus` with audit trail + live anomaly detection
- 💥 **Stress scenarios** — reproduce panic cascades, hoarding crashes, speculator bubbles
- 🔄 **A living economy** — agents *consume to survive*, *starve and die*, a *Producer* supplies the market, and *wages* recirculate cash
- 🎮 **Interactive TUI** — watch agents reason, trade, and talk in real time
- 🧪 **424 tests** across 18 files

---

## 🚀 Quick Start

```bash
# 1️⃣  Set up
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt

# 2️⃣  Launch the interactive GUI  (the fun way)
python main.py --gui

# 3️⃣  …or run headless in the terminal
python main.py --sim zoo --ticks 30 --metrics
```

<table>
<tr><th>Try this…</th><th>…to see this</th></tr>
<tr><td><code>--sim zoo</code></td><td>5 pure archetypes trade through an order book</td></tr>
<tr><td><code>--sim hybrid --haggle</code></td><td>Mood-driven NPCs that negotiate</td></tr>
<tr><td><code>--consume 3 --salary 70</code></td><td>A <b>sustainable</b> survival economy (nobody dies)</td></tr>
<tr><td><code>--consume 6 --salary 0</code></td><td>A <b>collapse</b> — agents starve one by one ☠️</td></tr>
<tr><td><code>--scenario panic_cascade --events</code></td><td>A market crash with live anomaly alerts</td></tr>
<tr><td><code>--llm ollama:llama3.2</code></td><td>Agents that <b>actually reason</b> via a real LLM 🤖</td></tr>
</table>

---

## 🎮 The GUI

A full in-terminal dashboard (built on [Textual](https://textual.textualize.io/)) — no browser needed.

```
┌─ Controls ──┬──── Agent Thoughts ─────┬── Market State ──┐
│ ▸ Sim mode  │  >> Speculator  tick 8  │  Price  $21.20   │
│ ▸ Scenario  │   > UPTREND +4.9%       │  Bid    $21.68   │
│ ▸ Speed     │   BID 12 @ $21.68       │  Ask    $21.00   │
│ ▸ Consume   │  >> Hoarder             │  ▁▂▃▅▆▇ sparkline │
│ ▸ Salary    │   > Still 40 short      │  ┌─────────────┐ │
│ [START][STEP]│   BID 5 @ $21.40       │  │ Agent  NW   │ │
│ [PAUSE][RESET]│ >> Producer            │  │ 🏭 P  $6.5k │ │
│ Speed: Normal│   + PRODUCED 25 units  │  │ 🚀 Sp $812  │ │
│ Tick: 8/30  │   $ PAYROLL $70 ea.     │  └─────────────┘ │
├─────────────┴─────────────────────────┴──────────────────┤
│ Console Log              │ Trade Talk                      │
│ [08] TRADE Sp ← P @ $21  │ Producer: "Shipped at cost+."   │
│ [08] PAYROLL $70 × 5     │ Speculator: "To the moon! 🚀"   │
│ [08] ☠ DEATH Panic       │ Hoarder: "Mine now. Never enuf."│
└──────────────────────────┴─────────────────────────────────┘
```

| ⌨️ Key | Action | | ⌨️ Key | Action |
|:---:|---|---|:---:|---|
| `Space` | ▶️ Start / Pause | | `+` / `-` | ⏩ Faster / ⏪ Slower |
| `S` | 👣 Step one tick | | `R` | 🔄 Reset |
| `Q` | 🚪 Quit | | | |

> 💡 **Tip:** Press `Space` to run, then tap `-` a few times to slow it right down and
> watch each agent reason *one at a time*. Speed adjusts live — no restart needed.

---

## 🧠 The Agent Zoo

Five pure archetypes, each a fixed personality with its own decision logic and failure mode.

| | Agent | Behavior | ⚠️ Pathology |
|:---:|---|---|---|
| 📈 | **MarketMaker** | Quotes both sides; widens spread under volatility | Inventory imbalance in one-sided flows |
| 🚀 | **Speculator** | Momentum chaser; pays up to enter, dumps to exit | Amplifies bubbles & crashes |
| 🐉 | **Hoarder** | Accumulates below market; releases at steep premium | Artificial scarcity → liquidity crash |
| 😱 | **Panic** | Calm until price cracks, then dumps *everything* | Sell-off cascades |
| 🧮 | **Rational** | Anchors to fair value; buys low, sells high quietly | Slow, but stabilizes the market |
| 🏭 | **Producer** | Mints supply each tick, sells at a cost-plus anchor | The economy's supply source & employer |

---

## 🎭 Hybrid NPCs (Simulation 2)

> **The idea:** real traders aren't *always* rational or *always* panicking — they shift
> between modes depending on what's happening. Each Hybrid NPC carries **2–3 embedded
> archetypes**, and market conditions vote each tick on which personality takes the wheel.
> Think of it as **mood-driven trading**.

**The cast** — each NPC is a weighted blend:

```
Iris    🧮 Rational 50%  | 🚀 Speculator 35% | 😱 Panic 15%
Marcus  🐉 Hoarder 60%   | 📈 MarketMaker 40%
Dex     🚀 Speculator 45%| 😱 Panic 35%      | 🧮 Rational 20%
Vera    📈 MarketMaker 55%| 🐉 Hoarder 30%   | 🧮 Rational 15%
Rex     🐉 Hoarder 50%   | 😱 Panic 30%      | 🚀 Speculator 20%
```

Each tick every embedded archetype computes an **activation score**, and the loudest wins:

```
activation_score = base_weight × signal_strength(market_state, agent_state)
```

<details>
<summary><b>🔬 What makes each side take over (activation signals)</b></summary>

| Archetype | Activates strongly when… |
|---|---|
| 🧮 Rational | Price deviates from fair value; market is calm |
| 🚀 Speculator | Strong momentum (trend up/down for N ticks) |
| 📈 MarketMaker | Bid-ask spread is wide; inventory balanced |
| 🐉 Hoarder | Scarcity rising; personal inventory low |
| 😱 Panic | Sharp price drop; recent losses; cash critically low |

</details>

<details>
<summary><b>😤 Mood modifiers (stress & confidence)</b></summary>

| Factor | Effect |
|---|---|
| 🔥 Winning streak | Boosts Speculator, suppresses Panic |
| 💸 Losing streak | Boosts Panic, suppresses Rational |
| 🌪️ High volatility | Amplifies whichever archetype leads |
| 🪙 Low cash | Suppresses Hoarder, amplifies Panic |
| 📉 Competitor dump | Spikes Panic for **all** NPCs (contagion) |

</details>

<details>
<summary><b>🗣️ Sample thought-process output</b></summary>

```
[TICK 58] HybridNPC Iris (Rational 50% | Speculator 35% | Panic 15%)
  > Inventory: 22 | Cash: $840 | Market: $21.30 (up 9% last 5 ticks)
  > Mood modifier: winning streak (+0.15 to Speculator)

  > Activation contest:
  |  Rational    0.38   (above fair $19.80 — weak sell signal)
  |  Speculator  0.74   (momentum +9% + winning-streak boost)
  |  Panic       0.09   (no loss trigger, cash fine)

  > DOMINANT MODE: Speculator  [beat Rational by +0.36]
  > [Speculator] Trend is strong. Already up on last two buys. Ride it.
  > Decision: BID 10 @ $21.72  (2% above market to get filled)
```

</details>

**👀 Emergent behaviours to watch for:**

- 🎭 **Mood swings** — a dominant archetype displaced mid-trend (often marks a reversal)
- 🦠 **Contagion** — one NPC's panic dump spikes Panic scores for its neighbours
- 🤐 **Suppressed rationality** — the Rational voice can't get heard during volatility
- 🌗 **Personality drift** — a winning streak makes a Rational NPC act like a Speculator

---

## 🤖 LLM-Backed Agents

> Swap the hand-written decision rules for a **real language model**. Each tick, the agent
> gets a compact market snapshot + its persona and the model returns a JSON decision —
> `{action, price, quantity, reasoning}` — and *that reasoning becomes the thought log.*

```
>> Ava   [ollama:llama3.2]   persona: disciplined value investor
   Model says: BID — "price is 8% under fair value and I'm low on food; accumulate"
   Decision: BID 4 @ $21.30
```

### Backends (pick what you have)

| Spec | Backend | Needs |
|---|---|---|
| `mock` | Deterministic offline heuristic | nothing — **default, always works** |
| `ollama:llama3.2` | 🦙 [Ollama](https://ollama.com) (local, free) | `ollama pull llama3.2` |
| `openai:gpt-4o-mini` | OpenAI | `OPENAI_API_KEY` |
| `anthropic:claude-haiku-4-5` | Anthropic | `ANTHROPIC_API_KEY` |

```bash
# Free + local (recommended): install Ollama, pull a model, then…
python main.py --llm ollama:llama3.2 --ticks 20 --metrics

# No setup at all — deterministic mock 'model'
python main.py --llm mock --ticks 20

# Run two models head-to-head (assigned to personas round-robin)
python main.py --llm "ollama:llama3.2,openai:gpt-4o-mini" --ticks 20 --metrics

# In the GUI
python main.py --gui --llm ollama:llama3.2
```

**Five personas** are spun up (value investor, momentum trader, hoarder, nervous trader,
market maker) alongside the rule-based Producer. With multiple models, agent names carry a
`[model]` tag (`Ava[llama3.2]`, `Bryce[gpt-4o-mini]`) so you can compare how different
models trade the *same* market.

- 🧱 **No new dependencies** — providers use the Python stdlib (`urllib`); SDKs not required
- 🛟 **Graceful fallback** — if the model is unreachable or returns garbage, the agent falls back to rule-based logic, so a run never crashes
- ✅ **Validated** — model output is clamped to the agent's cash & inventory before any order is placed
- 🧪 Fully tested offline via the deterministic `mock` client

> ⏱️ **Note:** real models add latency (each agent makes one call per tick). The GUI runs the
> sim on a worker thread so the UI stays responsive; just expect slower ticks than `mock`.

---

## 🔄 The Survival Economy

Agents don't just trade — they must **eat to live**. The full circular flow:

```
            💵 pays wages
      ┌─────────────────────────────────────────┐
      │                                          │
 ┌────▼─────┐    sells food     ┌────────────┐   │
 │ 🏭 PRODUCER│ ───────────────▶ │ ORDER BOOK │   │
 │  mints &  │   (cost-plus     │  bid / ask │   │
 │  anchors  │    anchor)       └─────┬──────┘   │
 └────▲─────┘                         │ workers buy
      │ earns cash                    ▼          │
      │                       ┌───────────────┐  │
      └───────────────────────│ 🧠 CONSUMERS  │──┘
                              │ eat each tick │
                              │ or starve ☠️  │
                              └───────────────┘
```

| Mechanic | What happens |
|---|---|
| 🍽️ **Consumption** | Every agent burns a ration each tick (`--consume`). Inventory depletes. |
| ⏳ **Survival pressure** | Low on stock? Agents bid **above** market to restock before starving. |
| ☠️ **Death** | Miss the ration `N` ticks running → knocked out, stops trading. |
| 🏭 **Production** | The Producer mints fresh supply every tick and sells the surplus. |
| ⚓ **Price anchor** | Producer prices at `cost × (1 + margin)` — *ignores* the frenzy, killing runaway inflation. |
| 💵 **Salaries** | The Producer pays workers a wage each tick, recirculating cash so they stay solvent. |

### 📈 The balance dial

> The economy lives or dies on one rule: **wage ≈ ration × price**.

| Config | Price | Outcome |
|---|---|---|
| `--consume 3 --salary 70` | stable **~$21** | ✅ **Sustainable** — 0 deaths, runs forever |
| `--consume 4 --salary 15` | **~$24** (+8%) | ⚠️ Partial die-off — wages can't cover food |
| `--consume 6 --salary 0` | spikes then freezes | ☠️ **Collapse** — 5 of 6 starve; Producer hoards all cash (Gini → 0.8) |

> 🧪 **Anchor in action:** the same heavy run that once spiralled to **$50 (+121%)**
> now holds at **~$24 (+8%)** thanks to cost-plus pricing.

### 🗣️ Trade Talk

Every agent *speaks* in its own voice as it deals — shown in a dedicated GUI panel and inline in the CLI:

> 🚀 **Speculator:** *"Riding the momentum — to the moon!"*
> 😱 **Panic:** *"Get me out! Take it, take it!"*
> 🐉 **Hoarder:** *"Mine now — never enough."*
> 🧮 **Rational:** *"Below fair value — patience pays."*
> 🏭 **Producer:** *"Shipped at my cost-plus price. Supply keeps flowing."*

---

## 💥 Failure Scenarios

Timed interventions that deliberately reproduce real market pathologies — run with `--scenario`.

<table>
<tr><th>Scenario</th><th>The story</th><th>Result</th></tr>
<tr>
<td>💣 <b>panic_cascade</b></td>
<td>A −28% shock at tick 8 breaches every Panic threshold at once → simultaneous dumps → liquidity drain.</td>
<td>Price <b>$21.89 → $12.01 (−44%)</b>, 45% drawdown</td>
</tr>
<tr>
<td>🐉 <b>hoarding_crash</b></td>
<td>Supply shock concentrates stock with the Hoarder → price spiked to $30 → hard crash to $13.</td>
<td>Gains given back on the crash</td>
</tr>
<tr>
<td>🫧 <b>speculator_bubble</b></td>
<td>7 ticks of rising prices feed a Speculator frenzy → a −42% reversal flips it into a panic seller.</td>
<td>Self-reinforcing bubble → bust</td>
</tr>
</table>

```bash
python main.py --sim zoo --ticks 25 --scenario panic_cascade --events --metrics --quiet
```

---

## 🏗️ Architecture

**The tick loop** — every tick flows through these phases:

```
🏭 Produce ─▶ 💵 Payroll ─▶ 💣 Scenario ─▶ 🤝 Haggle ─▶ 📖 Order book
   ─▶ ✅ Settle (+ 🦠 contagion) ─▶ 🍽️ Consume (+ ☠️ death) ─▶ 📡 Events ─▶ 📊 Metrics
```

**Hybrid NPCs** add an internal contest before they act:

```
PersonalityProfile.run_contest()
   ├─ raw activation signal per archetype        (0–1)
   ├─ mood deltas (streak, volatility, cash, contagion)
   └─ weighted scores ──▶ 🏆 winner
              │
              ▼
   winner.think() + act() + haggle_intent()
   └─ logs the full contest + a 🎭 MOOD SWING alert if the winner changed
```

---

## 🗺️ Roadmap

**All 9 phases complete** ✅ — click any phase for details.

| Phase | Title | Status |
|:---:|---|:---:|
| 1 | Core Market Engine | ✅ |
| 2 | Agent Zoo (5 archetypes) | ✅ |
| 3 | Haggling / Negotiation Protocol | ✅ |
| 4 | Event Pipeline + Anomaly Detection | ✅ |
| 5 | Stress Testing & Scenarios | ✅ |
| 6 | Interactive GUI (Textual TUI) | ✅ |
| 7 | Consumption, Survival & Death | ✅ |
| 8 | Salaries / Cash Recirculation | ✅ |
| 9 | Price Anchoring & Trade Talk | ✅ |
| 10 | LLM-Backed Agents (Ollama / OpenAI / Anthropic) | ✅ |

<details>
<summary><b>📦 Phase 1 — Core Market Engine</b></summary>

- Central order book (bid/ask matching, midpoint price discovery, self-trade prevention)
- Tick-based loop with per-tick market state snapshots
- Agent base class: inventory, cash, `think()` + `act()`, `on_trade()` settlement
- Cash/inventory conservation
- CLI (`--sim`, `--ticks`, `--agents`, `--seed`, `--quiet`)
- 75 unit tests

</details>

<details>
<summary><b>🧠 Phase 2 — Agent Zoo</b></summary>

- Five distinct archetypes with full thought-process output
- `_pending_orders` pattern — `think()` decides, `act()` executes (log always matches action)
- `initial_price_history` seeding so all agents activate from tick 1
- 42 behavioral tests

</details>

<details>
<summary><b>🤝 Phase 3 — Haggling / Negotiation Protocol</b></summary>

- `HaggleIntent` — direction + ideal price + worst-acceptable price + quantity
- `HaggleSession` — N-round concession negotiation
- `HaggleCoordinator` — pairs compatible buyers/sellers, one session per agent per tick
- Per-archetype `haggle_intent()` overrides; `HybridNPC` delegates to its winner
- Pre-tick phase: bilateral trades settle before the order book runs
- `--haggle` flag · 42 tests

</details>

<details>
<summary><b>📡 Phase 4 — Event Pipeline</b></summary>

- `EventType` + `MarketEvent` typed schema (trades, tick summaries, anomalies)
- `EventBus` — in-process publish/subscribe
- `AuditConsumer` (full history → JSONL) + `AnomalyDetector` (cascades, drain, crash/spike, storms)
- `--events` (inline red anomaly alerts) · `--audit <path>` · 39 tests

</details>

<details>
<summary><b>💥 Phase 5 — Stress Testing & Scenarios</b></summary>

- `ScenarioEvent` + `ScenarioRunner` — timed interventions
- Four actions: `supply_shock`, `demand_surge`, `agent_collapse`, `price_inject`
- Three named failure-mode scenarios
- `MetricsCollector` + `gini()`, `price_volatility()`, `max_drawdown()`
- `--scenario`, `--metrics` flags · 59 tests

</details>

<details>
<summary><b>🎮 Phase 6 — Interactive GUI</b></summary>

- `GUILogger` — callback bridge (drop-in for `ThoughtLogger`)
- `SimulatorApp` — Textual TUI, multi-panel live layout
- Engine refactor to `prepare()` / `step()` / `finalize()`; semaphore-driven worker thread
- **Per-thought pacing** + **five live speed tiers** (`+`/`-` keys or dropdown)
- `--gui` flag

</details>

<details>
<summary><b>🍽️ Phase 7 — Consumption, Survival & Death</b></summary>

- Consumption ration each tick (`--consume`); survival bidding when runway is short
- Death after `starvation_limit` consecutive starved ticks
- `ProducerAgent` mints + sells surplus (keeps its own reserve)
- Consumers start on bare-minimum inventory
- Metrics: consumed, starvation ticks, deaths/survivors; final ALIVE/DEAD table · 41 tests

</details>

<details>
<summary><b>💵 Phase 8 — Salaries / Cash Recirculation</b></summary>

- Payroll phase: employers pay each living worker a wage (`--salary`)
- Affordable-split when employer can't cover the bill; **cash conserved**
- `is_employer` flag; dead workers aren't paid
- Metrics: total wages, per-agent `wages_received` / `wages_paid` · 10 tests

</details>

<details>
<summary><b>⚓ Phase 9 — Price Anchoring & Trade Talk</b></summary>

- Cost-plus price anchor (`base_cost × (1 + margin)`) — tames runaway inflation
- Survival bids reference the current best ask, not the runaway last price
- Sustainable steady state reachable (`--consume 3 --salary 70` → 0 deaths)
- **Trade Talk** — archetype-flavoured dialogue on every trade; dedicated GUI panel · 3 tests

</details>

<details>
<summary><b>🤖 Phase 10 — LLM-Backed Agents</b></summary>

- Pluggable `LLMClient` interface; `MockLLMClient` (offline/deterministic) + `OllamaClient`, `OpenAIClient`, `AnthropicClient` (stdlib `urllib`, no new deps)
- `llm/prompt.py` — context builder + robust JSON decision parser (tolerates fences/prose)
- `LLMAgent` — model reasoning → validated order, clamped to cash/inventory; falls back to rule logic on any failure
- `build_llm_roster()` — 5 personas + Producer; round-robins multiple models for head-to-head comparison
- `--llm SPEC[,SPEC2]` flag (CLI + GUI) · 35 tests (parsing, mock heuristics, registry, agent, integration)

</details>

---

## 📁 Project Structure

```
Simple-market-simulator/
│
├── main.py                     # CLI entry point
├── requirements.txt
│
├── market/                     # 🏛️ Core engine
│   ├── models.py               #   Order, Trade, MarketState
│   ├── order_book.py           #   Bid/ask matching, price discovery
│   ├── engine.py               #   Tick loop, settlement, all phases
│   ├── haggle.py               #   HaggleIntent, Session, Coordinator
│   ├── events.py               #   EventType, MarketEvent, EventBus
│   ├── consumers.py            #   AuditConsumer, AnomalyDetector
│   ├── metrics.py              #   gini(), volatility(), MetricsCollector
│   └── scenarios.py            #   ScenarioRunner + named scenarios
│
├── agents/                     # 🤖 Decision logic
│   ├── base.py                 #   Abstract Agent (think/act/consume/produce…)
│   ├── market_maker.py · speculator.py · hoarder.py
│   ├── panic.py · rational.py · producer.py
│   ├── random_agent.py         #   Baseline
│   ├── llm_agent.py            # 🤖 LLMAgent + build_llm_roster()
│   └── hybrid/                 # 🎭 Simulation 2
│       ├── activation.py       #   Per-archetype signal functions
│       ├── mood.py             #   Streak / volatility / cash / contagion
│       ├── personality.py      #   PersonalityProfile + ContestResult
│       ├── npc.py              #   HybridNPC (delegates to winner)
│       └── roster.py           #   Iris, Marcus, Dex, Vera, Rex (+ Producer)
│
├── llm/                        # 🤖 Model backends
│   ├── client.py               #   LLMClient ABC + MockLLMClient
│   ├── providers.py            #   Ollama / OpenAI / Anthropic (urllib)
│   ├── prompt.py               #   Prompt builder + decision parser
│   └── registry.py             #   "provider:model" -> client
│
├── logger/
│   └── thought_logger.py       # 🎨 Rich CLI output
│
├── gui/                        # 🎮 Textual TUI
│   ├── app.py                  #   SimulatorApp (panels + worker)
│   └── logger.py               #   GUILogger (callback bridge)
│
└── tests/                      # 🧪 424 tests across 18 files
    ├── test_models · order_book · base_agent · random_agent · engine
    ├── test_agents_zoo · haggle · events · metrics · scenarios
    ├── test_consumption · producer · salary · llm
    └── test_hybrid/  (activation · mood · personality · npc)
```

---

## 🎛️ CLI Reference

| Flag | Values | Description |
|---|---|---|
| `--sim` | `random` · `zoo` · `hybrid` | Simulation mode (default: `random`) |
| `--ticks` | int | Number of ticks (default: 20) |
| `--agents` | int | Agents in random mode (default: 4) |
| `--seed` | int | Random seed (default: 42) |
| `--quiet` | flag | Hide per-agent thought logs |
| `--haggle` | flag | Enable pre-market bilateral haggling |
| `--events` | flag | Enable event pipeline + inline anomaly detection |
| `--audit` | path | Write JSONL audit trail (needs `--events`) |
| `--metrics` | flag | Show metrics summary + per-agent PnL |
| `--scenario` | `hoarding_crash` · `panic_cascade` · `speculator_bubble` | Inject a stress scenario |
| `--consume` | float | Per-tick survival ration (drives survival/death). CLI off; GUI defaults Med |
| `--salary` | float | Wage paid per worker per tick (recirculates cash). CLI off; GUI defaults living wage |
| `--llm` | `mock` · `ollama:MODEL` · `openai:MODEL` · `anthropic:MODEL` (comma-separate for multiple) | Back agents with a language model |
| `--gui` | flag | Launch the interactive Textual TUI |

<details>
<summary><b>📋 More example commands</b></summary>

```bash
# Survival economy + liquidity-drain anomalies
python main.py --sim zoo --ticks 30 --consume 4 --events

# Sustainable steady state (nobody dies)
python main.py --sim zoo --ticks 25 --consume 3 --salary 70 --metrics --quiet

# Full kitchen-sink CLI run
python main.py --sim hybrid --ticks 30 --haggle --events --metrics --scenario panic_cascade

# GUI with a scenario pre-loaded
python main.py --gui --sim zoo --scenario panic_cascade

# Run the whole test suite
python -m pytest tests/ -v
```

</details>

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| 🐍 Simulation core | Python 3.11+ (stdlib only) |
| 📡 Event pipeline | In-process `EventBus` (Kafka-shaped schema; swap-in ready) |
| 🎨 CLI output | [`rich`](https://github.com/Textualize/rich) — panels, tables, colour |
| 🎮 Interactive GUI | [`textual`](https://github.com/Textualize/textual) — live multi-panel TUI |
| 🤖 LLM backends | Ollama · OpenAI · Anthropic (via stdlib `urllib`, no SDK required) |
| 🧪 Testing | [`pytest`](https://pytest.org) — **424 tests** across 18 files |

---

<div align="center">

### 🧩 Key Concepts

**Price Equilibrium Stress Testing** · **Autonomous Haggling** · **Systemic Liquidity Risk** · **Survival Economics**

*Built phase by phase — from a bare order book to a self-sustaining economy that you can break on demand.*

</div>
