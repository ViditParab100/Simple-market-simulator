import argparse
import random

from market.engine import SimulationEngine
from agents.random_agent import RandomAgent
from agents.market_maker import MarketMakerAgent
from agents.speculator import SpeculatorAgent
from agents.hoarder import HoarderAgent
from agents.panic import PanicAgent
from agents.rational import RationalAgent
from logger.thought_logger import ThoughtLogger


def build_random_agents(n: int, seed: int) -> list:
    rng = random.Random(seed)
    return [
        RandomAgent(
            agent_id=f"Random-{i + 1:02d}",
            inventory=rng.randint(10, 50),
            cash=round(rng.uniform(200, 600), 2),
            seed=seed + i,
        )
        for i in range(n)
    ]


def build_zoo_agents() -> list:
    return [
        MarketMakerAgent("MarketMaker-01", inventory=30, cash=800.0),
        SpeculatorAgent("Speculator-01",   inventory=10, cash=600.0),
        HoarderAgent("Hoarder-01",         inventory=20, cash=1000.0, hoard_target=60),
        PanicAgent("Panic-01",             inventory=40, cash=300.0),
        RationalAgent("Rational-01",       inventory=25, cash=500.0),
    ]


def main():
    parser = argparse.ArgumentParser(description="Simple Market Simulator")
    parser.add_argument("--sim",    choices=["random", "zoo"], default="random",
                        help="Simulation mode: 'random' (default) or 'zoo' (5 archetypes)")
    parser.add_argument("--ticks",  type=int, default=20,
                        help="Number of simulation ticks (default: 20)")
    parser.add_argument("--agents", type=int, default=4,
                        help="Number of agents for random mode (default: 4)")
    parser.add_argument("--seed",   type=int, default=42,
                        help="Random seed for random mode (default: 42)")
    parser.add_argument("--quiet",  action="store_true",
                        help="Hide per-agent thought logs")
    args = parser.parse_args()

    agents = build_zoo_agents() if args.sim == "zoo" else build_random_agents(args.agents, args.seed)
    logger = ThoughtLogger(verbose=not args.quiet)

    # Seed zoo with a mild uptrend so momentum/fair-value agents have context from tick 1
    seed_history = [round(19.0 + i * 0.25, 2) for i in range(10)] if args.sim == "zoo" else None

    engine = SimulationEngine(agents=agents, logger=logger, initial_price_history=seed_history)
    engine.run(ticks=args.ticks)


if __name__ == "__main__":
    main()
