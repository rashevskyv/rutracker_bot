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

# eShop Live Showcase state — must not be clobbered by digest/rt/hb gist sync.
# These are synced only by the eshop runner (or explicit CLI file args).
ESHOP_STATE_FILES = [
    "eshop_posted_deals.json",
    "eshop_active_showcase.json",
    "last_eshop_deals_run.json",
]

# Files to sync by default (operational + caches). Includes eShop unless excluded.
FILES_TO_SYNC = [
    "posted_links.json",
    "hb_state.json",
    "udb_state.json",
    "fortheusers_state.json",
    "vitadb_state.json",
    "switchports_state.json",
    "daily_digest_data.json",
    "homebrew_digest_data.json",
    "last_entry.txt",
    "last_digest_run.json",
    "last_homebrew_digest_run.json",
    "manual_releases.json",
    "list_hb.json",
    "custom_releases_state.json",
    "eshop_posted_deals.json",
    "eshop_active_showcase.json",
    "eshop_region_prices_cache.json",
    "last_eshop_deals_run.json",
    "eshop_descriptions.json",
    "eshop_subscriptions.json",
    "eshop_wishlist.json",
    "user_subscriptions.json",
    "hb_descriptions.json",
    "translations_cache.json"
]

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
# Last synced registries: lets the merge tell a deletion from an addition.
BASE_DIR = os.path.join(DATA_DIR, ".gist_base")


