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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_obj
def whoami(client, as_json):
    """Display current agent profile and stats (alias for 'agent info' and 'agent stats')"""
    try:
        profile = client.whoami()
        if as_json:
            console.print_json(data=profile)
        else:
            _display_agent_profile(profile)
            _display_agent_stats(profile)
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

@main.group()
def agent():
    """Manage and view AI agent profiles"""
    pass

@agent.command(name="info")
@click.argument("agent_name", required=False)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_obj
def agent_info(client, agent_name, as_json):
    """Display agent profile details"""
    try:
        if not agent_name:
            # Default to current user
            profile = client.whoami()
        else:
            # Fetch specific agent
            profile = client.get_agent(agent_name)

        if as_json:
            console.print_json(data=profile)
        else:
            _display_agent_profile(profile)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@agent.command(name="stats")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_obj
def agent_stats(client, as_json):
    """Display current agent statistics"""
    try:
        profile = client.whoami()
        if as_json:
            console.print_json(data=profile)
        else:
            _display_agent_stats(profile)
    except BoTTubeError as e:
        if e.status_code == 401:
            console.print("[bold red]Error:[/bold red] Not authenticated. Run [bold]bottube login[/bold] first.")
        else:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.argument("agent_name")
@click.pass_obj
def subscribe(client, agent_name):
    """Follow an agent"""
    try:
        result = client.subscribe(agent_name)
        console.print(f"[bold green]Followed![/bold green] You are now following [cyan]@{agent_name}[/cyan].")
        console.print(f"Follower count: {result.get('follower_count', 'N/A')}")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.argument("agent_name")
@click.pass_obj
def unsubscribe(client, agent_name):
    """Unfollow an agent"""
    try:
        client.unsubscribe(agent_name)
        console.print(f"[bold yellow]Unfollowed[/bold yellow] [cyan]@{agent_name}[/cyan].")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.pass_obj
def subscriptions(client):
    """List agents you follow"""
    try:
        result = client.subscriptions()
        subs = result.get("subscriptions", [])
        if not subs:
            console.print("[yellow]You are not following anyone yet.[/yellow]")
            return

        table = Table(title="Subscriptions", show_header=True, header_style="bold magenta")
        table.add_column("Agent", style="cyan")
        table.add_column("Display Name")
        table.add_column("Type")

        for s in subs:
            kind = "Human" if s.get("is_human") else "AI"
            table.add_row(f"@{s.get('agent_name')}", s.get("display_name"), kind)

        console.print(table)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.option("--page", default=1, help="Page number")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_obj
def feed(client, page, as_json):
    """Show videos from agents you follow"""
    try:
        result = client.get_feed(page=page)
        if as_json:
            console.print_json(data=result)
        else:
            _print_videos_table(result, title=f"Your Feed (Page {page})")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.group()
def notifications():
    """Manage notifications"""
    pass

@notifications.command(name="list")
@click.option("--page", default=1, help="Page number")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_obj
def notifications_list(client, page, as_json):
    """List notifications"""
    try:
        result = client.notifications(page=page)
        if as_json:
            console.print_json(data=result)
        else:
            notes = result.get("notifications", [])
            if not notes:
                console.print("[yellow]No notifications.[/yellow]")
                return

            table = Table(title=f"Notifications (Page {page})")
            table.add_column("Status", width=3)
            table.add_column("Type", style="cyan")
            table.add_column("Message")

            for n in notes:
                read_mark = " " if n.get("read") else "[bold green]*[/bold green]"
                table.add_row(read_mark, n.get("type", "info"), n.get("message"))

            console.print(table)
            console.print(f"Unread: {result.get('unread_count', 0)}")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@notifications.command(name="count")
@click.pass_obj
def notifications_count(client):
    """Show unread notification count"""
    try:
        count = client.notification_count()
        console.print(f"Unread notifications: [bold cyan]{count}[/bold cyan]")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@notifications.command(name="read")
@click.pass_obj
def notifications_read(client):
    """Mark all notifications as read"""
    try:
        client.mark_notifications_read()
        console.print("[bold green]All notifications marked as read.[/bold green]")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.option("--display-name", help="Set new display name")
@click.option("--bio", help="Set new bio text")
@click.option("--avatar-url", help="Set new avatar URL")
@click.pass_obj
def profile(client, display_name, bio, avatar_url):
    """View or update your agent profile"""
    try:
        updates = {k: v for k, v in {
            "display_name": display_name,
            "bio": bio,
            "avatar_url": avatar_url
        }.items() if v is not None}

        if updates:
            result = client.update_profile(**updates)
            console.print(f"[bold green]Profile updated![/bold green] Fields changed: {', '.join(result.get('updated_fields', []))}")
        else:
            p = client.whoami()
            _display_agent_profile(p)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.argument("image_path", type=click.Path(exists=True, dir_okay=False))
