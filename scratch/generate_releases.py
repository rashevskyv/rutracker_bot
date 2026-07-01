import asyncio
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings_loader import close_clients
from services.translation import translate_short_description

async def process_repo(repo_data, is_specified=False):
    owner = repo_data["owner"]
    repo = repo_data["repo"]
    name = repo_data["name"]
    raw_description = repo_data["description"] or f"Port of {name} for Switch."
    html_url = repo_data["html_url"]
    
    latest_release = repo_data.get("latest_release")
    
    # 1. Determine version
    version = "v1.0.0"
    if latest_release and latest_release.get("tag_name"):
        version = latest_release["tag_name"]
    elif is_specified:
        # User specified, let's keep v1.0.0 if not found
        version = "v1.0.0"
        
    # 2. Determine release URL
    release_url = html_url
    if latest_release and latest_release.get("html_url"):
        release_url = latest_release["html_url"]
        
    # 3. Determine is_new
    is_new = False
    if is_specified:
        is_new = True
    else:
        # Determine if NaGaa95 release is new
        # Rules: if no release exists, or version is 1.0.0/v1.0.0/1.0/v1.0, or release body has "initial"
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
    # Format should be: "2026-06-25T23:31:33+03:00"
    # We can use published_at if exists, otherwise pushed_at or updated_at
    raw_date = None
    if latest_release and latest_release.get("published_at"):
        raw_date = latest_release["published_at"]
    else:
        raw_date = repo_data.get("pushed_at") or repo_data.get("updated_at")
        
    # Convert Z to +00:00 or parse and keep it
    if raw_date:
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            # Format to include timezone offset (e.g. +03:00 like other entries)
            # Since user's local timezone offset is +03:00 (from metadata), let's use +03:00 or keep UTC
            # Let's format in UTC/offset. Simple: dt.isoformat()
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
        
    # Add human-friendly cleanup or prefix if needed, but translate_short_description should be good
    
    # 6. Format app name nicely
    app_name = name
    # Clean up name: replace underscore/hyphen with space, keep case, or clean suffix
    # But usually github name is fine or we can capitalize it.
    # E.g. 'sandboxels-nx' -> 'Sandboxels-NX' or similar. Let's keep name as is or capitalize
    if "-" in app_name or "_" in app_name:
        parts = app_name.replace("_", " ").replace("-", " ").split()
        # Capitalize each part, but if part is 'nx' make it 'NX'
        parts = [p.upper() if p.lower() == 'nx' else p.capitalize() for p in parts]
        app_name = " ".join(parts)
    else:
        if app_name.lower() == 'chatnx':
            app_name = 'ChatNX'
            
    # Platform is Switch
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
    input_file = os.path.join(os.path.dirname(__file__), "github_repos.json")
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found!", file=sys.stderr)
        sys.exit(1)
        
    with open(input_file, "r", encoding="utf-8") as f:
        repos_data = json.load(f)
        
    generated_entries = []
    
    # Process specified repos
    print("Processing specified repos...", file=sys.stderr)
    for repo_data in repos_data.get("specified", []):
        entry = await process_repo(repo_data, is_specified=True)
        generated_entries.append(entry)
        
    # Process NaGaa95 repos
    print("Processing NaGaa95 repos...", file=sys.stderr)
    for repo_data in repos_data.get("nagaa", []):
        entry = await process_repo(repo_data, is_specified=False)
        generated_entries.append(entry)
        
    output_file = os.path.join(os.path.dirname(__file__), "generated_manual_releases.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(generated_entries, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully generated {len(generated_entries)} entries in {output_file}", file=sys.stderr)
    await close_clients()

if __name__ == "__main__":
    asyncio.run(main())
