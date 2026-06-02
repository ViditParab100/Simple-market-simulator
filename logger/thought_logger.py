from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich import box
from market.models import Order, OrderSide, Trade

if TYPE_CHECKING:
    from agents.base import Agent
    from market.metrics import RunMetrics

console = Console()


class ThoughtLogger:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def log_header(self, num_agents: int, ticks: int):
        console.print()
        console.print(Panel(
            f"[bold cyan]Simple Market Simulator[/bold cyan]\n"
            f"[dim]{num_agents} agents  |  {ticks} ticks[/dim]",
            border_style="cyan",
            expand=False,
        ))
        console.print()

    def log_tick_start(self, tick: int):
        console.print(Rule(f"[bold white]Tick {tick}[/bold white]", style="dim white"))

    def log_thought(
        self,
        tick: int,
        agent_id: str,
        thoughts: list[str],
        orders: list[Order],
    ):
        if not self.verbose:
            return

        thought_lines = "\n".join(f"  [dim]>[/dim] {t}" for t in thoughts)

        if orders:
            order_lines = []
            for o in orders:
                if o.side == OrderSide.BID:
                    order_lines.append(f"  [bold green]BID[/bold green] {o.quantity} units @ [green]${o.price:.2f}[/green]")
                else:
                    order_lines.append(f"  [bold red]ASK[/bold red] {o.quantity} units @ [red]${o.price:.2f}[/red]")
            order_block = "\n".join(order_lines)
        else:
            order_block = "  [dim]-- HOLD -- no orders[/dim]"

        console.print(f"\n[bold yellow]>> {agent_id}[/bold yellow]")
        console.print(thought_lines)
        console.print(order_block)

    def log_consumption(self, tick: int, total_consumed: float, starving: list[str]):
        if not self.verbose:
            return
        msg = f"\n  [blue]~ CONSUMED[/blue] {total_consumed:.1f} units this tick"
        if starving:
            msg += f"  [bold red](STARVING: {', '.join(starving)})[/bold red]"
        console.print(msg)

    def log_anomaly(self, description: str, tick: int):
        console.print(
            f"\n[bold red][ANOMALY tick {tick}][/bold red] [red]{description}[/red]"
        )

    def log_haggle_session(self, log: list[str]):
        if not self.verbose:
            return
        lines = "\n".join(f"  [dim]{l}[/dim]" for l in log)
        console.print(f"\n[bold magenta]~~ HAGGLE ~~[/bold magenta]\n{lines}")

    def log_trade(self, trade: Trade):
        console.print(
            f"\n  [bold green]** TRADE[/bold green]  "
            f"[cyan]{trade.buyer_id}[/cyan] bought {trade.quantity} unit(s) "
            f"from [magenta]{trade.seller_id}[/magenta] "
            f"@ [bold green]${trade.price:.2f}[/bold green]"
        )

    def log_tick_summary(
        self,
        tick: int,
        last_price: Optional[float],
        best_bid: Optional[float],
        best_ask: Optional[float],
        num_trades: int,
    ):
        price_str = f"[bold]${last_price:.2f}[/bold]" if last_price else "[dim]N/A[/dim]"
        bid_str = f"[green]${best_bid:.2f}[/green]" if best_bid else "[dim]n/a[/dim]"
        ask_str = f"[red]${best_ask:.2f}[/red]" if best_ask else "[dim]n/a[/dim]"
        console.print(
            f"\n[dim]Tick {tick} summary -> Last: {price_str}  "
            f"Bid: {bid_str}  Ask: {ask_str}  Trades: {num_trades}[/dim]"
        )
        console.print()

    def log_final_state(self, agents: list[Agent], last_price: Optional[float]):
        console.print()
        console.print(Rule("[bold cyan]Final State[/bold cyan]", style="cyan"))

        table = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True)
        table.add_column("Agent", style="bold white")
        table.add_column("Inventory", justify="right", style="cyan")
        table.add_column("Cash", justify="right", style="green")
        table.add_column("Net Worth", justify="right", style="yellow")
        table.add_column("Trades", justify="right", style="dim")

        price = last_price or 0.0
        for agent in agents:
            table.add_row(
                agent.agent_id,
                str(agent.inventory),
                f"${agent.cash:.2f}",
                f"${agent.net_worth(price):.2f}",
                str(agent.trade_count),
            )

        console.print(table)

    def log_scenario_event(self, tick: int, description: str):
        console.print(
            f"\n[bold yellow][SCENARIO tick {tick}][/bold yellow] "
            f"[yellow]{description}[/yellow]"
        )

    def log_metrics_summary(self, metrics: RunMetrics):
        console.print()
        console.print(Rule("[bold cyan]Run Metrics[/bold cyan]", style="cyan"))

        # Price table
        price_table = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True)
        price_table.add_column("Metric",   style="bold white")
        price_table.add_column("Value",    justify="right", style="cyan")

        pct_move = f"{metrics.price_change_pct:+.1%}"
        color    = "green" if metrics.price_change_pct >= 0 else "red"
        price_table.add_row("Price start",    f"${metrics.price_start:.2f}")
        price_table.add_row("Price end",      f"[{color}]${metrics.price_end:.2f} ({pct_move})[/{color}]")
        price_table.add_row("Price range",    f"${metrics.price_min:.2f} - ${metrics.price_max:.2f}")
        price_table.add_row("Volatility",     f"${metrics.volatility:.3f}")
        price_table.add_row("Max drawdown",   f"{metrics.max_drawdown_pct:.1%}")
        price_table.add_row("Ticks / trades", f"{metrics.total_ticks} / {metrics.ticks_with_trades} active")
        price_table.add_row("Total volume",   f"{metrics.total_volume} units ({metrics.total_trades} trades)")
        price_table.add_row("Gini (start)",   f"{metrics.gini_start:.3f}")
        price_table.add_row("Gini (end)",     f"{metrics.gini_end:.3f}")
        if metrics.total_consumed > 0:
            price_table.add_row("Consumed",       f"{metrics.total_consumed:.0f} units")
            starve_str = f"{metrics.total_starvation}"
            if metrics.total_starvation > 0:
                starve_str = f"[red]{metrics.total_starvation}[/red]"
            price_table.add_row("Starvation ticks", starve_str)
        console.print(price_table)

        # Per-agent PnL
        show_survival = metrics.total_consumed > 0
        agent_table = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True,
                            title="Agent PnL")
        agent_table.add_column("Agent",      style="bold white")
        agent_table.add_column("Start NW",   justify="right")
        agent_table.add_column("End NW",     justify="right")
        agent_table.add_column("PnL",        justify="right")
        agent_table.add_column("Trades",     justify="right", style="dim")
        if show_survival:
            agent_table.add_column("Consumed", justify="right", style="blue")
            agent_table.add_column("Starved",  justify="right", style="red")

        for a in sorted(metrics.agents, key=lambda x: x.pnl, reverse=True):
            pnl_color = "green" if a.pnl >= 0 else "red"
            row = [
                a.agent_id,
                f"${a.net_worth_start:.2f}",
                f"${a.net_worth_end:.2f}",
                f"[{pnl_color}]{a.pnl:+.2f} ({a.pnl_pct:+.1%})[/{pnl_color}]",
                str(a.trade_count),
            ]
            if show_survival:
                row.append(f"{a.consumed:.0f}")
                row.append(str(a.starved_ticks) if a.starved_ticks else "-")
            agent_table.add_row(*row)
        console.print(agent_table)
