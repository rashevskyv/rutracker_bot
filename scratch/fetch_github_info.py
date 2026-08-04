import asyncio
import sys
import os
import json
import aiohttp
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings_loader import get_session, close_clients
from scratch._gh import GITHUB_TOKEN, github_request, get_repo_details


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
