"""GitHub API helpers shared by the scratch/fetch_*.py scripts.

These were copy-pasted into five files; the only real differences were the dummy-token
filter (kept) and a stray `sorted and` in one condition (dropped — `sorted` is the
builtin, always truthy, so it never did anything).
"""
import json
import os
import sys


def load_github_token():
    """GITHUB_TOKEN from env, else config/local_settings.json or settings.json."""
    token = os.environ.get("GITHUB_TOKEN")
    if token and "dummy" not in token.lower():
        return token

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for filename in ["local_settings.json", "settings.json"]:
        path = os.path.join(root_dir, "config", filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    val = json.load(f).get("GITHUB_TOKEN")
                if val and not val.startswith("os.environ") and "gho_sHIJ" not in val:
                    return val
            except Exception:
                pass
    return None


GITHUB_TOKEN = load_github_token()


async def github_request(session, url: str) -> dict:
    """GET a GitHub API URL, returning parsed JSON or None on any non-200."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            print(f"Error requesting {url}: status {resp.status}", file=sys.stderr)
            return None
        return await resp.json()


async def get_repo_details(session, owner, repo):
    """Repo metadata plus its most recent release, or None if the repo is unreachable."""
    repo_info = await github_request(session, f"https://api.github.com/repos/{owner}/{repo}")
    if not repo_info:
        return None

    releases = await github_request(session, f"https://api.github.com/repos/{owner}/{repo}/releases")
    latest_release = releases[0] if releases and isinstance(releases, list) else None

    return {
        "owner": owner,
        "repo": repo,
        "name": repo_info.get("name"),
        "description": repo_info.get("description"),
        "html_url": repo_info.get("html_url"),
        "updated_at": repo_info.get("updated_at"),
        "pushed_at": repo_info.get("pushed_at"),
        "latest_release": {
            "tag_name": latest_release.get("tag_name"),
            "html_url": latest_release.get("html_url"),
            "published_at": latest_release.get("published_at"),
            "body": latest_release.get("body"),
        } if latest_release else None
    }
