"""Restricted queue gateway for the unprivileged Emu Radar service.

The root-owned launcher may be allowed through sudo; never allow a general Python command.
"""
import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

PLATFORMS = {"Switch", "PSVita", "PS1"}


def web_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Invalid release URL")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in {None, 443}:
        raise ValueError("Expected a public HTTPS release URL")
    return value


def validated_rows(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError("Expected 1–20 release rows")
    clean = []
    for row in rows:
        if not isinstance(row, dict) or row.get("platform") not in PLATFORMS:
            raise ValueError("Invalid release platform")
        out = {"type": "homebrew", "platform": row["platform"], "is_new": True, "processed": False,
               "inbox_id": uuid.uuid4().hex, "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        for key, maximum in [("app_name", 200), ("version", 100), ("description", 220)]:
            value = row.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"Invalid {key}")
            out[key] = value.strip()
        out["release_url"] = web_url(row.get("release_url"))
        if row.get("download_url"):
            out["download_url"] = web_url(row["download_url"])
        date = row.get("date")
        if not isinstance(date, str) or len(date) > 64:
            raise ValueError("Invalid release date")
        datetime.fromisoformat(date.replace("Z", "+00:00"))
        out["date"] = date
        clean.append(out)
    return clean


def queue_rows(rows):
    rows = validated_rows(rows)
    import add_release as ar
    gist_id, token, _ = ar.sgs.resolve_gist_credentials()
    if not gist_id or not token:
        raise ValueError("Bot Gist credentials are missing")
    manual, inbox = ar.read_gist(gist_id, token)
    taken = {(r.get("release_url"), r.get("version")) for r in manual + inbox}
    new = []
    for row in rows:
        key = (row["release_url"], row["version"])
        if key not in taken:
            new.append(row)
            taken.add(key)
    if new:
        published = {r.get("inbox_id") for r in manual if r.get("processed")}
        ar.write_inbox(gist_id, token, [r for r in inbox if r.get("inbox_id") not in published] + new)
    print(f"queued {len(new)} of {len(rows)} (rest already queued or published)")


def main():
    logging.disable(logging.INFO)  # Root credentials must not appear in the service's output.
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    repo = commands.add_parser("repo")
    repo.add_argument("url")
    repo.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    repo.add_argument("--description", required=True)
    repo.add_argument("--dry-run", action="store_true")
    commands.add_parser("rows")
    args = parser.parse_args()
    try:
        if args.command == "rows":
            raw = sys.stdin.read(100_001)
            if len(raw) > 100_000:
                raise ValueError("Release payload is too large")
            queue_rows(json.loads(raw))
        else:
            from services.homebrew_registry import repository_api_url
            url = web_url(args.url)
            if urlsplit(url).hostname != "github.com" or not repository_api_url(url).startswith("https://api.github.com/repos/"):
                raise ValueError("Expected a GitHub repository URL")
            if not args.description.strip() or len(args.description) > 220:
                raise ValueError("Description must contain 1–220 characters")
            import add_release as ar
            sys.argv = ["add_release.py", url, "--platform", args.platform, "--description", args.description]
            if args.dry_run:
                sys.argv.append("--dry-run")
            ar.main()
    except (ValueError, TypeError) as error:
        parser.exit(2, f"Queue request rejected: {error}\n")


if __name__ == "__main__":
    main()
