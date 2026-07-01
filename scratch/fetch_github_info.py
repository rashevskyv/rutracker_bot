import asyncio
import sys
import os
import json
import aiohttp
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings_loader import get_session, close_clients

# Load GitHub token dynamically from environment or settings
def load_github_token():
    import os
    import json
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    # Try config/local_settings.json or settings.json
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for filename in ["local_settings.json", "settings.json"]:
        path = os.path.join(root_dir, "config", filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    val = cfg.get("GITHUB_TOKEN")
                    if val and not val.startswith("os.environ"):
                        return val
            except Exception:
                pass
    return None

GITHUB_TOKEN = load_github_token()

async def github_request(session, url: str) -> dict:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            print(f"Error requesting {url}: status {resp.status}", file=sys.stderr)
            return None
        return await resp.json()

async def get_repo_details(session, owner, repo):
    repo_url = f"https://api.github.com/repos/{owner}/{repo}"
    releases_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    
    repo_info = await github_request(session, repo_url)
    if not repo_info:
        return None
        
    releases = await github_request(session, releases_url)
    latest_release = None
    if releases and isinstance(releases, list) and len(releases) > 0:
        latest_release = releases[0]
        
    return {
        "owner": owner,
        "repo": repo,
        "name": repo_info.get("name"),
        "description": repo_info.get("description"),
        "html_url": repo_info.get("html_url"),
        "updated_at": repo_info.get("updated_at"),
        "pushed_at": repo_info.get("pushed_at"),
        "latest_release": {
            "tag_name": latest_release.get("tag_name") if latest_release else None,
            "html_url": latest_release.get("html_url") if latest_release else None,
            "published_at": latest_release.get("published_at") if latest_release else None,
            "body": latest_release.get("body") if latest_release else None,
        } if latest_release else None
    }

async def main():
    session = get_session()
    
    # 1. Fetch specified repos
    repos_to_fetch = [
        ("souldbminerr", "sandboxels-nx"),
        ("souldbminerr", "spidermonkey-NX"),
        ("souldbminerr", "ChatNX")
    ]
    
    results = []
    for owner, repo in repos_to_fetch:
        details = await get_repo_details(session, owner, repo)
        if details:
            results.append(details)
            
    # 2. Fetch NaGaa95 repos
    nagaa_repos_url = "https://api.github.com/users/NaGaa95/repos?per_page=100"
    nagaa_repos = await github_request(session, nagaa_repos_url)
    
    nagaa_filtered = []
    if nagaa_repos and isinstance(nagaa_repos, list):
        print(f"Fetched {len(nagaa_repos)} repos for NaGaa95", file=sys.stderr)
        for repo_info in nagaa_repos:
            # We care about repos updated/pushed since 2026-06-01
            pushed_at_str = repo_info.get("pushed_at") or repo_info.get("updated_at")
            if pushed_at_str:
                pushed_dt = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
                summer_dt = datetime.fromisoformat("2026-06-01T00:00:00+00:00")
                if pushed_dt >= summer_dt:
                    owner = "NaGaa95"
                    repo_name = repo_info.get("name")
                    details = await get_repo_details(session, owner, repo_name)
                    if details:
                        nagaa_filtered.append(details)
                        
    output_data = {
        "specified": results,
        "nagaa": nagaa_filtered
    }
    
    output_file = os.path.join(os.path.dirname(__file__), "github_repos.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"Successfully wrote data to {output_file}", file=sys.stderr)
    await close_clients()

if __name__ == "__main__":
    asyncio.run(main())
