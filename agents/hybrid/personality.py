"""
PersonalityProfile: holds an NPC's archetype weights and runs the
activation contest each tick to determine which archetype takes control.
"""
from __future__ import annotations
from dataclasses import dataclass
from market.models import MarketState
from .activation import ArchetypeTag, SIGNAL_FN, _clamp
from .mood import MoodState, compute_mood_deltas


@dataclass
class ContestResult:
    winner: ArchetypeTag
    scores: dict[ArchetypeTag, float]       # final scores after mood deltas
    raw_signals: dict[ArchetypeTag, float]  # pre-mood activation signals
    mood_deltas: dict[ArchetypeTag, float]
    runner_up: ArchetypeTag
    margin: float                           # winner score - runner_up score

    def thought_lines(self) -> list[str]:
        """Return formatted lines for the activation contest section of the thought log."""
        lines = ["Activation contest:"]
        for tag in sorted(self.scores, key=lambda t: self.scores[t], reverse=True):
            score  = self.scores[tag]
            signal = self.raw_signals.get(tag, 0.0)
            delta  = self.mood_deltas.get(tag, 0.0)
            delta_str = f"  mood {delta:+.2f}" if abs(delta) > 0.001 else ""
            lines.append(
                f"  | {tag.value:<12} {score:.2f}  (signal {signal:.2f}{delta_str})"
            )
        lines.append(
            f"DOMINANT MODE: {self.winner.value}  "
            f"[beat {self.runner_up.value} by +{self.margin:.2f}]"
        )
        return lines


class PersonalityProfile:
    """
    Encapsulates an NPC's fixed archetype weights and runs the activation
    contest each tick.

    base_weights: dict mapping ArchetypeTag -> weight (should sum to ~1.0,
                  but does not have to — they are relative, not absolute).
    """

    def __init__(self, base_weights: dict[ArchetypeTag, float]):
        if not base_weights:
            raise ValueError("PersonalityProfile requires at least one archetype.")
        total = sum(base_weights.values())
        # Normalise so weights sum to 1.0
        self.base_weights: dict[ArchetypeTag, float] = {
            tag: w / total for tag, w in base_weights.items()
        }

    def run_contest(
        self,
        state: MarketState,
        inventory: int,
        cash: float,
        mood: MoodState,
        agent_id: str,
        **signal_kwargs,
    ) -> ContestResult:
        last_price = state.last_price or 20.0

        # 1. Raw activation signal per archetype
        raw: dict[ArchetypeTag, float] = {}
        for tag, weight in self.base_weights.items():
            fn = SIGNAL_FN[tag]
            raw[tag] = fn(state, inventory, cash)

        # 2. Mood deltas
        deltas = compute_mood_deltas(
            mood, agent_id, cash, state.price_history, last_price
        )

        # 3. Final score = base_weight * (raw_signal + mood_delta), clamped
        scores: dict[ArchetypeTag, float] = {}
        for tag, weight in self.base_weights.items():
            delta = deltas.get(tag, 0.0)
            scores[tag] = _clamp(weight * _clamp(raw[tag] + delta))

        # 4. Pick winner
        ranked = sorted(scores, key=lambda t: scores[t], reverse=True)
        winner     = ranked[0]
        runner_up  = ranked[1] if len(ranked) > 1 else winner
        margin     = round(scores[winner] - scores[runner_up], 4)

        return ContestResult(
            winner=winner,
            scores=scores,
            raw_signals=raw,
            mood_deltas=deltas,
            runner_up=runner_up,
            margin=margin,
        )

    def label(self) -> str:
        """Human-readable personality label, e.g. 'Rational 50% | Speculator 35% | Panic 15%'"""
        parts = sorted(self.base_weights.items(), key=lambda x: x[1], reverse=True)
        return " | ".join(f"{tag.value} {w:.0%}" for tag, w in parts)
