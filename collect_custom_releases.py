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
CUSTOM_RELEASES_STATE_FILE = os.path.join(DATA_DIR, "custom_releases_state.json")

TARGET_USERS = ["NaGaa95", "ChanseyIsTheBest", "delsonazevedo", "boraeskicioglu", "PalindromicBreadLoaf"]
NEW_AUTHOR_AGE_DAYS = 21  # Collect releases from last 3 weeks for new authors

def run_gist_sync(action: str) -> bool:
    """Runs the sync_gist_state.py script to download or upload state."""
    print(f"\n--- Gist Sync: {action.upper()} ---")
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        res = subprocess.run(
            [sys.executable, "sync_gist_state.py", action],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )
        if res.returncode != 0:
            print(f"Error during Gist sync {action}: {res.stderr}")
            return False
        print(res.stdout.strip())
        return True
    except Exception as e:
        print(f"Failed to run Gist sync {action}: {e}")
        return False

def load_custom_releases_state() -> dict:
    """Loads state tracking for custom releases collection."""
    if os.path.exists(CUSTOM_RELEASES_STATE_FILE):
        try:
            with open(CUSTOM_RELEASES_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"Error loading custom_releases_state.json: {e}")
    return {"last_run": None, "authors": {}}

def save_custom_releases_state(state: dict):
    """Saves state tracking for custom releases collection."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(CUSTOM_RELEASES_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving custom_releases_state.json: {e}")

def parse_iso_datetime(date_str: str) -> datetime:
    """Parses ISO-8601 date string to timezone-aware UTC datetime."""
    if not date_str:
        return None
    try:
        clean = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        print(f"Warning: Could not parse date '{date_str}': {e}")
        return None

def is_release_after_cutoff(pub_date_str: str, cutoff_dt: datetime) -> bool:
    """Checks if release date is at or after cutoff datetime."""
    pub_dt = parse_iso_datetime(pub_date_str)
    if not pub_dt or not cutoff_dt:
        return False
    return pub_dt >= cutoff_dt

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
    except urllib.error.HTTPError as e:
        if e.code == 401 and token:
            print(f"Warning: Authorization failed (401 Bad credentials) for {username}, retrying without token...")
            return fetch_user_repos(username, token=None)
        print(f"Error fetching repos for {username}: {e}")
        return []
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
        if e.code == 401 and token:
            print(f"Warning: Authorization failed (401 Bad credentials) for {owner}/{repo}, retrying without token...")
            return fetch_latest_release(owner, repo, token=None)
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

def is_local_web2api_online() -> bool:
    import socket
    try:
        s = socket.socket()
        s.settimeout(0.1)
        s.connect(("127.0.0.1", 8081))
        s.close()
        return True
    except Exception:
        return False

def analyze_repo_with_gemini(repo_name: str, repo_desc: str, topics: list, username: str = "author") -> dict:
    """Calls Gemini Web2API (or OpenAI API) to format app name, description in Ukrainian, and verify if it's Switch homebrew."""
    prompt = f"""
Analyze the following new GitHub repository of user '{username}'.

Repo Name: {repo_name}
Description: {repo_desc or "No description provided."}
Topics: {", ".join(topics) if topics else "None"}

Determine:
1. Is this repository a homebrew application, game, port, emulator, or utility designed for Nintendo Switch? Set "is_switch_homebrew": true if yes, false if it is for PC only, another platform, non-Switch tutorial/bootcamp, or generic non-Switch code.
2. Formulate a short, punchy description of this release in Ukrainian (max 1-2 sentences). Example: 'Новий реліз [Name] для Nintendo Switch.'
3. Clean the app name (remove suffixes like '-NX', '_nx', '-switch', or similar).

Respond ONLY with a raw JSON object containing these keys:
{{
  "is_switch_homebrew": true,
  "app_name": "...",
  "description": "...",
  "platform": "Switch"
}}
"""
    # 1. Attempt Local Gemini Web2API (http://localhost:8081/v1) with gemini-3.5-flash-thinking
    if is_local_web2api_online():
        try:
            from core.settings_loader import settings
            base_url = settings.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "http://localhost:8081/v1"
            client = OpenAI(api_key="dummy_key", base_url=base_url, max_retries=0, timeout=5.0)
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
                return json.loads(content)
        except Exception as e:
            print(f"Info: Local Gemini Web2API call failed ({e}). Trying OpenAI API fallback.")

    # 2. Attempt OpenRouter / OpenAI API (if OPENROUTER_API_KEY or OPENAI_API_KEY is available)
    try:
        from core.settings_loader import settings
        api_key = (
            settings.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or settings.get("OPENAI_API_KEY")
            or settings.get("OPENAI_API")
            or os.environ.get("OPENAI_API_KEY")
        )
        if api_key:
            is_openrouter = api_key.startswith("sk-or-") or bool(settings.get("OPENROUTER_API_KEY")) or bool(os.environ.get("OPENROUTER_API_KEY"))
            base_url = "https://openrouter.ai/api/v1" if is_openrouter else None
            headers = {"HTTP-Referer": "https://github.com/rashevskyv/rutracker_bot", "X-Title": "RuTracker Bot"} if is_openrouter else None
            
            client = OpenAI(api_key=api_key.strip(), base_url=base_url, default_headers=headers, max_retries=0, timeout=15.0)
            default_model = "openai/gpt-5.6-luna" if is_openrouter else "gpt-4o-mini"
            model_name = settings.get("OPENROUTER_MODEL") or settings.get("OPENAI_MODEL") or default_model
            
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
                return json.loads(content)
    except Exception as e:
        print(f"Warning: OpenRouter/OpenAI API call failed for {repo_name}: {e}. Using code fallback format.")

    # 3. Code-based heuristic fallback
    combined_text = f"{repo_name} {repo_desc or ''} {' '.join(topics)}".lower()
    is_switch = any(kw in combined_text for kw in ["switch", "nx", "homebrew", "nintendo", "libnx", "atmosphere", "hekat", "nro", "nsp", "xci", "hbmenu", "port"])
    clean_name = repo_name.replace("-NX", "").replace("_nx", "").replace("-switch", "").replace("-", " ").title()
    return {
        "is_switch_homebrew": is_switch,
        "app_name": clean_name,
        "description": f"Новий реліз {clean_name} для Nintendo Switch.",
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

    state = load_custom_releases_state()
    last_run_str = state.get("last_run")
    authors_state = state.get("authors", {})
    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    total_added_count = 0

    for username in TARGET_USERS:
        is_new_author = username not in authors_state
        if is_new_author:
            cutoff_dt = now_dt - timedelta(days=NEW_AUTHOR_AGE_DAYS)
            print(f"\n==========================================")
            print(f"Processing NEW author: {username} (cutoff: last {NEW_AUTHOR_AGE_DAYS} days -> {cutoff_dt.strftime('%Y-%m-%d')})")
            print(f"==========================================")
        else:
            last_run_dt = parse_iso_datetime(last_run_str)
            if last_run_dt:
                cutoff_dt = last_run_dt
            else:
                cutoff_dt = now_dt - timedelta(days=NEW_AUTHOR_AGE_DAYS)
            print(f"\n==========================================")
            print(f"Processing existing author: {username} (cutoff: since last run -> {cutoff_dt.strftime('%Y-%m-%d %H:%M:%S UTC')})")
            print(f"==========================================")

        repos = fetch_user_repos(username, github_token)
        if not repos:
            print(f"No repositories found for {username} or error occurred.")
            authors_state[username] = {
                "first_seen": authors_state.get(username, {}).get("first_seen") or now_str,
                "last_checked": now_str
            }
            continue

        print(f"Checking {len(repos)} repositories for {username}...")
        user_added_count = 0

        for repo in repos:
            repo_name = repo["name"]
            repo_url = repo["html_url"]
            repo_desc = repo["description"]
            topics = repo.get("topics", [])
            
            if is_already_added(manual_releases, repo_url, repo_name):
                continue

            release = fetch_latest_release(username, repo_name, github_token)
            
            pub_date = repo.get("pushed_at") or repo.get("updated_at") or now_str
            version = "v1.0.0"
            release_url = repo_url

            if release:
                version = release.get("tag_name") or version
                release_url = release.get("html_url") or release_url
                pub_date = release.get("published_at") or pub_date

            if not is_release_after_cutoff(pub_date, cutoff_dt):
                continue

            ai_res = analyze_repo_with_gemini(repo_name, repo_desc, topics, username)

            if not ai_res.get("is_switch_homebrew", True):
                print(f"Skipping repository '{repo_name}': not identified as Nintendo Switch homebrew.")
                continue

            print(f"\nFound new Nintendo Switch release: {repo_name} ({version}, date: {pub_date})...")

            new_entry = {
                "type": "homebrew",
                "platform": ai_res.get("platform", "Switch"),
                "app_name": f"{ai_res.get('app_name', repo_name)} ({username})",
                "version": version,
                "release_url": release_url,
                "description": ai_res.get("description") or f"Новий реліз {repo_name} для Nintendo Switch.",
                "is_new": True,
                "date": pub_date,
                "processed": False
            }

            manual_releases.append(new_entry)
            user_added_count += 1
            total_added_count += 1
            print(f"-> ADDED NEW RELEASE: {new_entry['app_name']} ({version}) - {new_entry['description']}")

        authors_state[username] = {
            "first_seen": authors_state.get(username, {}).get("first_seen") or now_str,
            "last_checked": now_str
        }
        print(f"\nUser {username}: added {user_added_count} new release(s).")

    state["last_run"] = now_str
    state["authors"] = authors_state
    save_custom_releases_state(state)

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
        # Save state & upload state even if 0 releases were added so last_run is updated!
        if run_gist_sync("upload"):
            print("State updated and uploaded to Gist.")
        print("\nNo new releases found since last run.")

if __name__ == "__main__":
    main()
