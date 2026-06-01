import argparse
import random

from market.engine import SimulationEngine
from agents.random_agent import RandomAgent
from logger.thought_logger import ThoughtLogger


def main():
    parser = argparse.ArgumentParser(description="Simple Market Simulator — Phase 1")
    parser.add_argument("--ticks",  type=int,  default=10,    help="Number of simulation ticks (default: 10)")
    parser.add_argument("--agents", type=int,  default=4,     help="Number of random agents (default: 4)")
    parser.add_argument("--seed",   type=int,  default=42,    help="Random seed (default: 42)")
    parser.add_argument("--quiet",  action="store_true",      help="Hide per-agent thought logs")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    agents = [
        RandomAgent(
            agent_id=f"Random-{i + 1:02d}",
            inventory=rng.randint(10, 50),
            cash=round(rng.uniform(200, 600), 2),
            seed=args.seed + i,
        )
        for i in range(args.agents)
    ]

    logger = ThoughtLogger(verbose=not args.quiet)
    engine = SimulationEngine(agents=agents, logger=logger)
    engine.run(ticks=args.ticks)


if __name__ == "__main__":
    main()
