#!/usr/bin/env python3
import os
import json
import urllib.request
import urllib.error
import argparse
import logging
from typing import Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Files to sync
FILES_TO_SYNC = [
    "posted_links.json",
    "hb_state.json",
    "daily_digest_data.json",
    "homebrew_digest_data.json",
    "last_entry.txt",
    "last_digest_run.json",
    "last_homebrew_digest_run.json",
    "manual_releases.json",
    "list_hb.json"
]

DATA_DIR = "data"

def get_gist_headers(token: str) -> Dict[str, str]:
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def download_state(gist_id: str, token: str):
    logger.info(f"Downloading state from Gist {gist_id}...")
    url = f"https://api.github.com/gists/{gist_id}"
    req = urllib.request.Request(url, headers=get_gist_headers(token))
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    try:
        with urllib.request.urlopen(req) as response:
            gist_data = json.loads(response.read().decode())
            
            files = gist_data.get("files", {})
            for filename in FILES_TO_SYNC:
                if filename in files:
                    content = files[filename].get("content", "")
                    # Empty content in gist comes as string
                    filepath = os.path.join(DATA_DIR, filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info(f"Downloaded {filename}")
                else:
                    logger.warning(f"{filename} not found in Gist, will be created locally if needed.")
                    
        logger.info("Download complete.")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP Error: {e.code} - {e.read().decode()}")
        raise
    except Exception as e:
        logger.error(f"Error downloading state: {e}")
        raise

def merge_json_files(filename: str, local_content: str, gist_content: str) -> str:
    """Safely merges local and Gist contents for JSON files to prevent data loss while respecting local edits."""
    try:
        local_data = json.loads(local_content)
        gist_data = json.loads(gist_content)
    except Exception as e:
        logger.error(f"Error parsing JSON for merge ({filename}): {e}. Keeping local version.")
        return local_content

    if filename == "manual_releases.json":
        if not isinstance(local_data, list): local_data = []
        if not isinstance(gist_data, list): gist_data = []
        
        # Helper to get a unique key for manual release
        def get_release_key(e):
            url = e.get('url') or e.get('release_url') or ""
            name = e.get('title') or e.get('app_name') or ""
            version = e.get('version') or ""
            return (url.strip(), name.strip().lower(), version.strip().lower())

        gist_by_key = {get_release_key(e): e for e in gist_data}
        
        # Base merged list on local_data so local deletions and edits are respected!
        merged_list = []
        for local_entry in local_data:
            key = get_release_key(local_entry)
            if key in gist_by_key:
                gist_entry = gist_by_key[key]
                merged_entry = dict(gist_entry)
                merged_entry.update(local_entry)
                if local_entry.get('processed') or gist_entry.get('processed'):
                    merged_entry['processed'] = True
                merged_list.append(merged_entry)
            else:
                merged_list.append(local_entry)
                
        return json.dumps(merged_list, ensure_ascii=False, indent=2)

    elif filename == "posted_links.json":
        if not isinstance(local_data, dict): local_data = {}
        if not isinstance(gist_data, dict): gist_data = {}
        merged_dict = dict(gist_data)
        for k, v in local_data.items():
            if k not in merged_dict or v > merged_dict[k]:
                merged_dict[k] = v
        return json.dumps(merged_dict, ensure_ascii=False, indent=2)

    elif filename in ("daily_digest_data.json", "homebrew_digest_data.json"):
        if not isinstance(local_data, dict) or "entries" not in local_data: local_data = {"entries": []}
        if not isinstance(gist_data, dict) or "entries" not in gist_data: gist_data = {"entries": []}
        
        def get_entry_key(e):
            if filename == "daily_digest_data.json":
                return (e.get('url', '').strip(), e.get('is_updated', False))
            else:
                return e.get('release_url', '').strip() or (e.get('app_name', '').strip().lower(), e.get('version', '').strip().lower())
        
        gist_by_key = {get_entry_key(e): e for e in gist_data["entries"]}
        merged_entries = list(gist_data["entries"])
        
        for local_entry in local_data["entries"]:
            key = get_entry_key(local_entry)
            if key not in gist_by_key:
                merged_entries.append(local_entry)
            else:
                gist_entry = gist_by_key[key]
                local_time = local_entry.get('timestamp', '')
                gist_time = gist_entry.get('timestamp', '')
                if local_time > gist_time:
                    idx = merged_entries.index(gist_entry)
                    merged_entries[idx] = local_entry
        return json.dumps({"entries": merged_entries}, ensure_ascii=False, indent=2)

    elif filename in ("last_digest_run.json", "last_homebrew_digest_run.json"):
        if not isinstance(local_data, dict): local_data = {}
        if not isinstance(gist_data, dict): gist_data = {}
        local_time = local_data.get("last_digest_time", "")
        gist_time = gist_data.get("last_digest_time", "")
        if local_time > gist_time:
            return json.dumps(local_data, ensure_ascii=False, indent=2)
        else:
            return json.dumps(gist_data, ensure_ascii=False, indent=2)

    elif filename == "hb_state.json":
        if not isinstance(local_data, dict): local_data = {}
        if not isinstance(gist_data, dict): gist_data = {}
        merged_state = dict(gist_data)
        for k, v in local_data.items():
            if k not in merged_state:
                merged_state[k] = v
            else:
                gist_v = merged_state[k]
                local_ver = v.get("version", "")
                gist_ver = gist_v.get("version", "")
                local_upd = v.get("updated") or v.get("date", "")
                gist_upd = gist_v.get("updated") or gist_v.get("date", "")
                if local_upd > gist_upd or local_ver > gist_ver:
                    merged_state[k] = v
        return json.dumps(merged_state, ensure_ascii=False, indent=2)

    return gist_content if gist_content.strip() else local_content


def upload_state(gist_id: str, token: str, force: bool = False):
    logger.info(f"Uploading state to Gist {gist_id} (force={force})...")
    
    # 1. Download current Gist content first to perform a safe merge unless force is True
    gist_files = {}
    if not force:
        try:
            url = f"https://api.github.com/gists/{gist_id}"
            req = urllib.request.Request(url, headers=get_gist_headers(token))
            with urllib.request.urlopen(req) as response:
                gist_data = json.loads(response.read().decode())
                gist_files = gist_data.get("files", {})
            logger.info("Successfully fetched current Gist state for merging.")
        except Exception as e:
            logger.warning(f"Could not download Gist content before upload, skipping merge: {e}")
    else:
        logger.info("Force flag enabled: bypassing merge, uploading local files directly.")
    
    files_payload = {}
    for filename in FILES_TO_SYNC:
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                local_content = f.read()
                
            gist_file = gist_files.get(filename, {})
            gist_content = gist_file.get("content", "")
            
            # Merge logic if both Gist and local have content and force is False
            if not force and gist_content.strip() and gist_content.strip() not in ("empty", "{}") and local_content.strip():
                if filename.endswith('.json'):
                    final_content = merge_json_files(filename, local_content, gist_content)
                else:
                    final_content = local_content
                
                # Write the merged content back to the local file to keep it synced
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(final_content)
            else:
                final_content = local_content
                
            if final_content.strip():
                files_payload[filename] = {"content": final_content}
            else:
                files_payload[filename] = {"content": "{}" if filename.endswith('.json') else "empty"}
            logger.info(f"Prepared {filename} for upload.")
        else:
            logger.warning(f"File {filename} not found locally, skipping.")
            
    if not files_payload:
        logger.warning("No files found to upload.")
        return

    url = f"https://api.github.com/gists/{gist_id}"
    payload = json.dumps({"files": files_payload}).encode("utf-8")
    
    req = urllib.request.Request(url, data=payload, headers=get_gist_headers(token), method="PATCH")
    
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                logger.info("Upload successful.")
            else:
                logger.error(f"Upload returned status {response.status}")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP Error: {e.code} - {e.read().decode()}")
        raise
    except Exception as e:
        logger.error(f"Error uploading state: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Synchronize bot state with GitHub Gist")
    parser.add_argument("action", choices=["download", "upload"], help="Action to perform")
    parser.add_argument("-f", "--force", action="store_true", help="Force upload local files directly without merging")
    
    args = parser.parse_args()
    
    gist_id = os.environ.get("GIST_ID")
    token = os.environ.get("GIST_TOKEN")
    
    if not gist_id or not token:
        try:
            from core.settings_loader import settings
            gist_id = gist_id or settings.get("GIST_ID") or "46128fc489e0fd60e226ff26dc638e97"
            token = token or settings.get("GIST_TOKEN") or settings.get("GITHUB_TOKEN")
        except Exception as e:
            logger.debug(f"Could not load Gist settings from config: {e}")
            
    if not gist_id or not token:
        logger.error("GIST_ID and GIST_TOKEN must be set as environment variables or in config/local_settings.json.")
        exit(1)
        
    if args.action == "download":
        download_state(gist_id, token)
    elif args.action == "upload":
        upload_state(gist_id, token, force=args.force)

if __name__ == "__main__":
    main()