def load_base(filename: str):
    """Parsed Gist content of filename at the last sync, or None."""
    try:
        with open(os.path.join(BASE_DIR, filename), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_base(filename: str, content: str):
    if filename not in {"manual_releases.json", "list_hb.json"}:
        return
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(os.path.join(BASE_DIR, filename), "w", encoding="utf-8") as f:
        f.write(content)


def _release_name(e: dict) -> str:
    return (e.get('title') or e.get('app_name') or "").strip().lower()


def _release_key(e: dict) -> tuple:
    url = e.get('url') or e.get('release_url') or ""
    return (url.strip(), _release_name(e), (e.get('version') or "").strip().lower())


def merge_manual_releases(local_rows: list, gist_rows: list, base_rows: list = None) -> list:
    """Three-way merge of manual releases against base_rows, the Gist content at the last sync.

    A row only one side has was added there, unless base has it unchanged: then the other side
    deleted it. A row both sides have takes the local version only if it was edited since base;
    its processed flag comes from the side that changed it since base. Without a base nothing
    counts as deleted and a row processed on either side stays processed.
    """
    base = {_release_key(e): e for e in base_rows or []}
    local = {_release_key(e): e for e in local_rows}
    gist_keys = {_release_key(e) for e in gist_rows}
    gist_names = {_release_name(e) for e in gist_rows}
    merged = []
    for g in gist_rows:
        k = _release_key(g)
        l = local.get(k)
        if l is None:
            if base.get(k) != g:  # added in the Gist, or changed there after a local delete
                merged.append(g)
            continue
        b = base.get(k)
        row = dict(g) if l == b else {**g, **l}
        if b is None:
            if l.get('processed') or g.get('processed'):
                row['processed'] = True
        else:  # a stale copy cannot re-queue a published row, but a deliberate re-queue goes through
            row['processed'] = bool(l.get('processed') if bool(l.get('processed')) != bool(b.get('processed')) else g.get('processed'))
        merged.append(row)
    for l in local_rows:
        k = _release_key(l)
        if k in gist_keys or base.get(k) == l:  # merged above, or deleted in the Gist
            continue
        if base_rows is None and l.get('processed') and _release_name(l) in gist_names:
            continue  # no base: a processed row the Gist re-versioned, not a new one
        merged.append(l)
    return merged

# Written only by add_release.py on the dev machine; servers read it and never upload it, so a row
# queued there cannot be dropped by another machine's upload.
INBOX_FILE = "manual_inbox.json"


def absorb_inbox(manual_rows: list, inbox_rows: list) -> list:
    """manual_rows plus every inbox row not in it yet (matched by inbox_id or release key)."""
    ids = {r.get("inbox_id") for r in manual_rows if r.get("inbox_id")}
    keys = {_release_key(r) for r in manual_rows}
    new = [dict(r, processed=False) for r in inbox_rows
           if isinstance(r, dict) and r.get("inbox_id") and r["inbox_id"] not in ids and _release_key(r) not in keys]
    for r in new:
        logger.info(f"Queued inbox release {r.get('app_name')} {r.get('version')}")
    return manual_rows + new


def gist_file_text(file_info: dict, token: str) -> str:
    """Content of a Gist file entry, fetched from raw_url when the API truncated it."""
    if file_info.get("truncated") and file_info.get("raw_url"):
        raw_req = urllib.request.Request(file_info["raw_url"], headers=get_gist_headers(token))
        with urllib.request.urlopen(raw_req) as raw_resp:
            return raw_resp.read().decode("utf-8")
    return file_info.get("content", "")


def get_gist_headers(token: str = None) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "rutracker_bot"
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers

def normalize_target_files(files_arg, exclude_files: list = None) -> list:
    if not files_arg:
        normalized = list(FILES_TO_SYNC)
    else:
        normalized = []
        for f in files_arg:
            basename = os.path.basename(f)
            if basename in FILES_TO_SYNC:
                normalized.append(basename)
            elif f"{basename}.json" in FILES_TO_SYNC:
                normalized.append(f"{basename}.json")
            elif f"{basename}.txt" in FILES_TO_SYNC:
                normalized.append(f"{basename}.txt")
            else:
                normalized.append(basename)
    if exclude_files:
        exclude = {os.path.basename(f) for f in exclude_files}
        normalized = [f for f in normalized if f not in exclude]
    return normalized


def resolve_gist_credentials():
    """Load GIST_ID / token from env or local_settings. Returns (gist_id, token, used_github_token)."""
    gist_id = os.environ.get("GIST_ID")
    token = os.environ.get("GIST_TOKEN")
    used_github_token = False

    if not gist_id or not token:
        try:
            from core.settings_loader import settings
            gist_id = gist_id or settings.get("GIST_ID")
            if not token:
                token = settings.get("GIST_TOKEN")
                if not token:
                    token = settings.get("GITHUB_TOKEN")
                    used_github_token = bool(token)
        except Exception as e:
            logger.debug(f"Could not load Gist settings from config: {e}")

    return gist_id, token, used_github_token


def sync_eshop_state_to_gist(force: bool = True) -> bool:
    """Force-upload eShop showcase/history/last_run so digest sync cannot revive stale cards."""
    gist_id, token, used_github_token = resolve_gist_credentials()
    if not gist_id:
        logger.error("Cannot sync eShop state to Gist: GIST_ID is not set.")
        return False
    if not token:
        logger.error("Cannot sync eShop state to Gist: GIST_TOKEN/GITHUB_TOKEN is not set.")
        return False
    if used_github_token:
        logger.warning("GIST_TOKEN not set — falling back to GITHUB_TOKEN for eShop state upload.")
    try:
        upload_state(gist_id, token, force=force, target_files=ESHOP_STATE_FILES)
        return True
    except Exception as e:
        logger.error(f"Failed to upload eShop state to Gist: {e}")
        return False


def download_state(gist_id: str, token: str, target_files: list = None, exclude_files: list = None):
    sync_list = normalize_target_files(target_files, exclude_files=exclude_files)
    logger.info(f"Downloading state from Gist {gist_id} (files: {', '.join(sync_list)})...")
    url = f"https://api.github.com/gists/{gist_id}"
    req = urllib.request.Request(url, headers=get_gist_headers(token))
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    try:
        try:
            response_obj = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code == 401 and token:
                logger.warning("Authentication failed (401 Bad credentials), attempting unauthenticated download for public Gist...")
                req = urllib.request.Request(url, headers=get_gist_headers(None))
                response_obj = urllib.request.urlopen(req)
            else:
                raise

        with response_obj as response:
            gist_data = json.loads(response.read().decode())
            
            files = gist_data.get("files", {})
            for filename in sync_list:
                if filename in files:
                    content = gist_file_text(files[filename], token)
                    if filename == "list_hb.json":
                        from services.homebrew_registry import validate_registry
                        try:
                            validate_registry(json.loads(content))
                        except ValueError as e:
                            # Skip only the registry: aborting here left later files (and the upload) unsynced.
                            logger.error(f"Invalid list_hb.json in Gist, keeping local file: {e}")
                            continue
                    gist_text = content
                    filepath = os.path.join(DATA_DIR, filename)

                    # Never blindly overwrite newer local JSON (especially eshop showcase).
                    if filename.endswith(".json") and os.path.exists(filepath):
                        try:
                            with open(filepath, "r", encoding="utf-8") as lf:
                                local_content = lf.read()
                            if local_content.strip() and content.strip():
                                merged = merge_json_files(filename, local_content, content, base=load_base(filename))
                                if merged != content:
                                    logger.info(
                                        f"Download merge kept newer/local-preferred state for {filename}"
                                    )
                                content = merged
                            elif local_content.strip() and not content.strip():
                                content = local_content
                                logger.info(f"Download kept non-empty local {filename} (Gist empty)")
                        except Exception as merge_err:
                            if filename == "list_hb.json":
                                try:
                                    validate_registry(json.loads(local_content))
                                except ValueError:
                                    # Gist copy was validated above: let it repair a broken local file.
                                    logger.error(f"Local list_hb.json unusable, taking Gist copy: {merge_err}")
                                else:
                                    logger.error(f"Homebrew registry download merge failed; preserving local file: {merge_err}")
                                    continue
                            logger.warning(
                                f"Download merge failed for {filename}, using Gist content: {merge_err}"
                            )

                    if filename == "manual_releases.json" and INBOX_FILE in files:
                        try:
                            inbox = json.loads(gist_file_text(files[INBOX_FILE], token) or "[]")
                            rows = json.loads(content)
                            merged_rows = absorb_inbox(rows, inbox if isinstance(inbox, list) else [])
                            if len(merged_rows) != len(rows):
                                content = json.dumps(merged_rows, ensure_ascii=False, indent=2)
                        except ValueError as e:
                            logger.warning(f"Ignoring unreadable {INBOX_FILE}: {e}")

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    save_base(filename, gist_text)
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

def merge_json_files(filename: str, local_content: str, gist_content: str, base=None) -> str:
    """Safely merges local and Gist contents for JSON files to prevent data loss while respecting local edits.

    base is the parsed Gist registry at the last sync (see load_base).
    """
    try:
        local_data = json.loads(local_content)
        gist_data = json.loads(gist_content)
    except Exception as e:
        if filename == "list_hb.json":
            raise ValueError("Invalid homebrew registry; refusing to merge") from e
        logger.error(f"Error parsing JSON for merge ({filename}): {e}. Keeping local version.")
        return local_content

    if filename == "list_hb.json":
        from services.homebrew_registry import merge_registry
        return json.dumps(merge_registry(local_data, gist_data, base), ensure_ascii=False, indent=2)

    if filename == "manual_releases.json":
        merged_list = merge_manual_releases(
            local_data if isinstance(local_data, list) else [],
            gist_data if isinstance(gist_data, list) else [],
            base if isinstance(base, list) else None,
        )
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

    elif filename in ("last_digest_run.json", "last_homebrew_digest_run.json", "last_eshop_deals_run.json", "last_swuk_digest_run.json"):
        if not isinstance(local_data, dict): local_data = {}
        if not isinstance(gist_data, dict): gist_data = {}
        local_time = str(local_data.get("last_digest_time") or local_data.get("last_run_timestamp") or "")
        gist_time = str(gist_data.get("last_digest_time") or gist_data.get("last_run_timestamp") or "")
        if local_time >= gist_time:
            return json.dumps(local_data, ensure_ascii=False, indent=2)
        else:
            return json.dumps(gist_data, ensure_ascii=False, indent=2)

    elif filename == "eshop_posted_deals.json":
        if not isinstance(local_data, dict): local_data = {}
        if not isinstance(gist_data, dict): gist_data = {}
        merged_deals = dict(gist_data)
        for k, v in local_data.items():
            if k not in merged_deals:
                merged_deals[k] = v
            else:
                local_ts = v.get("posted_at", 0) if isinstance(v, dict) else (float(v) if isinstance(v, (int, float)) else 0)
                gist_v = merged_deals[k]
                gist_ts = gist_v.get("posted_at", 0) if isinstance(gist_v, dict) else (float(gist_v) if isinstance(gist_v, (int, float)) else 0)
                if local_ts >= gist_ts:
                    merged_deals[k] = v
        return json.dumps(merged_deals, ensure_ascii=False, indent=2)

    elif filename == "eshop_active_showcase.json":
        if not isinstance(local_data, dict): local_data = {}
        if not isinstance(gist_data, dict): gist_data = {}
        all_keys = set(local_data.keys()) | set(gist_data.keys())
        merged_showcase = {}
        for k in all_keys:
            local_items = local_data.get(k, []) if isinstance(local_data.get(k), list) else []
            gist_items = gist_data.get(k, []) if isinstance(gist_data.get(k), list) else []
            if not gist_items:
                merged_showcase[k] = local_items
            elif not local_items:
                merged_showcase[k] = gist_items
            else:
                max_local_ts = max((float(it.get("posted_at", 0)) for it in local_items if isinstance(it, dict)), default=0.0)
                max_gist_ts = max((float(it.get("posted_at", 0)) for it in gist_items if isinstance(it, dict)), default=0.0)
                max_local_msg = max((int(it.get("message_id", 0)) for it in local_items if isinstance(it, dict) and it.get("message_id")), default=0)
                max_gist_msg = max((int(it.get("message_id", 0)) for it in gist_items if isinstance(it, dict) and it.get("message_id")), default=0)

                # Local wins if it has newer posts, higher message IDs, or equal recency with >= count
                if max_local_ts > max_gist_ts or max_local_msg > max_gist_msg or (max_local_ts == max_gist_ts and len(local_items) >= len(gist_items)):
                    merged_showcase[k] = local_items
                else:
                    merged_showcase[k] = gist_items
        return json.dumps(merged_showcase, ensure_ascii=False, indent=2)

    elif filename in ("hb_state.json", "udb_state.json", "fortheusers_state.json", "vitadb_state.json", "switchports_state.json"):
        if not isinstance(local_data, dict): local_data = {}
        if not isinstance(gist_data, dict): gist_data = {}
        merged_state = dict(gist_data)
        for k, v in local_data.items():
            if k not in merged_state:
                merged_state[k] = v
            else:
                gist_v = merged_state[k]
                if isinstance(v, dict) and isinstance(gist_v, dict):
                    local_ver = str(v.get("version") or v.get("tag_name") or "")
                    gist_ver = str(gist_v.get("version") or gist_v.get("tag_name") or "")
                    local_upd = str(v.get("updated") or v.get("date") or v.get("last_updated") or v.get("comm_date") or "")
                    gist_upd = str(gist_v.get("updated") or gist_v.get("date") or gist_v.get("last_updated") or gist_v.get("comm_date") or "")
                    if filename == "fortheusers_state.json":
                        def _parse_ftu_date(s: str) -> str:
                            p = s.split("/")
                            return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}" if len(p) == 3 else s
                        norm_local_upd = _parse_ftu_date(local_upd)
                        norm_gist_upd = _parse_ftu_date(gist_upd)
                    else:
                        norm_local_upd = local_upd
                        norm_gist_upd = gist_upd
                    if norm_local_upd > norm_gist_upd or (norm_local_upd == norm_gist_upd and local_ver > gist_ver):
                        merged_state[k] = v
                else:
                    merged_state[k] = v
        return json.dumps(merged_state, ensure_ascii=False, indent=2)

    elif filename == "custom_releases_state.json":
        if not isinstance(local_data, dict): local_data = {}
        if not isinstance(gist_data, dict): gist_data = {}
        local_run = local_data.get("last_run", "") or ""
        gist_run = gist_data.get("last_run", "") or ""
        last_run = local_run if local_run >= gist_run else gist_run
        
        merged_authors = dict(gist_data.get("authors", {}))
        for auth, auth_info in local_data.get("authors", {}).items():
            if auth not in merged_authors:
                merged_authors[auth] = auth_info
            else:
                first_seen = min(auth_info.get("first_seen", ""), merged_authors[auth].get("first_seen", "")) or auth_info.get("first_seen", "") or merged_authors[auth].get("first_seen", "")
                last_checked = max(auth_info.get("last_checked", ""), merged_authors[auth].get("last_checked", ""))
                merged_authors[auth] = {"first_seen": first_seen, "last_checked": last_checked}
        
        merged_res = {
            "last_run": last_run,
            "authors": merged_authors
        }
        return json.dumps(merged_res, ensure_ascii=False, indent=2)

    return gist_content if gist_content.strip() else local_content


