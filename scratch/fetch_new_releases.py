import asyncio
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings_loader import get_session, close_clients
from services.translation import translate_short_description

# We reuse the token from scratch/fetch_user_list.py if needed, or get_env_or_setting
# Load GitHub token dynamically from environment or settings
def load_github_token():
    import os
    import json
    token = os.environ.get("GITHUB_TOKEN")
    if token and "dummy" not in token.lower():
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
                    if val and not val.startswith("os.environ") and "gho_sHIJ" not in val:
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

async def process_repo(repo_data, custom_name=None):
    owner = repo_data["owner"]
    repo = repo_data["repo"]
    name = repo_data["name"]
    raw_description = repo_data["description"] or f"Homebrew for Switch: {name}."
    html_url = repo_data["html_url"]
    
    latest_release = repo_data.get("latest_release")
    
    # 1. Determine version
    version = "v1.0.0"
    if latest_release and latest_release.get("tag_name"):
        version = latest_release["tag_name"]
        
    # 2. Determine release URL
    release_url = html_url
    if latest_release and latest_release.get("html_url"):
        release_url = latest_release["html_url"]
        
    # 3. Determine is_new
    is_new = False
    if not latest_release:
        is_new = True
    else:
        v_lower = version.lower()
        if v_lower in ("1.0.0", "v1.0.0", "1.0", "v1.0", "1.0.0-nx", "v1.0.0-nx"):
            is_new = True
        else:
            body = (latest_release.get("body") or "").lower()
            if "initial release" in body or "initial version" in body:
                is_new = True
                
    # 4. Determine date
    raw_date = None
    if latest_release and latest_release.get("published_at"):
        raw_date = latest_release["published_at"]
    else:
        raw_date = repo_data.get("pushed_at") or repo_data.get("updated_at")
        
    if raw_date:
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            date_str = dt.isoformat()
        except Exception:
            date_str = datetime.now().isoformat()
    else:
        date_str = datetime.now().isoformat()
        
    # 5. Translate description
    print(f"Translating description for {owner}/{repo}: '{raw_description}'", file=sys.stderr)
    try:
        translated_desc = await translate_short_description(raw_description)
    except Exception as e:
        print(f"Translation failed for {repo}: {e}", file=sys.stderr)
        translated_desc = raw_description
        
    # 6. Format app name nicely
    app_name = custom_name if custom_name else name
    
    platform = "Switch"
    
    return {
        "type": "homebrew",
        "app_name": app_name,
        "version": version,
        "release_url": release_url,
        "platform": platform,
        "is_new": is_new,
        "description": translated_desc,
        "date": date_str,
        "processed": False
    }

async def main():
    session = get_session()
    
    repos_to_fetch = [
        ("NaGaa95", "laytonbmr_nx", "Laytonbmr NX (Layton Brothers: Mystery Room)"),
        ("NaGaa95", "vln_nx", "Vln NX (Very Little Nightmares)")
    ]
    
    generated_entries = []
    
    for owner, repo_name, custom_name in repos_to_fetch:
        print(f"Fetching details for {owner}/{repo_name}...", file=sys.stderr)
        details = await get_repo_details(session, owner, repo_name)
        if details:
            entry = await process_repo(details, custom_name)
            generated_entries.append(entry)
            
    # Load existing manual releases
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manual_path = os.path.join(root_dir, "data", "manual_releases.json")
    
    if not os.path.exists(manual_path):
        manual_entries = []
    else:
        with open(manual_path, "r", encoding="utf-8") as f:
            manual_entries = json.load(f)
            
    # Deduplicate entries by (app_name, version)
    existing_keys = {(e["app_name"].lower(), e["version"].lower()) for e in manual_entries}
    
    added_count = 0
    for entry in generated_entries:
        key = (entry["app_name"].lower(), entry["version"].lower())
        if key not in existing_keys:
            manual_entries.append(entry)
            added_count += 1
            
    with open(manual_path, "w", encoding="utf-8") as f:
        json.dump(manual_entries, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully added {added_count} new entries to {manual_path}", file=sys.stderr)
    await close_clients()

if __name__ == "__main__":
    asyncio.run(main())
