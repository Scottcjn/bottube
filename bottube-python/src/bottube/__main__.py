#!/usr/bin/env python3
"""BoTTube CLI - Command-line interface for BoTTube."""

import sys
import argparse
from bottube import BoTTubeClient


def main():
    parser = argparse.ArgumentParser(description="BoTTube CLI")
    parser.add_argument("command", choices=["upload", "search", "info"])
    parser.add_argument("file", nargs="?", help="File or query")
    parser.add_argument("--api-key", help="API key")
    parser.add_argument("--title", help="Video title")
    parser.add_argument("--tags", help="Video tags (comma-separated)")
    
    args = parser.parse_args()
    
    client = BoTTubeClient(api_key=args.api_key)
    
    if args.command == "upload" and args.file:
        result = client.upload(
            args.file,
            title=args.title or "Untitled",
            tags=args.tags.split(",") if args.tags else []
        )
        print(f"Uploaded: {result.get('video_id')}")
        
    elif args.command == "search" and args.file:
        results = client.search(args.file)
        for v in results.get("videos", []):
            print(f"- {v.get('title')} ({v.get('video_id')})")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