def upload_state(gist_id: str, token: str, force: bool = False, target_files: list = None, exclude_files: list = None):
    sync_list = normalize_target_files(target_files, exclude_files=exclude_files)
    logger.info(f"Uploading state to Gist {gist_id} (force={force}, files: {', '.join(sync_list)})...")
    
    # 1. Download current Gist content first to perform a safe merge unless force is True
    gist_files = {}
    if not force:
        try:
            url = f"https://api.github.com/gists/{gist_id}"
            req = urllib.request.Request(url, headers=get_gist_headers(token))
            try:
                response_obj = urllib.request.urlopen(req)
            except urllib.error.HTTPError as e:
                if e.code == 401 and token:
                    logger.warning("Authentication failed (401 Bad credentials) while fetching Gist state for merge, attempting unauthenticated fetch...")
                    req = urllib.request.Request(url, headers=get_gist_headers(None))
                    response_obj = urllib.request.urlopen(req)
                else:
                    raise
            with response_obj as response:
                gist_data = json.loads(response.read().decode())
                gist_files = gist_data.get("files", {})
            logger.info("Successfully fetched current Gist state for merging.")
        except Exception as e:
            # An unmerged upload would overwrite whatever other writers added since our download.
            logger.error(f"Could not fetch Gist content before upload, nothing uploaded: {e}")
            raise
    else:
        logger.info("Force flag enabled: bypassing merge, uploading local files directly.")
    
    files_payload = {}
    for filename in sync_list:
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            gist_file = gist_files.get(filename, {})
            try:
                gist_content = gist_file_text(gist_file, token)
            except Exception as e:
                logger.warning(f"Failed to fetch raw truncated content for {filename}: {e}")
                gist_content = gist_file.get("content", "")

            # Read local only after the network fetch: the runners share data/, and a local read taken
            # before a slow raw fetch wrote stale content back over another process's fresh writes.
            with open(filepath, "r", encoding="utf-8") as f:
                local_content = f.read()

            if filename == "list_hb.json":
                from services.homebrew_registry import validate_registry
                try:
                    validate_registry(json.loads(local_content))
                except ValueError as e:
                    logger.error(f"Invalid local list_hb.json, not uploading it: {e}")
                    continue
            
            # Merge logic if both Gist and local have content and force is False
            if not force and gist_content.strip() and gist_content.strip() not in ("empty", "{}") and local_content.strip():
                if filename == "list_hb.json":
                    try:
                        final_content = merge_json_files(filename, local_content, gist_content, base=load_base(filename))
                    except ValueError as e:
                        # Local was validated above: let it repair a broken Gist copy.
                        logger.error(f"Gist list_hb.json unusable, uploading local: {e}")
                        final_content = local_content
                elif filename.endswith('.json'):
                    final_content = merge_json_files(filename, local_content, gist_content, base=load_base(filename))
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
                for filename, file_data in files_payload.items():
                    save_base(filename, file_data["content"])
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
    parser.add_argument("files", nargs="*", default=None, help="Optional specific file(s) to sync (e.g. manual_releases.json)")
    parser.add_argument("-f", "--force", action="store_true", help="Force upload local files directly without merging")
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Basename to skip (repeatable), e.g. --exclude eshop_active_showcase.json. "
             "Use --exclude-eshop-state as a shortcut for Live Showcase files.",
    )
    parser.add_argument(
        "--exclude-eshop-state",
        action="store_true",
        help="Skip eshop_active_showcase.json / eshop_posted_deals.json / last_eshop_deals_run.json",
    )
    
    args = parser.parse_args()

    exclude = list(args.exclude or [])
    if args.exclude_eshop_state:
        exclude.extend(ESHOP_STATE_FILES)
    
    gist_id, token, used_github_token = resolve_gist_credentials()

    if not gist_id:
        logger.error(
            "GIST_ID is not set. Put it in config/local_settings.json or export GIST_ID. "
            "State sync is how manual_releases.json, posted_links.json and the digest "
            "files survive between runs — refusing to guess which Gist to write to."
        )
        exit(1)

    if not token:
        logger.error("GIST_TOKEN is not set (and no GITHUB_TOKEN to fall back on). "
                     "Set it in config/local_settings.json or export GIST_TOKEN.")
        exit(1)

    if used_github_token:
        logger.warning("GIST_TOKEN not set — falling back to GITHUB_TOKEN. "
                       "That token needs the 'Gists: Read and write' permission, "
                       "otherwise uploads fail with 403 and state is silently lost.")
        
    if args.action == "download":
        download_state(gist_id, token, target_files=args.files or None, exclude_files=exclude or None)
    elif args.action == "upload":
        upload_state(
            gist_id,
            token,
            force=args.force,
            target_files=args.files or None,
            exclude_files=exclude or None,
        )

if __name__ == "__main__":
    main()
