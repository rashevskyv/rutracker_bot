#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.error
import subprocess
from datetime import datetime, timezone, timedelta
from openai import OpenAI

DATA_DIR = "data"
MANUAL_RELEASES_FILE = os.path.join(DATA_DIR, "manual_releases.json")
TARGET_USERS = ["NaGaa95", "ChanseyIsTheBest"]
MAX_RELEASE_AGE_DAYS = 3  # Only collect releases from the last 3 days (recent/new)

EXCLUDE_KEYWORDS = [
    "kernel", "nvgpu", "dtb", "l4t", "firmware", "hekate", "atmosphere", 
    "payload", "android", "linux", "driver", "cheat", "database", "patch", 
    "config", "bootloader", "sysmodule", "overlay", "module", "loader", "sdk"
]

def run_gist_sync(action: str) -> bool:
    """Runs the sync_gist_state.py script to download or upload state."""
    print(f"\n--- Gist Sync: {action.upper()} ---")
    try:
        res = subprocess.run([sys.executable, "sync_gist_state.py", action], capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            print(f"Error during Gist sync {action}: {res.stderr}")
            return False
        print(res.stdout.strip())
        return True
    except Exception as e:
        print(f"Failed to run Gist sync {action}: {e}")
        return False

def fetch_user_repos(username: str, token: str = None) -> list:
    """Fetches all public repositories for a GitHub user."""
    print(f"Fetching repositories for user '{username}'...")
    url = f"https://api.github.com/users/{username}/repos?per_page=100&sort=updated"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "RuTracker-Bot-Collector")
    if token:
        req.add_header("Authorization", f"token {token}")
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching repos for {username}: {e}")
        return []

def fetch_latest_release(owner: str, repo: str, token: str = None) -> dict:
    """Fetches the latest release details for a repository."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "RuTracker-Bot-Collector")
    if token:
        req.add_header("Authorization", f"token {token}")
        
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None # No releases
        print(f"HTTP Error {e.code} fetching release for {owner}/{repo}")
        return None
    except Exception as e:
        print(f"Error fetching release for {owner}/{repo}: {e}")
        return None

def is_already_added(manual_entries: list, repo_url: str, repo_name: str) -> bool:
    """Checks if a repository is already tracked in manual_releases.json."""
    repo_url_clean = repo_url.lower().rstrip('/')
    repo_name_clean = repo_name.lower().replace("-nx", "").replace("_nx", "").replace("-switch", "").replace("_switch", "").strip()
    
    for entry in manual_entries:
        entry_url = (entry.get("release_url") or entry.get("url") or "").lower().rstrip('/')
        if repo_url_clean in entry_url or entry_url in repo_url_clean:
            return True
            
        entry_name = (entry.get("app_name") or entry.get("title") or "").lower().replace("-nx", "").replace("_nx", "").replace("-switch", "").replace("_switch", "").strip()
        if entry.get("type") == "homebrew" and entry_name == repo_name_clean:
            return True
            
    return False

def is_system_or_kernel_component(repo_name: str, repo_desc: str) -> bool:
    """Returns True if the repo is a kernel, DTB, firmware, or non-game system component."""
    combined = f"{repo_name} {repo_desc or ''}".lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in combined:
            return True
    return False

def is_release_recent(pub_date_str: str, max_days: int = MAX_RELEASE_AGE_DAYS) -> bool:
    """Checks if the release date is within the max allowed age in days."""
    if not pub_date_str:
        return False
    try:
        date_clean = pub_date_str.replace("Z", "+00:00")
        pub_dt = datetime.fromisoformat(date_clean)
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        age = now - pub_dt
        return age <= timedelta(days=max_days)
    except Exception as e:
        print(f"Warning: Could not parse release date '{pub_date_str}': {e}")
        return True

def analyze_repo_with_gemini(repo_name: str, repo_desc: str, topics: list, username: str = "author") -> dict:
    """Calls local Gemini Web2API (or OpenAI API) to analyze if a repo is a Switch game port and translate details."""
    prompt = f"""
Analyze the following GitHub repository of user '{username}' to determine if it is specifically a playable GAME or a GAME PORT for the Nintendo Switch console.

Repo Name: {repo_name}
Description: {repo_desc or "No description provided."}
Topics: {", ".join(topics) if topics else "None"}

CRITICAL CLASSIFICATION RULES:
1. Set 'is_switch_game' to true ONLY if this repository is a playable GAME or a GAME PORT (e.g. Android/PC/retro game ported to Nintendo Switch).
2. Set 'is_switch_game' to false if it is a kernel, Linux/L4T component, DTB file, firmware, driver, system tool, bootloader, payload, cheat database, sysmodule, overlay, emulator, or non-game utility.
3. Formulate a short, punchy description of the game/game port in Ukrainian (max 1-2 sentences). Example: 'Порт гри [Name] для Nintendo Switch.'
4. Clean the app name (remove suffixes like '-NX', '_nx', '-switch', or similar).

