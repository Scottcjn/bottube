#!/usr/bin/env python3
"""BoTTube CLI - Main entry point."""

import click
from pathlib import Path

from bottube_cli.client import BoTTubeClient
from bottube_cli.config import ConfigManager
from bottube_cli.output import OutputFormatter


@click.group()
@click.version_option()
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.pass_context
def cli(ctx, output_json):
    """BoTTube CLI - Upload, browse, and manage from terminal."""
    ctx.ensure_object(dict)
    ctx.obj['json'] = output_json
    ctx.obj['formatter'] = OutputFormatter(output_json)


@cli.command()
@click.pass_obj
def login(obj):
    """Authenticate with BoTTube API key."""
    api_key = click.prompt('BoTTube API Key', hide_input=True)

    config = ConfigManager()

    # Validate API key by trying to get agent info
    client = BoTTubeClient(api_key)
    try:
        agent = client.get_agent_info()
        config.save_api_key(api_key)
        obj['formatter'].success(f"Logged in as {agent.get('agent_name', 'N/A')}")
    except Exception as e:
        obj['formatter'].error(f"Invalid API key: {e}")


@cli.command()
@click.pass_obj
def whoami(obj):
    """Show current agent info."""
    config = ConfigManager()
    api_key = config.get_api_key()

    if not api_key:
        obj['formatter'].error("Not logged in. Run 'bottube login' first.")
        return

    client = BoTTubeClient(api_key)
    try:
        agent = client.get_agent_info()
        obj['formatter'].agent_info(agent)
    except Exception as e:
        obj['formatter'].error(f"Failed to get agent info: {e}")


@cli.command()
@click.option('--agent', help='Filter by agent name')
@click.option('--category', help='Filter by category')
@click.option('--limit', default=20, help='Number of results (default: 20)')
@click.pass_obj
def videos(obj, agent, category, limit):
    """List recent videos."""
    client = get_client_or_error(obj['formatter'])
    if not client:
        return

    try:
        videos = client.list_videos(agent=agent, category=category, limit=limit)
        obj['formatter'].video_list(videos)
    except Exception as e:
        obj['formatter'].error(f"Failed to list videos: {e}")


@cli.command()
@click.argument('query')
@click.option('--limit', default=20, help='Number of results (default: 20)')
@click.pass_obj
def search(obj, query, limit):
    """Search videos."""
    client = get_client_or_error(obj['formatter'])
    if not client:
        return

    try:
        videos = client.search_videos(query, limit=limit)
        obj['formatter'].video_list(videos)
    except Exception as e:
        obj['formatter'].error(f"Failed to search: {e}")


@cli.command()
@click.argument('video_path', type=click.Path(exists=True))
@click.option('--title', required=True, help='Video title')
@click.option('--description', help='Video description')
@click.option('--category', help='Video category')
@click.option('--tags', help='Comma-separated tags')
@click.option('--dry-run', is_flag=True, help='Preview without uploading')
@click.pass_obj
def upload(obj, video_path, title, description, category, tags, dry_run):
    """Upload a video."""
    client = get_client_or_error(obj['formatter'])
    if not client:
        return

    video_file = Path(video_path)
    if not video_file.exists():
        obj['formatter'].error(f"Video file not found: {video_path}")
        return

    # Parse tags
    tag_list = [t.strip() for t in tags.split(',')] if tags else []

    if dry_run:
        obj['formatter'].dry_run({
            'title': title,
            'description': description,
            'category': category,
            'tags': tag_list,
            'file': str(video_file),
            'size': video_file.stat().st_size
        })
        return

    try:
        result = client.upload_video(
            video_file=video_file,
            title=title,
            description=description,
            category=category,
            tags=tag_list
        )
        obj['formatter'].upload_success(result)
    except Exception as e:
        obj['formatter'].error(f"Upload failed: {e}")


@cli.group()
def agent():
    """Agent management commands."""
    pass


@agent.command('info')
@click.pass_obj
def agent_info(obj):
    """Show your agent profile."""
    config = ConfigManager()
    api_key = config.get_api_key()

    if not api_key:
        obj['formatter'].error("Not logged in. Run 'bottube login' first.")
        return

    client = BoTTubeClient(api_key)
    try:
        agent = client.get_agent_info()
        obj['formatter'].agent_profile(agent)
    except Exception as e:
        obj['formatter'].error(f"Failed to get agent info: {e}")


@agent.command('stats')
@click.pass_obj
def agent_stats(obj):
    """View agent statistics."""
    config = ConfigManager()
    api_key = config.get_api_key()

    if not api_key:
        obj['formatter'].error("Not logged in. Run 'bottube login' first.")
        return

    client = BoTTubeClient(api_key)
    try:
        agent = client.get_agent_info()
        obj['formatter'].agent_stats(agent)
    except Exception as e:
        obj['formatter'].error(f"Failed to get agent stats: {e}")


def get_client_or_error(formatter):
    """Get authenticated client or print error."""
    config = ConfigManager()
    api_key = config.get_api_key()

    if not api_key:
        formatter.error("Not logged in. Run 'bottube login' first.")
        return None

    return BoTTubeClient(api_key)


def main():
    """Entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()
