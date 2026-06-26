"""
Named NPC definitions for Simulation 2.

Each NPC has a distinct personality that creates a different style of
market participation. The roster is designed so the five characters
together cover all five archetypes as either a primary or secondary trait,
ensuring a well-rounded market with realistic emergent behaviour.
"""
from __future__ import annotations
from .activation import ArchetypeTag
from .personality import PersonalityProfile
from .npc import HybridNPC
from agents.producer import ProducerAgent


def build_roster(seed_price: float = 20.0) -> list:
    """
    Return the default cast for --sim hybrid: one Producer (supply) plus five
    mixed-personality NPCs that start on bare-minimum inventory and depend on
    the Producer for supply.
    """
    return [
        # Producer: the supply side — mints fresh units every tick.
        ProducerAgent("Producer", inventory=12, cash=200.0, production_rate=20),

        # Iris: fundamentals-first with a speculative streak
        # Usually calm and rational, but chases momentum when it's strong enough
        HybridNPC(
            agent_id="Iris",
            inventory=6,
            cash=600.0,
            profile=PersonalityProfile({
                ArchetypeTag.RATIONAL:     0.50,
                ArchetypeTag.SPECULATOR:   0.35,
                ArchetypeTag.PANIC:        0.15,
            }),
        ),

        # Marcus: cautious accumulator who also likes making spreads
        # Steady buyer in thin markets; pivots to market-making when inventory is full
        HybridNPC(
            agent_id="Marcus",
            inventory=5,
            cash=900.0,
            profile=PersonalityProfile({
                ArchetypeTag.HOARDER:      0.55,  # was 0.60 — gave too much edge over MM
                ArchetypeTag.MARKET_MAKER: 0.45,  # was 0.40
            }),
        ),

        # Dex: thrill-seeker — panics badly under pressure, speculates in uptrends
        # Amplifies trends in both directions; most likely to trigger a cascade
        HybridNPC(
            agent_id="Dex",
            inventory=4,
            cash=400.0,
            profile=PersonalityProfile({
                ArchetypeTag.PANIC:        0.50,  # was 0.35 — must dominate in crashes
                ArchetypeTag.SPECULATOR:   0.30,  # was 0.45 — still wins in uptrends
                ArchetypeTag.RATIONAL:     0.20,
            }),
        ),

        # Vera: liquidity provider who hoards when supply is scarce
        # Normally stabilising; can flip to hoarder behaviour during supply shocks
        HybridNPC(
            agent_id="Vera",
            inventory=6,
            cash=700.0,
            profile=PersonalityProfile({
                ArchetypeTag.MARKET_MAKER: 0.55,
                ArchetypeTag.HOARDER:      0.30,
                ArchetypeTag.RATIONAL:     0.15,
            }),
        ),

        # Rex: loss-averse accumulator — hoards relentlessly but panics on drawdowns
        # Creates scarcity in calm markets, then dumps everything in a crash
        HybridNPC(
            agent_id="Rex",
            inventory=5,
            cash=500.0,
            profile=PersonalityProfile({
                ArchetypeTag.HOARDER:      0.40,  # was 0.50 — pure hoarding suppressed contagion panic
                ArchetypeTag.PANIC:        0.40,  # was 0.30 — now reacts to contagion + downtrends
                ArchetypeTag.SPECULATOR:   0.20,
            }),
        ),
    ]