Respond ONLY with a raw JSON object containing these keys:
{{
  "is_switch_game": true/false,
  "app_name": "...",
  "description": "...",
  "platform": "Switch"
}}
"""
    # 1. Attempt Local Gemini Web2API (http://localhost:8081/v1) with gemini-3.5-flash-thinking
    try:
        from core.settings_loader import settings
        base_url = settings.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "http://localhost:8081/v1"
        client = OpenAI(api_key="dummy_key", base_url=base_url, max_retries=0, timeout=25.0)
        model_name = settings.get("OPENAI_MODEL", "gemini-3.5-flash-thinking")
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = response.choices[0].message.content
        if content:
            content = content.strip()
            import re
            match = re.search(r'(\{.*\})', content, re.DOTALL)
            if match:
                content = match.group(1)
            res = json.loads(content)
            res["is_switch_related"] = res.get("is_switch_game", False)
            return res
    except Exception as e:
        print(f"Warning: Local Gemini Web2API call failed for {repo_name}: {e}. Trying OpenAI API fallback...")

    # 2. Attempt OpenAI API fallback (if OPENAI_API_KEY is available)
    try:
        from core.settings_loader import settings
        api_key = settings.get("OPENAI_API_KEY") or settings.get("OPENAI_API") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            client = OpenAI(api_key=api_key, max_retries=0, timeout=10.0)
            response = client.chat.completions.create(
                model=settings.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            content = response.choices[0].message.content
            if content:
                content = content.strip()
                import re
                match = re.search(r'(\{.*\})', content, re.DOTALL)
                if match:
                    content = match.group(1)
                res = json.loads(content)
                res["is_switch_related"] = res.get("is_switch_game", False)
                return res
    except Exception as e:
        print(f"Warning: OpenAI API fallback failed for {repo_name}: {e}. Using keywords.")

    # 3. Keyword fallback
    desc_lower = (repo_desc or "").lower()
    name_lower = repo_name.lower()
    is_game = any(x in name_lower or x in desc_lower for x in ["game", "port", "switch", "nx"]) and not is_system_or_kernel_component(repo_name, repo_desc)
    
    return {
        "is_switch_related": is_game,
        "app_name": repo_name.replace("-NX", "").replace("_nx", "").replace("-switch", "").replace("-", " ").title(),
        "description": f"Порт гри {repo_name} для Nintendo Switch." if is_game else "",
        "platform": "Switch"
    }

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    github_token = None
    try:
        from core.settings_loader import settings
        github_token = settings.get("GIST_TOKEN") or settings.get("GITHUB_TOKEN")
    except Exception:
        pass

    if not run_gist_sync("download"):
        print("Gist download failed. Cannot proceed safely.")
        return

    if os.path.exists(MANUAL_RELEASES_FILE):
        try:
            with open(MANUAL_RELEASES_FILE, "r", encoding="utf-8") as f:
                manual_releases = json.load(f)
        except Exception as e:
            print(f"Error loading manual_releases.json: {e}")
            manual_releases = []
    else:
        manual_releases = []

    total_added_count = 0

    for username in TARGET_USERS:
        print(f"\n==========================================")
        print(f"Processing user: {username}")
        print(f"==========================================")
        
        repos = fetch_user_repos(username, github_token)
        if not repos:
            print(f"No repositories found for {username} or error occurred.")
            continue

        print(f"Analyzing {len(repos)} repositories for {username}...")
        user_added_count = 0

        for repo in repos:
            repo_name = repo["name"]
            repo_url = repo["html_url"]
            repo_desc = repo["description"]
            topics = repo.get("topics", [])
            
            if is_already_added(manual_releases, repo_url, repo_name):
                continue

            if is_system_or_kernel_component(repo_name, repo_desc):
                print(f"-> Skipped {repo_name} (system/kernel component)")
                continue

            release = fetch_latest_release(username, repo_name, github_token)
            
            pub_date = repo.get("pushed_at") or repo.get("updated_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            version = "v1.0.0"
            release_url = repo_url

            if release:
                version = release.get("tag_name") or version
                release_url = release.get("html_url") or release_url
                pub_date = release.get("published_at") or pub_date

            if not is_release_recent(pub_date, MAX_RELEASE_AGE_DAYS):
                print(f"-> Skipped {repo_name} (release is older than {MAX_RELEASE_AGE_DAYS} days: {pub_date})")
                continue

            print(f"\nChecking game candidate: {repo_name} ({pub_date})...")
            
            ai_res = analyze_repo_with_gemini(repo_name, repo_desc, topics, username)
            if not ai_res.get("is_switch_related"):
                print(f"-> Skipped {repo_name} (not a Switch game/game port according to AI)")
                continue

            new_entry = {
                "type": "homebrew",
                "platform": ai_res.get("platform", "Switch"),
                "app_name": f"{ai_res.get('app_name', repo_name)} ({username})",
                "version": version,
                "release_url": release_url,
                "description": ai_res.get("description") or f"Порт гри для Nintendo Switch.",
                "is_new": True,
                "date": pub_date,
                "processed": False
            }

            manual_releases.append(new_entry)
            user_added_count += 1
            total_added_count += 1
            print(f"-> ADDED NEW GAME: {new_entry['app_name']} ({version}) - {new_entry['description']}")

        print(f"\nUser {username}: added {user_added_count} new game release(s).")

    if total_added_count > 0:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(MANUAL_RELEASES_FILE, "w", encoding="utf-8") as f:
            json.dump(manual_releases, f, ensure_ascii=False, indent=2)
            
        print(f"\nSuccessfully added {total_added_count} new manual releases locally.")
        
        if run_gist_sync("upload"):
            print("Gist upload successful! All environments are in sync.")
        else:
            print("Gist upload failed. State remains local.")
    else:
        print("\nNo new Switch game releases found.")

if __name__ == "__main__":
    main()
