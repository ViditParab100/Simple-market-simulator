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
