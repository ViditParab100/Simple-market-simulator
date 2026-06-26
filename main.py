import argparse
import random

from market.engine import SimulationEngine
from agents.random_agent import RandomAgent
from agents.market_maker import MarketMakerAgent
from agents.speculator import SpeculatorAgent
from agents.hoarder import HoarderAgent
from agents.panic import PanicAgent
from agents.rational import RationalAgent
from agents.producer import ProducerAgent
from agents.llm_agent import build_llm_roster
from agents.hybrid.roster import build_roster
from market.haggle import HaggleCoordinator
from market.auction import AuctionCoordinator
from market.events import EventBus, EventType
from market.consumers import AuditConsumer, AnomalyDetector
from market.metrics import MetricsCollector
from market.scenarios import NAMED_SCENARIOS
from logger.thought_logger import ThoughtLogger

# Seed price history: mild uptrend so momentum/fair-value agents activate from tick 1
_SEED_HISTORY = [round(19.0 + i * 0.25, 2) for i in range(10)]


def build_random_agents(n: int, seed: int) -> list:
    rng = random.Random(seed)
    agents = [ProducerAgent("Producer-01", inventory=12, cash=200.0, production_rate=20)]
    agents += [
        RandomAgent(
            agent_id=f"Random-{i + 1:02d}",
            inventory=rng.randint(3, 8),
            cash=round(rng.uniform(200, 600), 2),
            seed=seed + i,
        )
        for i in range(n)
    ]
    return agents


def build_zoo_agents() -> list:
    # Consumers start on bare-minimum inventory — they depend on the Producer
    # for supply. The Producer mints fresh units every tick.
    return [
        ProducerAgent("Producer-01",       inventory=12, cash=200.0, production_rate=20),
        MarketMakerAgent("MarketMaker-01", inventory=5,  cash=800.0),
        SpeculatorAgent("Speculator-01",   inventory=4,  cash=600.0),
        HoarderAgent("Hoarder-01",         inventory=4,  cash=1000.0, hoard_target=60),
        PanicAgent("Panic-01",             inventory=6,  cash=300.0),
        RationalAgent("Rational-01",       inventory=5,  cash=500.0),
    ]


def main():
    parser = argparse.ArgumentParser(description="Simple Market Simulator")
    parser.add_argument("--sim",    choices=["random", "zoo", "hybrid"], default="random",
                        help="Simulation mode: random | zoo | hybrid (default: random)")
    parser.add_argument("--ticks",  type=int, default=20,
                        help="Number of simulation ticks (default: 20)")
    parser.add_argument("--agents", type=int, default=4,
                        help="Number of agents for random mode (default: 4)")
    parser.add_argument("--seed",   type=int, default=42,
                        help="Random seed for random mode (default: 42)")
    parser.add_argument("--quiet",  action="store_true",
                        help="Hide per-agent thought logs")
    parser.add_argument("--haggle",  action="store_true",
                        help="Enable pre-tick bilateral haggling phase")
    parser.add_argument("--auction", action="store_true",
                        help="Enable English auction phase: Producer offloads surplus "
                             "via ascending-price bidding (triggers when surplus >= 35 units)")
    parser.add_argument("--events", action="store_true",
                        help="Enable event pipeline with anomaly detection")
    parser.add_argument("--audit",    type=str, default=None, metavar="PATH",
                        help="Write JSONL audit trail to PATH (requires --events)")
    parser.add_argument("--metrics", action="store_true",
                        help="Show run metrics summary at end")
    parser.add_argument("--scenario", choices=list(NAMED_SCENARIOS.keys()), default=None,
                        help="Inject a named stress-test scenario")
    parser.add_argument("--consume", type=float, default=-1.0, metavar="RATE",
                        help="Per-tick survival ration for every agent. Default: 3.0 (all modes). "
                             "Pass 0 to disable survival (market freezes — no buying pressure).")
    parser.add_argument("--salary",  type=float, default=-1.0, metavar="WAGE",
                        help="Wage the Producer pays each worker per tick. Default: 70.0 (all modes). "
                             "Pass 0 to disable wages (agents go broke and starve).")
    parser.add_argument("--llm",     type=str, default=None, metavar="SPEC",
                        help="Back agents with a language model. e.g. 'mock', "
                             "'ollama:llama3.2', 'openai:gpt-4o-mini', "
                             "'groq:llama-3.1-8b-instant', 'groq:gemma2-9b-it'. "
                             "Comma-separate multiple specs to run models head-to-head.")
    parser.add_argument("--speed",   type=str, default="very_slow",
                        choices=["very_slow", "slow", "normal", "fast", "instant"],
                        help="Initial GUI speed (default: very_slow)")
    parser.add_argument("--gui",     action="store_true",
                        help="Launch the interactive Textual GUI")
    args = parser.parse_args()

    if args.gui:
        from gui.app import launch
        launch(
            sim_mode=args.sim,
            scenario=args.scenario or "none",
            ticks=args.ticks,
            speed=args.speed,
            haggle=args.haggle,
            # explicit flags override; otherwise GUI uses its visible defaults
            consumption=args.consume if args.consume >= 0 else 4.0,
            salary=args.salary if args.salary >= 0 else 70.0,
            llm=args.llm,
        )
        return

    # survival is always on — food is a necessity in every mode
    consume_rate = args.consume if args.consume >= 0 else 3.0
    salary_rate  = args.salary  if args.salary  >= 0 else 70.0

    if args.llm:
        agents       = build_llm_roster(args.llm)
        seed_history = _SEED_HISTORY
    elif args.sim == "hybrid":
        agents       = build_roster()
        seed_history = _SEED_HISTORY
    elif args.sim == "zoo":
        agents       = build_zoo_agents()
        seed_history = _SEED_HISTORY
    else:
        agents       = build_random_agents(args.agents, args.seed)
        seed_history = _SEED_HISTORY

    logger           = ThoughtLogger(verbose=not args.quiet)
    coordinator      = HaggleCoordinator(max_rounds=3) if args.haggle else None
    auction_coord    = AuctionCoordinator() if args.auction else None

    # Event pipeline
    bus      = None
    audit    = None
    detector = None
    if args.events:
        bus      = EventBus()
        audit    = AuditConsumer(bus)
        detector = AnomalyDetector(bus)
        # Print anomalies inline as they are detected
        bus.subscribe(EventType.ANOMALY,
                      lambda e: logger.log_anomaly(e.metadata.get("description", ""), e.tick))

    scenario  = NAMED_SCENARIOS.get(args.scenario) if args.scenario else None
    collector = MetricsCollector() if args.metrics else None

    engine = SimulationEngine(
        agents=agents, logger=logger,
        initial_price_history=seed_history,
        haggle_coordinator=coordinator,
        auction_coordinator=auction_coord,
        event_bus=bus,
        scenario_runner=scenario,
        metrics_collector=collector,
        consumption_rate=consume_rate,
        salary=salary_rate,
    )
    engine.run(ticks=args.ticks)

    # Post-run: write audit trail
    if audit and args.audit:
        audit.export_jsonl(args.audit)
        print(f"\nAudit trail written to {args.audit} ({len(audit.events)} events)")

    # Post-run: anomaly summary
    if detector and detector.anomalies:
        print(f"\n{len(detector.anomalies)} anomaly/anomalies detected during this run.")


if __name__ == "__main__":
    main()
