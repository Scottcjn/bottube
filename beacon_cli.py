#!/usr/bin/env python3

import argparse
import sys
import json
import time
from typing import Optional

from beacon_discord_transport import DiscordTransport


class BeaconCLI:
    def __init__(self):
        self.discord = None

    def setup_discord(self, webhook_url: str) -> bool:
        """Initialize Discord transport with webhook URL"""
        try:
            self.discord = DiscordTransport(webhook_url)
            return True
        except Exception as e:
            print(f"Error: Failed to initialize Discord transport: {e}")
            return False

    def ping_discord(self, webhook_url: str, retries: int = 3) -> int:
        """Test Discord webhook connectivity"""
        if not self.setup_discord(webhook_url):
            return 1

        print("Pinging Discord webhook...")

        for attempt in range(retries + 1):
            try:
                result = self.discord.ping()
                if result.get('success'):
                    print("✓ Discord webhook ping successful")
                    return 0
                else:
                    error_msg = result.get('error', 'Unknown error')
                    if attempt < retries:
                        print(f"⚠ Attempt {attempt + 1}/{retries + 1} failed: {error_msg}")
                        print("  Retrying in 2 seconds...")
                        time.sleep(2)
                    else:
                        print(f"✗ Discord webhook ping failed: {error_msg}")
                        return 1
            except Exception as e:
                if attempt < retries:
                    print(f"⚠ Attempt {attempt + 1}/{retries + 1} failed: {e}")
                    print("  Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    print(f"✗ Discord webhook ping failed: {e}")
                    return 1

        return 1

    def send_discord(self, webhook_url: str, message: str,
                    username: Optional[str] = None, retries: int = 3) -> int:
        """Send message via Discord webhook"""
        if not self.setup_discord(webhook_url):
            return 1

        print(f"Sending message to Discord: '{message}'")

        payload = {'content': message}
        if username:
            payload['username'] = username

        for attempt in range(retries + 1):
            try:
                result = self.discord.send_message(payload)
                if result.get('success'):
                    print("✓ Message sent successfully")
                    return 0
                else:
                    error_msg = result.get('error', 'Unknown error')
                    status_code = result.get('status_code')

                    if status_code == 429:  # Rate limited
                        retry_after = result.get('retry_after', 5)
                        if attempt < retries:
                            print(f"⚠ Rate limited, waiting {retry_after} seconds...")
                            time.sleep(retry_after)
                            continue

                    if attempt < retries:
                        print(f"⚠ Attempt {attempt + 1}/{retries + 1} failed: {error_msg}")
                        print("  Retrying in 3 seconds...")
                        time.sleep(3)
                    else:
                        print(f"✗ Failed to send message: {error_msg}")
                        return 1

            except Exception as e:
                if attempt < retries:
                    print(f"⚠ Attempt {attempt + 1}/{retries + 1} failed: {e}")
                    print("  Retrying in 3 seconds...")
                    time.sleep(3)
                else:
                    print(f"✗ Failed to send message: {e}")
                    return 1

        return 1

    def listen_discord(self, webhook_url: str, interval: int = 30,
                      duration: Optional[int] = None) -> int:
        """Listen for Discord transport events (lightweight polling mode)"""
        if not self.setup_discord(webhook_url):
            return 1

        print(f"Starting Discord listener (polling every {interval}s)")
        if duration:
            print(f"Will run for {duration} seconds")
        print("Press Ctrl+C to stop...")

        start_time = time.time()
        check_count = 0

        try:
            while True:
                check_count += 1
                current_time = time.time()

                # Check if duration limit reached
                if duration and (current_time - start_time) >= duration:
                    print(f"\n✓ Listener completed after {duration} seconds")
                    break

                print(f"[{time.strftime('%H:%M:%S')}] Check #{check_count} - Polling transport status...")

                try:
                    # Lightweight status check
                    result = self.discord.get_status()
                    if result.get('success'):
                        status = result.get('status', 'unknown')
                        print(f"  Status: {status}")

                        # Check for any pending events or notifications
                        events = result.get('events', [])
                        if events:
                            print(f"  Found {len(events)} events:")
                            for event in events:
                                event_type = event.get('type', 'unknown')
                                timestamp = event.get('timestamp', '')
                                print(f"    - {event_type} at {timestamp}")
                        else:
                            print("  No new events")
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        print(f"  ⚠ Status check failed: {error_msg}")

                except Exception as e:
                    print(f"  ⚠ Error during status check: {e}")

                # Wait for next poll
                time.sleep(interval)

        except KeyboardInterrupt:
            print(f"\n✓ Listener stopped by user after {check_count} checks")
            return 0
        except Exception as e:
            print(f"\n✗ Listener failed: {e}")
            return 1

        return 0


def main():
    parser = argparse.ArgumentParser(description='Beacon CLI - Discord Transport Interface')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Discord subcommand group
    discord_parser = subparsers.add_parser('discord', help='Discord transport commands')
    discord_subparsers = discord_parser.add_subparsers(dest='discord_command',
                                                       help='Discord operations')

    # Discord ping command
    ping_parser = discord_subparsers.add_parser('ping', help='Test Discord webhook connectivity')
    ping_parser.add_argument('webhook_url', help='Discord webhook URL')
    ping_parser.add_argument('--retries', type=int, default=3,
                           help='Number of retry attempts (default: 3)')

    # Discord send command
    send_parser = discord_subparsers.add_parser('send', help='Send message via Discord webhook')
    send_parser.add_argument('webhook_url', help='Discord webhook URL')
    send_parser.add_argument('message', help='Message to send')
    send_parser.add_argument('--username', help='Custom username for the message')
    send_parser.add_argument('--retries', type=int, default=3,
                           help='Number of retry attempts (default: 3)')

    # Discord listen command
    listen_parser = discord_subparsers.add_parser('listen',
                                                 help='Listen for Discord transport events')
    listen_parser.add_argument('webhook_url', help='Discord webhook URL')
    listen_parser.add_argument('--interval', type=int, default=30,
                             help='Polling interval in seconds (default: 30)')
    listen_parser.add_argument('--duration', type=int,
                             help='Maximum duration in seconds (default: unlimited)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'discord':
        if not args.discord_command:
            discord_parser.print_help()
            return 1

        cli = BeaconCLI()

        if args.discord_command == 'ping':
            return cli.ping_discord(args.webhook_url, args.retries)

        elif args.discord_command == 'send':
            return cli.send_discord(args.webhook_url, args.message,
                                  args.username, args.retries)

        elif args.discord_command == 'listen':
            return cli.listen_discord(args.webhook_url, args.interval, args.duration)

    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
