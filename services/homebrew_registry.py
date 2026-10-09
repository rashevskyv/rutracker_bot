"""Discover source repositories in RuTracker homebrew posts and register update tracking."""
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

logger = logging.getLogger(__name__)
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "list_hb.json"
MANUAL_PATH = REGISTRY_PATH.with_name("manual_releases.json")


def repository_api_url(url: str) -> str:
    """Canonical supported API URL, or empty for non-repository links."""
    if not isinstance(url, str):
        return ""
    try:
        parsed = urlsplit(url.strip())
        if (parsed.scheme not in {"https", "http"} or parsed.username or parsed.password
                or parsed.port not in {None, 443}):
            return ""
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    parts = parsed.path.strip("/").split("/")
    if host == "api.github.com" and parts[:1] == ["repos"]:
        parts = parts[1:]
        host = "github.com"
    if host in {"github.com", "www.github.com"}:
        if len(parts) < 2 or parts[0].lower() in {"orgs", "users", "topics", "settings", "features", "search"}:
            return ""
        owner, repo = parts[:2]
        repo = repo.removesuffix(".git")
        if not re.fullmatch(r"[A-Za-z0-9-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo) or repo in {".", ".."}:
            return ""
        return f"https://api.github.com/repos/{owner}/{repo}".lower()
    if host == "gitlab.com":
        if parts[:3] == ["api", "v4", "projects"]:
            project = unquote(parts[3]) if len(parts) >= 4 else ""
        else:
            project = "/".join(parts[:parts.index("-")] if "-" in parts else parts)
            project = project.removesuffix(".git")
        if not project or (not project.isdigit() and "/" not in project):
            return ""
        if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in {".", ".."} for part in project.split("/")):
            return ""
        # GitLab project paths are case-sensitive; numeric project IDs are preferred after lookup.
        return f"https://gitlab.com/api/v4/projects/{quote(project, safe='')}/releases"
    return ""


def source_urls(post_body) -> list:
    """Read links before description cleaning removes spoilers or source sections."""
    links = [a["href"] for a in post_body.find_all("a", href=True)]
    links.extend(re.findall(r'https?://[^\s<>"\']+', post_body.get_text(" ")))
    return sorted({api for link in links if (api := repository_api_url(link.rstrip(".,);]")))})


def load_registry(path: Path) -> list:
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Invalid registry: {path.name}")
    if path == REGISTRY_PATH:
        validate_registry(rows)
    return rows


def validate_registry(rows):
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not repository_api_url(row.get("api_url", "")) for row in rows):
        raise ValueError("Invalid homebrew registry; refusing to overwrite")


def tracked_api_urls(rows: list) -> set:
    return {api for row in rows for field in ("api_url", "release_url", "url")
            if (api := repository_api_url(row.get(field, "")))}


def merge_registry(local: list, remote: list, base=None) -> list:
    """Keep independent additions and remote metadata; honor deletions of unchanged base rows."""
    validate_registry(local)
    validate_registry(remote)
    key = lambda row: repository_api_url(row["api_url"])
    previous = {key(row): row for row in base
                if isinstance(row, dict) and repository_api_url(row.get("api_url", ""))} if isinstance(base, list) else {}
    local_by_key = {key(row): row for row in local}
    remote_keys = {key(row) for row in remote}
    merged = []
    seen = set()
    for row in remote:
        identity = key(row)
        # Existing aliases can share a repository; preserve their distinct metadata.
        if row in merged or (identity not in local_by_key and previous.get(identity) == row):
            continue
        merged.append(row)
        seen.add(identity)
    for row in local:
        identity = key(row)
        if identity in seen or identity in remote_keys or previous.get(identity) == row:
            continue
        merged.append(row)
        seen.add(identity)
    return merged


async def register_tracker_homebrew(title: str, urls: list) -> bool:
    """Register a single explicit source; failures must not prevent the RuTracker post."""
    candidates = {api for url in urls if (api := repository_api_url(url))}
    if len(candidates) != 1:
        logger.warning("Homebrew tracking skipped for %s: %d source repositories", title, len(candidates))
        return False
    api_url = candidates.pop()
    try:
        rows = load_registry(REGISTRY_PATH)
        manual = [row for row in load_registry(MANUAL_PATH) if row.get("type") == "homebrew"]
        if api_url in tracked_api_urls(rows + manual):
            return False
        from core.settings_loader import get_session
        metadata_url = api_url.removesuffix("/releases") if "gitlab.com" in api_url else api_url
        async with get_session().get(metadata_url, timeout=15, allow_redirects=False) as response:
            if response.status != 200:
                # shortcut: lookup failures retry on later topic updates; add a pending queue if outages become frequent.
                logger.warning("Homebrew source lookup failed for %s: HTTP %s", api_url, response.status)
                return False
            metadata = await response.json()
        if "gitlab.com" in api_url:
            project_id = metadata.get("id")
            if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id <= 0:
                raise ValueError("GitLab returned no project ID")
            api_url = f"https://gitlab.com/api/v4/projects/{project_id}/releases"
        elif repository_api_url(metadata.get("html_url", "")) != api_url:
            raise ValueError("GitHub returned a different repository")
        name = metadata.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Source returned no repository name")
        # Re-read after the request: another runner may have added rows while it was in flight.
        rows = load_registry(REGISTRY_PATH)
        manual = [row for row in load_registry(MANUAL_PATH) if row.get("type") == "homebrew"]
        if api_url in tracked_api_urls(rows + manual):
            return False
        rows.append({
            "app_name": name.strip(), "api_url": api_url, "platform": "Switch",
            "description": "", "prefix": "", "new": False,
            # The torrent was already announced; watch changes from discovery onward.
            "comm_date": datetime.now(timezone.utc).isoformat(),
        })
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=REGISTRY_PATH.parent,
                                             prefix=".list_hb-", suffix=".tmp", delete=False) as stream:
                temp_path = Path(stream.name)
                json.dump(rows, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temp_path, REGISTRY_PATH)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        logger.info("Registered RuTracker homebrew for Switch updates: %s (%s)", name, api_url)
        return True
    except Exception:
        logger.exception("Could not register RuTracker homebrew: %s", title)
        return False
