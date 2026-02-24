#!/usr/bin/env python3
import argparse
import json
import requests

API_BASE = "https://bottube.ai"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--thumbnail", default="")
    args = ap.parse_args()

    files = {"video": open(args.video, "rb")}
    data = {
        "title": args.title,
        "description": args.description,
        "tags": json.dumps([t.strip() for t in args.tags.split(',') if t.strip()]),
    }
    if args.thumbnail:
        files["thumbnail"] = open(args.thumbnail, "rb")

    r = requests.post(
        f"{API_BASE}/api/upload",
        headers={"X-API-Key": args.api_key},
        data=data,
        files=files,
        timeout=120,
    )
    print(r.status_code)
    print(r.text)

if __name__ == "__main__":
    main()
