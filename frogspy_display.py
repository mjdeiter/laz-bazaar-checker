"""
frogspy_display.py  --  Drop-in pretty printer for FrogSpy output.

Usage
-----
Import and call print_report(results, trader, elapsed) at the end of your
existing FrogSpy scan, replacing the current text dump.

Requires: pip install rich
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.columns import Columns

console = Console()


# ── Status config ──────────────────────────────────────────────────────────────

STATUS_UNDERCUT  = "undercut"
STATUS_NONE      = "none"       # no competition
STATUS_CHEAPEST  = "cheapest"

STATUS_STYLE = {
    STATUS_UNDERCUT: ("UNDERCUT",  "bold yellow"),
    STATUS_NONE:     ("SOLO",      "bold green"),
    STATUS_CHEAPEST: ("CHEAPEST",  "bold cyan"),
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def fmt(n):
    """Format an integer with commas, or return a dim dash."""
    if n is None:
        return "[dim]—[/dim]"
    return f"{n:,}"


def pct_diff(your_price, lowest):
    """Return a coloured percentage string showing how far above lowest you are."""
    if lowest is None or lowest == 0:
        return ""
    diff = your_price - lowest
    p = (diff / lowest) * 100
    if p > 0:
        return f"[yellow]+{p:.0f}%[/yellow]"
    return f"[green]{p:.0f}%[/green]"


# ── Inline scan-time printer (replaces the per-item print in the loop) ─────────

def print_item_line(item: dict):
    """
    Call this inside your scan loop instead of a plain print().
    item keys: name, your_price, status, lowest, rivals, low7, med7
    """
    name       = item["name"]
    your_price = item["your_price"]
    status     = item["status"]
    lowest     = item.get("lowest")
    rivals     = item.get("rivals", 0)
    low7       = item.get("low7")
    med7       = item.get("med7")

    if status == STATUS_UNDERCUT:
        badge_style = "bold white on red"
    elif status == STATUS_CHEAPEST:
        badge_style = "bold white on cyan"
    else:
        badge_style = "bold white on green"

    label = STATUS_STYLE[status][0]
    badge = Text(f" {label} ", style=badge_style)

    line = Text()
    line.append(f"  {name}", style="bold white")
    line.append(f"  {your_price:,}", style="dim white")
    line.append("  ")
    line.append_text(badge)

    if status == STATUS_UNDERCUT and lowest is not None:
        diff = your_price - lowest
        line.append(f"  vs {lowest:,}  ", style="yellow")
        line.append(f"(+{diff:,} / {pct_diff(your_price, lowest)})", style="dim yellow")
        line.append(f"  {rivals} rival{'s' if rivals != 1 else ''}", style="dim")

    if low7 is not None:
        line.append(f"  [7d low:{low7:,}  med:{med7:,}]", style="dim blue")

    console.print(line)


# ── End-of-scan summary table ──────────────────────────────────────────────────

def print_report(results: list, trader: str, elapsed: float, timestamp: str = ""):
    """
    Print the full summary table after the scan completes.

    results: list of item dicts (same structure as print_item_line)
    trader:  trader name string
    elapsed: scan time in seconds
    """

    # ── Summary stat cards ────────────────────────────────────────────────────
    total     = len(results)
    undercut  = sum(1 for r in results if r["status"] == STATUS_UNDERCUT)
    solo      = sum(1 for r in results if r["status"] == STATUS_NONE)
    cheapest  = sum(1 for r in results if r["status"] == STATUS_CHEAPEST)

    cards = [
        Panel(f"[bold white]{total}[/bold white]\n[dim]items checked[/dim]",       border_style="white",  padding=(0, 2)),
        Panel(f"[bold yellow]{undercut}[/bold yellow]\n[dim]being undercut[/dim]",  border_style="yellow", padding=(0, 2)),
        Panel(f"[bold green]{solo}[/bold green]\n[dim]no competition[/dim]",        border_style="green",  padding=(0, 2)),
        Panel(f"[bold cyan]{cheapest}[/bold cyan]\n[dim]cheapest / tied[/dim]",     border_style="cyan",   padding=(0, 2)),
    ]

    console.rule(f"[bold white]FrogSpy[/bold white]  [dim]{trader}[/dim]  [dim]{timestamp}[/dim]")
    console.print(Columns(cards, equal=True, expand=True))

    # ── Detail table ──────────────────────────────────────────────────────────
    table = Table(
        box=box.SIMPLE_HEAD,
        show_footer=False,
        header_style="bold dim",
        expand=True,
    )

    table.add_column("Item",       style="white",     no_wrap=False, ratio=4)
    table.add_column("Your price", style="white",     justify="right", ratio=2)
    table.add_column("Lowest",     style="yellow",    justify="right", ratio=2)
    table.add_column("Gap",        style="dim yellow", justify="right", ratio=1)
    table.add_column("Rivals",     style="dim",       justify="center", ratio=1)
    table.add_column("7d low",     style="dim blue",  justify="right", ratio=2)
    table.add_column("7d med",     style="dim blue",  justify="right", ratio=2)
    table.add_column("Status",     justify="center",  ratio=2)

    # Sort: undercuts first, then solo, then cheapest
    order = {STATUS_UNDERCUT: 0, STATUS_NONE: 1, STATUS_CHEAPEST: 2}
    sorted_results = sorted(results, key=lambda r: order[r["status"]])

    for item in sorted_results:
        status   = item["status"]
        lowest   = item.get("lowest")
        rivals   = item.get("rivals", 0)
        low7     = item.get("low7")
        med7     = item.get("med7")

        label = STATUS_STYLE[status][0]
        if status == STATUS_UNDERCUT:
            badge = Text(f" {label} ", style="bold white on red")
        elif status == STATUS_CHEAPEST:
            badge = Text(f" {label} ", style="bold white on cyan")
        else:
            badge = Text(f" {label} ", style="bold white on green")

        lowest_str = fmt(lowest) if lowest is not None else "[dim]—[/dim]"
        gap_str    = pct_diff(item["your_price"], lowest) if lowest else "[dim]—[/dim]"
        rivals_str = str(rivals) if rivals else "[dim]—[/dim]"

        table.add_row(
            item["name"],
            fmt(item["your_price"]),
            lowest_str,
            gap_str,
            rivals_str,
            fmt(low7),
            fmt(med7),
            badge,
        )

    console.print(table)
    console.print(f"[dim]Scan completed in {elapsed:.1f}s[/dim]\n")
