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

def upload_state(gist_id: str, token: str):
    logger.info(f"Uploading state to Gist {gist_id}...")
    
    files_payload = {}
    for filename in FILES_TO_SYNC:
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    files_payload[filename] = {"content": content}
                else:
                    # Gist doesn't accept completely empty files, provide placeholder
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
    
    args = parser.parse_args()
    
    gist_id = os.environ.get("GIST_ID")
    token = os.environ.get("GIST_TOKEN")
    
    if not gist_id or not token:
        try:
            from core.settings_loader import settings
            gist_id = gist_id or settings.get("GIST_ID")
            token = token or settings.get("GIST_TOKEN")
        except Exception as e:
            logger.debug(f"Could not load Gist settings from config: {e}")
            
    if not gist_id or not token:
        logger.error("GIST_ID and GIST_TOKEN must be set as environment variables or in config/local_settings.json.")
        exit(1)
        
    if args.action == "download":
        download_state(gist_id, token)
    elif args.action == "upload":
        upload_state(gist_id, token)

if __name__ == "__main__":
    main()
