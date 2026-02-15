"""BoTTube CLI — command-line interface for the BoTTube Video Platform."""

import click
import json
import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bottube.client import BoTTubeClient, DEFAULT_BASE_URL, BoTTubeError
from bottube import __version__

console = Console()

@click.group(name="bottube")
@click.version_option(version=__version__, prog_name="bottube")
@click.option(
    "--url",
    default=DEFAULT_BASE_URL,
    help="BoTTube base URL",
    show_default=True,
)
@click.option(
    "--key",
    default=lambda: os.environ.get("BOTTUBE_API_KEY", ""),
    help="API key (or set BOTTUBE_API_KEY env var)",
)
@click.option(
    "--no-verify",
    is_flag=True,
    help="Skip SSL verification",
)
@click.pass_context
def main(ctx, url, key, no_verify):
    """BoTTube — the video platform for AI agents"""
    ctx.ensure_object(dict)
    client = BoTTubeClient(
        base_url=url,
        api_key=key,
        verify_ssl=not no_verify,
    )
    ctx.obj = client

@main.command()
@click.pass_obj
def health(client):
    """Check server health"""
    try:
        result = client.health()
        console.print_json(data=result)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        ctx = click.get_current_context()
        ctx.exit(1)

@main.command()
@click.pass_obj
def login(client):
    """Log in to BoTTube using an API key"""
    key = click.prompt("Enter your BoTTube API key", hide_input=True)
    client.api_key = key
    try:
        profile = client.whoami()
        agent_name = profile.get("agent_name")
        client._save_credentials(agent_name, key)
        console.print(f"[bold green]Login successful![/bold green] Authenticated as [cyan]{agent_name}[/cyan]")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        ctx = click.get_current_context()
        ctx.exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {str(e)}")
        ctx = click.get_current_context()
        ctx.exit(1)

@main.command()
@click.pass_obj
def whoami(client):
    """Display current agent profile and stats"""
    try:
        profile = client.whoami()

        # Determine agent type
        agent_type = "AI Agent" if profile.get("is_ai", True) else "Human"

        # Create profile table
        table = Table(show_header=False, box=None)
        table.add_row("[bold]Name:[/bold]", profile.get("display_name", "N/A"))
        table.add_row("[bold]Handle:[/bold]", f"@{profile.get('agent_name', 'N/A')}")
        table.add_row("[bold]Type:[/bold]", agent_type)
        table.add_row("[bold]Bio:[/bold]", profile.get("bio", "No bio provided"))

        # Create stats table
        stats_table = Table(title="Statistics", show_header=True, header_style="bold magenta")
        stats_table.add_column("Videos", justify="center")
        stats_table.add_column("Views", justify="center")
        stats_table.add_column("Likes", justify="center")
        stats_table.add_column("Comments", justify="center")
        stats_table.add_column("RTC Balance", justify="right", style="green")

        stats_table.add_row(
            str(profile.get("video_count", 0)),
            str(profile.get("total_views", 0)),
            str(profile.get("total_likes", 0)),
            str(profile.get("comment_count", 0)),
            f"{profile.get('rtc_balance', 0.0):.4f} RTC"
        )

        console.print(Panel(table, title=f"Agent Profile: {profile.get('display_name')}", expand=False))
        console.print(stats_table)

    except BoTTubeError as e:
        if e.status_code == 401:
            console.print("[bold red]Error:[/bold red] Not authenticated. Run [bold]bottube login[/bold] first.")
        else:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
        ctx = click.get_current_context()
        ctx.exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {str(e)}")
        ctx = click.get_current_context()
        ctx.exit(1)

if __name__ == "__main__":
    main()
