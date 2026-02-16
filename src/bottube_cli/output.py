"""Output formatting for CLI."""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class OutputFormatter:
    """Format and print CLI output."""

    def __init__(self, json_output: bool = False):
        """Initialize formatter."""
        self.json_output = json_output
        self.console = Console() if RICH_AVAILABLE else None

    def _print(self, message: str, color: Optional[str] = None) -> None:
        """Print message with optional color."""
        if self.json_output:
            return

        if self.console:
            if color:
                self.console.print(message, style=color)
            else:
                self.console.print(message)
        else:
            print(message)

    def error(self, message: str) -> None:
        """Print error message."""
        if self.json_output:
            print(json.dumps({"error": message}, indent=2))
        else:
            if self.console:
                self.console.print(f"❌ {message}", style="red")
            else:
                print(f"ERROR: {message}")

    def success(self, message: str) -> None:
        """Print success message."""
        if self.json_output:
            print(json.dumps({"success": message}, indent=2))
        else:
            if self.console:
                self.console.print(f"✅ {message}", style="green")
            else:
                print(f"SUCCESS: {message}")

    def agent_info(self, agent: Dict[str, Any]) -> None:
        """Print agent information."""
        if self.json_output:
            print(json.dumps(agent, indent=2))
            return

        if self.console:
            panel = Panel(
                f"[bold]Agent:[/bold] {agent.get('agent_name', 'N/A')}\n"
                f"[bold]Display:[/bold] {agent.get('display_name', 'N/A')}\n"
                f"[bold]ID:[/bold] {agent.get('id', 'N/A')}",
                title="Current Agent",
                border_style="blue"
            )
            self.console.print(panel)
        else:
            print(f"Agent: {agent.get('agent_name', 'N/A')}")
            print(f"Display: {agent.get('display_name', 'N/A')}")
            print(f"ID: {agent.get('id', 'N/A')}")

    def agent_profile(self, agent: Dict[str, Any]) -> None:
        """Print detailed agent profile."""
        if self.json_output:
            print(json.dumps(agent, indent=2))
            return

        if self.console:
            table = Table(title="Agent Profile")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            for key, value in agent.items():
                table.add_row(key, str(value))

            self.console.print(table)
        else:
            for key, value in agent.items():
                print(f"{key}: {value}")

    def agent_stats(self, agent: Dict[str, Any]) -> None:
        """Print agent statistics."""
        if self.json_output:
            stats = {
                'agent_name': agent.get('agent_name'),
                'display_name': agent.get('display_name'),
                'stats': agent
            }
            print(json.dumps(stats, indent=2))
            return

        if self.console:
            panel = Panel(
                f"[bold]Videos:[/bold] {agent.get('video_count', 'N/A')}\n"
                f"[bold]Subscribers:[/bold] {agent.get('subscriber_count', 'N/A')}\n"
                f"[bold]Created:[/bold] {self._format_date(agent.get('created_at'))}",
                title=f"Stats - {agent.get('display_name', 'N/A')}",
                border_style="cyan"
            )
            self.console.print(panel)
        else:
            print(f"Videos: {agent.get('video_count', 'N/A')}")
            print(f"Subscribers: {agent.get('subscriber_count', 'N/A')}")
            print(f"Created: {self._format_date(agent.get('created_at'))}")

    def video_list(self, videos: List[Dict[str, Any]]) -> None:
        """Print list of videos."""
        if self.json_output:
            print(json.dumps(videos, indent=2))
            return

        if not videos:
            self._print("No videos found.", "yellow")
            return

        if self.console:
            table = Table(title="Videos")
            table.add_column("ID", style="dim")
            table.add_column("Title")
            table.add_column("Agent")
            table.add_column("Duration")

            for video in videos:
                video_id = video.get('video_id', 'N/A')[:8] + '...'
                table.add_row(
                    video_id,
                    video.get('title', 'N/A')[:40],
                    video.get('agent', 'N/A'),
                    str(video.get('duration_sec', 0))
                )

            self.console.print(table)
        else:
            for i, video in enumerate(videos, 1):
                print(f"{i}. {video.get('title', 'N/A')}")

    def upload_success(self, result: Dict[str, Any]) -> None:
        """Print successful upload result."""
        if self.json_output:
            print(json.dumps(result, indent=2))
            return

        video_url = f"https://bottube.ai{result.get('watch_url', '')}"
        self.success(f"Video uploaded successfully!")
        self._print(f"Watch URL: {video_url}", "cyan")
        self._print(f"Video ID: {result.get('video_id', 'N/A')}")

    def dry_run(self, data: Dict[str, Any]) -> None:
        """Print dry-run preview."""
        if self.json_output:
            print(json.dumps({"dry_run": True, "preview": data}, indent=2))
            return

        if self.console:
            panel = Panel(
                self._format_dry_run(data),
                title="Dry Run Preview",
                border_style="yellow"
            )
            self.console.print(panel)
        else:
            print("=== Dry Run Preview ===")
            print(self._format_dry_run(data))

    def _format_date(self, date_str: Optional[str]) -> str:
        """Format date string."""
        if not date_str:
            return "N/A"

        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return date_str

    def _format_dry_run(self, data: Dict[str, Any]) -> str:
        """Format dry-run data."""
        lines = []
        lines.append(f"[bold]Title:[/bold] {data.get('title', 'N/A')}")
        lines.append(f"[bold]File:[/bold] {data.get('file', 'N/A')}")
        lines.append(f"[bold]Size:[/bold] {data.get('size', 0)} bytes")

        if data.get('description'):
            lines.append(f"[bold]Description:[/bold] {data['description']}")
        if data.get('category'):
            lines.append(f"[bold]Category:[/bold] {data['category']}")
        if data.get('tags'):
            lines.append(f"[bold]Tags:[/bold] {', '.join(data['tags'])}")

        return '\n'.join(lines)
