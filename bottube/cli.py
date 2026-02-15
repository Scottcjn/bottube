"""BoTTube CLI — command-line interface for the BoTTube Video Platform."""

import click
import json
import os
from rich.console import Console

from bottube.client import BoTTubeClient, DEFAULT_BASE_URL
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

if __name__ == "__main__":
    main()
