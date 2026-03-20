#!/usr/bin/env python3

import sys
import argparse
import json
from bottube_server import get_db
from beacon_discord import DiscordBeacon, DiscordTransportError


def create_parser():
    parser = argparse.ArgumentParser(prog='beacon', description='Beacon transport CLI')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Discord subcommand
    discord_parser = subparsers.add_parser('discord', help='Discord transport commands')
    discord_subparsers = discord_parser.add_subparsers(dest='action', help='Discord actions')

    # Discord ping
    ping_parser = discord_subparsers.add_parser('ping', help='Test Discord webhook connection')
    ping_parser.add_argument('--webhook-url', required=True, help='Discord webhook URL')
    ping_parser.add_argument('--retries', type=int, default=3, help='Number of retry attempts')
    ping_parser.add_argument('--timeout', type=int, default=10, help='Request timeout in seconds')

    # Discord send
    send_parser = discord_subparsers.add_parser('send', help='Send message via Discord webhook')
    send_parser.add_argument('--webhook-url', required=True, help='Discord webhook URL')
    send_parser.add_argument('--message', required=True, help='Message content to send')
    send_parser.add_argument('--username', help='Override webhook username')
    send_parser.add_argument('--avatar-url', help='Override webhook avatar URL')
    send_parser.add_argument('--dry-run', action='store_true', help='Validate payload without sending')
    send_parser.add_argument('--retries', type=int, default=3, help='Number of retry attempts')
    send_parser.add_argument('--timeout', type=int, default=10, help='Request timeout in seconds')

    return parser


def handle_discord_ping(args):
    try:
        beacon = DiscordBeacon(
            webhook_url=args.webhook_url,
            max_retries=args.retries,
            timeout=args.timeout
        )

        print(f"Testing Discord webhook connection...")
        result = beacon.ping()

        if result.get('success'):
            print("✓ Discord webhook ping successful")
            if 'response_time' in result:
                print(f"  Response time: {result['response_time']:.2f}s")
            return 0
        else:
            print(f"✗ Discord webhook ping failed: {result.get('error', 'Unknown error')}")
            return 1

    except DiscordTransportError as e:
        print(f"✗ Discord transport error: {e}")
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return 1


def handle_discord_send(args):
    try:
        beacon = DiscordBeacon(
            webhook_url=args.webhook_url,
            max_retries=args.retries,
            timeout=args.timeout
        )

        payload = {
            'content': args.message
        }

        if args.username:
            payload['username'] = args.username
        if args.avatar_url:
            payload['avatar_url'] = args.avatar_url

        if args.dry_run:
            print("Dry run mode - payload validation:")
            print(json.dumps(payload, indent=2))
            is_valid = beacon.validate_payload(payload)
            if is_valid:
                print("✓ Payload is valid")
                return 0
            else:
                print("✗ Payload validation failed")
                return 1

        print(f"Sending message to Discord...")
        result = beacon.send_message(payload)

        if result.get('success'):
            print("✓ Message sent successfully")
            if 'message_id' in result:
                print(f"  Message ID: {result['message_id']}")
            return 0
        else:
            print(f"✗ Failed to send message: {result.get('error', 'Unknown error')}")
            if 'retry_count' in result:
                print(f"  Retries attempted: {result['retry_count']}")
            return 1

    except DiscordTransportError as e:
        print(f"✗ Discord transport error: {e}")
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return 1


def main():
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'discord':
        if not args.action:
            parser.parse_args(['discord', '--help'])
            return 1

        if args.action == 'ping':
            return handle_discord_ping(args)
        elif args.action == 'send':
            return handle_discord_send(args)
        else:
            print(f"Unknown discord action: {args.action}")
            return 1
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