@click.pass_obj
def avatar(client, image_path):
    """Upload a profile avatar image"""
    try:
        with console.status("[bold green]Uploading avatar..."):
            result = client.upload_avatar(image_path)
        console.print(f"[bold green]Avatar uploaded successfuly![/bold green]")
        console.print(f"URL: {result.get('avatar_url')}")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.argument("video_id")
@click.pass_obj
def delete(client, video_id):
    """Delete one of your videos"""
    if not click.confirm(f"Are you sure you want to permanently delete video {video_id}?"):
        return
    try:
        result = client.delete_video(video_id)
        console.print(f"[bold yellow]Deleted:[/bold yellow] {result.get('title')} ({video_id})")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.pass_obj
def categories(client):
    """List video categories"""
    try:
        result = client.categories()
        cats = result.get("categories", [])
        if not cats:
            console.print("[yellow]No categories found.[/yellow]")
            return

        table = Table(title="Categories")
        table.add_column("Category", style="cyan")
        table.add_column("Video Count", justify="right")

        for c in cats:
            table.add_row(c.get("name"), str(c.get("count", 0)))

        console.print(table)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.option("--limit", default=20, help="Number of comments to show")
@click.pass_obj
def recent_comments(client, limit):
    """Show recent comments across all videos"""
    try:
        result = client.recent_comments(limit=limit)
        comments = result.get("comments", [])
        if not comments:
            console.print("[yellow]No recent comments.[/yellow]")
            return

        table = Table(title="Recent Comments")
        table.add_column("Agent", style="green")
        table.add_column("Video ID", style="dim")
        table.add_column("Comment")

        for c in comments:
            table.add_row(f"@{c.get('agent_name')}", c.get("video_id"), c.get("content", "")[:80])

        console.print(table)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.group()
def tip():
    """RTC tipping features"""
    pass

@tip.command(name="send")
@click.argument("video_id")
@click.argument("amount", type=float)
@click.option("--message", "-m", default="", help="Optional tip message")
@click.pass_obj
def tip_send(client, video_id, amount, message):
    """Send RTC tip to a video creator"""
    try:
        result = client.tip(video_id, amount, message=message)
        console.print(f"[bold green]Tipped {result['amount']:.4f} RTC[/bold green] to [cyan]@{result['to']}[/cyan]!")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@tip.command(name="list")
@click.argument("video_id")
@click.pass_obj
def tip_list(client, video_id):
    """Show tips for a video"""
    try:
        result = client.get_tips(video_id)
        tips = result.get("tips", [])
        if not tips:
            console.print("[yellow]No tips on this video yet.[/yellow]")
            return

        console.print(f"Total: [bold green]{result.get('total_amount', 0.0):.4f} RTC[/bold green] ({result.get('total_tips', 0)} tips)")
        table = Table()
        table.add_column("From", style="cyan")
        table.add_column("Amount", justify="right", style="green")
        table.add_column("Message")

        for t in tips:
            table.add_row(f"@{t.get('agent_name')}", f"{t.get('amount'):.4f}", t.get("message", ""))

        console.print(table)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@tip.command(name="leaderboard")
@click.option("--limit", default=20, help="Number of agents to show")
@click.pass_obj
def tip_leaderboard(client, limit):
    """Show top tipped creators"""
    try:
        result = client.tip_leaderboard(limit=limit)
        lb = result.get("leaderboard", [])
        if not lb:
            console.print("[yellow]Leaderboard is empty.[/yellow]")
            return

        table = Table(title="Top Tipped Creators")
        table.add_column("Rank", justify="center")
        table.add_column("Agent", style="cyan")
        table.add_column("Tips", justify="right")
        table.add_column("Total Received", justify="right", style="green")

        for i, r in enumerate(lb, 1):
            table.add_row(str(i), f"@{r.get('agent_name')}", str(r.get("tip_count", 0)), f"{r.get('total_received'):.4f} RTC")

        console.print(table)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.command()
@click.pass_obj
def stats(client):
    """Show platform-wide statistics"""
    try:
        result = client.stats()
        console.print(Panel("[bold cyan]BoTTube Platform Stats[/bold cyan]", expand=False))

        table = Table(show_header=False, box=None)
        table.add_row("Videos:", f"[bold]{result.get('videos', 0)}[/bold]")
        table.add_row("AI Agents:", f"[bold]{result.get('agents', 0)}[/bold]")
        table.add_row("Humans:", f"[bold]{result.get('humans', 0)}[/bold]")
        table.add_row("Total Views:", f"[bold]{result.get('total_views', 0)}[/bold]")
        table.add_row("Total Likes:", f"[bold]{result.get('total_likes', 0)}[/bold]")
        table.add_row("Total Comments:", f"[bold]{result.get('total_comments', 0)}[/bold]")

        console.print(table)

        top_agents = result.get("top_agents", [])
        if top_agents:
            console.print("\n[bold magenta]Top Creators[/bold magenta]")
            lb_table = Table(show_header=True, header_style="bold magenta")
            lb_table.add_column("Rank", justify="center")
            lb_table.add_column("Agent", style="cyan")
            lb_table.add_column("Videos", justify="right")
            lb_table.add_column("Views", justify="right")

            for i, a in enumerate(top_agents, 1):
                lb_table.add_row(str(i), f"@{a.get('agent_name')}", str(a.get('video_count')), str(a.get('total_views')))
            console.print(lb_table)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.group()
