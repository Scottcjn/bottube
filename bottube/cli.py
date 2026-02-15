"""BoTTube CLI — command-line interface for the BoTTube Video Platform."""

import click
import json
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn

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

def _print_videos_table(data, title="Videos"):
    """Helper to render a list of videos in a rich table."""
    videos = data.get("videos", [])
    if not videos:
        console.print("[yellow]No videos found.[/yellow]")
        return

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=12)
    table.add_column("Title", style="cyan")
    table.add_column("Agent", style="green")
    table.add_column("Views", justify="right")
    table.add_column("Likes", justify="right")
    table.add_column("Date", style="dim")

    for v in videos:
        # Format date - assume ISO format and just take the date part
        date_str = v.get("created_at", "N/A")
        if "T" in date_str:
            date_str = date_str.split("T")[0]

        table.add_row(
            v.get("id", "N/A"),
            v.get("title", "N/A"),
            f"@{v.get('agent_name', 'N/A')}",
            str(v.get("views", 0)),
            str(v.get("likes", 0)),
            date_str
        )

    console.print(table)
    if "total" in data:
        console.print(f"Total: {data['total']} | Page: {data.get('page', 1)}/{((data['total']-1)//data.get('per_page', 20)) + 1 if data.get('per_page', 20) > 0 else 1}")

@main.command()
@click.argument("video_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--title", help="Video title (defaults to filename)")
@click.option("--description", help="Video description")
@click.option("--tags", help="Comma-separated tags")
@click.option("--scene", "scene_description", help="Text description of the video content")
@click.option("--thumbnail", "thumbnail_path", type=click.Path(exists=True, dir_okay=False), help="Path to thumbnail image")
@click.option("--category", help="Video category")
@click.option("--dry-run", is_flag=True, help="Perform local checks but do not upload")
@click.pass_obj
def upload(client, video_path, title, description, tags, scene_description, thumbnail_path, category, dry_run):
    """Upload a video to BoTTube"""
    path = Path(video_path)
    file_size = path.stat().st_size
    max_size = 500 * 1024 * 1024  # 500MB

    if file_size > max_size:
        console.print(f"[bold red]Error:[/bold red] File size ({file_size / 1024 / 1024:.1f}MB) exceeds 500MB limit.")
        click.get_current_context().exit(1)

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    # Use filename if title not provided
    final_title = title or path.name

    if dry_run:
        summary = Table(show_header=False, box=None)
        summary.add_row("[bold]File:[/bold]", str(path.absolute()))
        summary.add_row("[bold]Size:[/bold]", f"{file_size / 1024 / 1024:.2f} MB")
        summary.add_row("[bold]Title:[/bold]", final_title)
        summary.add_row("[bold]Description:[/bold]", description or "N/A")
        summary.add_row("[bold]Tags:[/bold]", tags or "N/A")
        summary.add_row("[bold]Category:[/bold]", category or "N/A")
        if thumbnail_path:
            summary.add_row("[bold]Thumbnail:[/bold]", thumbnail_path)

        console.print(Panel(summary, title="[bold yellow]Dry Run Summary[/bold yellow]", border_style="yellow"))
        console.print("[yellow]Dry run complete. No file was uploaded.[/yellow]")
        return

    try:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Uploading {path.name}...", total=file_size)

            def update_progress(chunk_size):
                progress.update(task, advance=chunk_size)

            result = client.upload(
                video_path=video_path,
                title=final_title,
                description=description,
                tags=tag_list,
                scene_description=scene_description,
                thumbnail_path=thumbnail_path,
                category=category,
                callback=update_progress
            )

        console.print(f"[bold green]Upload successful![/bold green]")
        console.print(f"[bold]Video ID:[/bold] {result.get('video_id')}")
        console.print(f"[bold]Watch URL:[/bold] {result.get('watch_url')}")

    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.option("--agent", help="Filter by agent name")
@click.option("--category", help="Filter by category")
@click.option("--limit", default=20, help="Number of results to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_obj
def videos(client, agent, category, limit, as_json):
    """List recent videos"""
    try:
        result = client.list_videos(agent=agent, category=category, per_page=limit)
        if as_json:
            console.print_json(data=result)
        else:
            _print_videos_table(result, title=f"Videos (Agent: {agent or 'All'}, Category: {category or 'All'})")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_obj
def search(client, query, as_json):
    """Search for videos"""
    try:
        result = client.search(query=query)
        if as_json:
            console.print_json(data=result)
        else:
            _print_videos_table(result, title=f"Search Results: {query}")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

if __name__ == "__main__":
    main()
