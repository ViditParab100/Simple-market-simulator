"""
HybridNPC: an agent whose behaviour is decided each tick by an activation
contest between its embedded archetypes.
"""
from __future__ import annotations
from market.models import Order, Trade, MarketState
from market.haggle import HaggleIntent
from agents.base import Agent
from agents.market_maker import MarketMakerAgent
from agents.speculator import SpeculatorAgent
from agents.hoarder import HoarderAgent
from agents.panic import PanicAgent
from agents.rational import RationalAgent
from .activation import ArchetypeTag
from .mood import MoodState
from .personality import PersonalityProfile, ContestResult


class HybridNPC(Agent):
    """
    An NPC with a mixed personality. Each tick:
      1. PersonalityProfile runs the activation contest.
      2. The winning archetype's think() + act() logic runs.
      3. PanicAgent FSM state is synced back so recovery persists.
      4. Mood state is updated from trade history.
    """

    def __init__(
        self,
        agent_id: str,
        inventory: int,
        cash: float,
        profile: PersonalityProfile,
    ):
        super().__init__(agent_id, inventory, cash)
        self.profile = profile
        self.mood    = MoodState()

        self._last_winner:    ArchetypeTag | None  = None
        self._last_contest:   ContestResult | None = None
        self._pending_orders: list[Order]           = []

        # PanicAgent FSM state threaded across ticks
        self._panic_state:    str = "calm"
        self._panic_recovery: int = 0

    # ------------------------------------------------------------------
    # Agent interface
    # ------------------------------------------------------------------

    def think(self, state: MarketState) -> list[str]:
        last_price  = state.last_price or 20.0
        prev_winner = self._last_winner

        # 1. Run activation contest
        contest = self.profile.run_contest(
            state, self.inventory, self.cash, self.mood, self.agent_id
        )
        self._last_contest = contest
        winner = contest.winner

        # 2. Build header
        thoughts: list[str] = [
            f"Inventory: {self.inventory} units  |  Cash: ${self.cash:.2f}  |  Market: ${last_price:.2f}",
            f"Personality: {self.profile.label()}",
        ]

        # 3. Active mood modifiers (skip zero-delta entries)
        active_moods = {t: d for t, d in contest.mood_deltas.items() if abs(d) > 0.001}
        if active_moods:
            mood_str = "  ".join(f"{t.value} {d:+.2f}" for t, d in active_moods.items())
            thoughts.append(f"Mood modifiers: {mood_str}")

        # 4. Activation contest log
        thoughts.extend(contest.thought_lines())

        # 5. Mood swing alert
        if prev_winner is not None and winner != prev_winner:
            thoughts.append(f"** MOOD SWING: {prev_winner.value} -> {winner.value} **")

        # 6. Build delegate and run its logic
        delegate = self._build_delegate(winner)
        delegate_thoughts = delegate.think(state)
        orders            = delegate.act(state)

        # 7. Sync PanicAgent FSM state back so recovery carries over
        if winner == ArchetypeTag.PANIC:
            self._panic_state    = delegate._state
            self._panic_recovery = delegate._recovery_counter

        # 8. Append delegate voice to thoughts
        if delegate_thoughts:
            thoughts.append(f"[{winner.value}] {delegate_thoughts[0]}")
            for line in delegate_thoughts[1:]:
                thoughts.append(f"  {line}")

        self._pending_orders = orders
        self._last_winner    = winner
        return thoughts

    def act(self, state: MarketState) -> list[Order]:
        return self._pending_orders

    def on_trade(self, trade: Trade):
        super().on_trade(trade)
        self.mood.record_trade(trade, self.agent_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_delegate(self, tag: ArchetypeTag) -> Agent:
        """Fresh delegate carrying this NPC's current inventory/cash."""
        factories = {
            ArchetypeTag.MARKET_MAKER: lambda: MarketMakerAgent(self.agent_id, self.inventory, self.cash),
            ArchetypeTag.SPECULATOR:   lambda: SpeculatorAgent(self.agent_id, self.inventory, self.cash),
            ArchetypeTag.HOARDER:      lambda: HoarderAgent(self.agent_id, self.inventory, self.cash),
            ArchetypeTag.PANIC:        lambda: PanicAgent(self.agent_id, self.inventory, self.cash),
            ArchetypeTag.RATIONAL:     lambda: RationalAgent(self.agent_id, self.inventory, self.cash),
        }
        delegate = factories[tag]()

        # Thread PanicAgent FSM so recovery state persists across ticks
        if tag == ArchetypeTag.PANIC:
            delegate._state            = self._panic_state
            delegate._recovery_counter = self._panic_recovery

        return delegate

    def haggle_intent(self, state: MarketState) -> HaggleIntent | None:
        """Delegate haggle intent to whichever archetype last won the contest."""
        if self._last_winner is None:
            return None
        delegate = self._build_delegate(self._last_winner)
        return delegate.haggle_intent(state)

    @property
    def dominant_archetype(self) -> ArchetypeTag | None:
        return self._last_winner