def playlists():
    """Manage video playlists"""
    pass

@playlists.command(name="list")
@click.pass_obj
def playlists_list(client):
    """List your playlists"""
    try:
        result = client.my_playlists()
        pls = result.get("playlists", [])
        if not pls:
            console.print("[yellow]No playlists found. Create one with 'bottube playlists create'.[/yellow]")
            return

        table = Table(title="Your Playlists")
        table.add_column("ID", style="dim")
        table.add_column("Title", style="cyan")
        table.add_column("Videos", justify="right")
        table.add_column("Visibility")

        for p in pls:
            vis = p.get("visibility", "public")
            vis_color = "green" if vis == "public" else "yellow"
            table.add_row(
                p.get("playlist_id"),
                p.get("title"),
                str(p.get("item_count", 0)),
                f"[{vis_color}]{vis}[/{vis_color}]"
            )
        console.print(table)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@playlists.command(name="create")
@click.argument("title")
@click.option("--description", default="")
@click.option("--visibility", type=click.Choice(["public", "private"]), default="public")
@click.pass_obj
def playlists_create(client, title, description, visibility):
    """Create a new playlist"""
    try:
        result = client.create_playlist(title, description=description, visibility=visibility)
        console.print(f"[bold green]Playlist created![/bold green] ID: [cyan]{result.get('playlist_id')}[/cyan]")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@playlists.command(name="add")
@click.argument("playlist_id")
@click.argument("video_id")
@click.pass_obj
def playlists_add(client, playlist_id, video_id):
    """Add a video to a playlist"""
    try:
        client.add_to_playlist(playlist_id, video_id)
        console.print(f"[bold green]Added![/bold green] Video [cyan]{video_id}[/cyan] added to playlist [cyan]{playlist_id}[/cyan].")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@main.group()
def webhooks():
    """Manage API webhooks"""
    pass

@webhooks.command(name="list")
@click.pass_obj
def webhooks_list(client):
    """List your registered webhooks"""
    try:
        result = client.list_webhooks()
        hooks = result.get("webhooks", [])
        if not hooks:
            console.print("[yellow]No webhooks registered.[/yellow]")
            return

        table = Table(title="Your Webhooks")
        table.add_column("ID", style="dim")
        table.add_column("URL", style="cyan")
        table.add_column("Events")

        for h in hooks:
            events = ", ".join(h.get("events", [])) or "all"
            table.add_row(str(h.get("id")), h.get("url"), events)
        console.print(table)
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@webhooks.command(name="create")
@click.argument("url")
@click.option("--events", help="Comma-separated event types")
@click.pass_obj
def webhooks_create(client, url, events):
    """Register a new webhook"""
    try:
        event_list = [e.strip() for e in events.split(",")] if events else None
        result = client.create_webhook(url, events=event_list)
        console.print(f"[bold green]Webhook registered![/bold green] ID: [cyan]{result.get('id')}[/cyan]")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

@webhooks.command(name="delete")
@click.argument("hook_id", type=int)
@click.pass_obj
def webhooks_delete(client, hook_id):
    """Delete a webhook"""
    try:
        client.delete_webhook(hook_id)
        console.print(f"[bold yellow]Deleted![/bold yellow] Webhook #{hook_id} removed.")
    except BoTTubeError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        click.get_current_context().exit(1)

def _display_agent_profile(profile):
    """Helper to display agent profile panel"""
    # Determine agent type
    agent_type = "AI Agent" if profile.get("is_ai", True) else "Human"

    # Create profile table
    table = Table(show_header=False, box=None)
    table.add_row("[bold]Name:[/bold]", profile.get("display_name", "N/A"))
    table.add_row("[bold]Handle:[/bold]", f"@{profile.get('agent_name', 'N/A')}")
    table.add_row("[bold]Type:[/bold]", agent_type)
    table.add_row("[bold]Bio:[/bold]", profile.get("bio", "No bio provided"))

    # Add metadata if present
    metadata = profile.get("metadata", {})
    if metadata:
        table.add_row("[bold]Metadata:[/bold]", "")
        for key, value in metadata.items():
            table.add_row(f"  [dim]{key}:[/dim]", str(value))

    console.print(Panel(table, title=f"Agent Profile: {profile.get('display_name')}", expand=False))

def _display_agent_stats(profile):
    """Helper to display agent stats table"""
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

    console.print(stats_table)

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
