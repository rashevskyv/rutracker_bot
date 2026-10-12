"""Mirror GitHub repos into the Emu Radar Store's manual.json.

Best effort: every failure returns a warning string. The caller must never fail because of the store.
Auth comes from the local `gh` login; no token is read or stored here.
"""
import base64
import json
import shutil
import subprocess
from urllib.parse import urlparse

STORE_REPO = "rashevskyv/emuradar-store"
MANUAL_PATH = "manual.json"
GITHUB_HOSTS = ("github.com", "www.github.com")


def repo_from_url(url):
    """'https://github.com/owner/repo/releases/tag/v1' -> 'owner/repo'. None for non-GitHub URLs."""
    u = urlparse(url)
    if u.netloc.lower() not in GITHUB_HOSTS:
        return None
    parts = u.path.strip("/").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    name = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    return f"{parts[0]}/{name}"


def upsert(rows, repo):
    """Return (rows, changed). Adds {"repo": repo} or, for a known repo, clears its "disabled" flag.

    Only the repo key and the disabled flag are written, so SwitchPorts fields stay as they are.
    """
    for row in rows:
        if str(row.get("repo", "")).lower() == repo.lower():
            if row.get("disabled") is True:
                row.pop("disabled")
                return rows, True
            return rows, False
    return rows + [{"repo": repo}], True


def has_repo(rows, repo):
    """True when any row (enabled or disabled) names the repo, case-insensitively."""
    return any(str(r.get("repo", "")).lower() == repo.lower() for r in rows)


def _gh(run, args, stdin=None, timeout=60):
    return run(["gh", "api", *args], input=stdin, capture_output=True, text=True, check=True, timeout=timeout).stdout


def _edit_manual(label, mutate, run=subprocess.run, which=shutil.which):
    """Read manual.json, let mutate(rows) -> (rows, changed, note), write it back with the read sha.

    Returns the note. A conflicting write (409) re-reads once. Never raises.
    """
    if which("gh") is None:
        return f"store: WARNING gh not found, {label} not added to the Emu Radar Store"
    path = f"repos/{STORE_REPO}/contents/{MANUAL_PATH}"
    try:
        for _attempt in range(2):  # a second try re-reads the file if the sha moved (409)
            try:
                meta = json.loads(_gh(run, [path]))
                rows = json.loads(base64.b64decode(meta["content"]).decode("utf-8"))
                if not isinstance(rows, list):
                    return f"store: WARNING {MANUAL_PATH} is not a list, {label} not added"
                rows, changed, note = mutate(rows)
                if not changed:
                    return note
                body = {
                    "message": f"manual: add {label}",
                    "content": base64.b64encode((json.dumps(rows, indent=2, ensure_ascii=False) + "\n").encode("utf-8")).decode("ascii"),
                    "sha": meta["sha"],
                    "branch": "main",
                }
                _gh(run, ["-X", "PUT", path, "--input", "-"], stdin=json.dumps(body))
                return note
            except subprocess.CalledProcessError:
                continue
        return f"store: WARNING could not update {MANUAL_PATH} for {label} (gh call failed)"
    except Exception as e:  # malformed JSON, missing keys, no network: never fail the queue
        return f"store: WARNING could not update {MANUAL_PATH} for {label}: {type(e).__name__}"


def read_manual_rows(run=subprocess.run, which=shutil.which):
    """Return the store's manual.json rows, or None when they cannot be read safely."""
    if which("gh") is None:
        return None
    try:
        meta = json.loads(_gh(run, [f"repos/{STORE_REPO}/contents/{MANUAL_PATH}"], timeout=30))
        rows = json.loads(base64.b64decode(meta["content"]).decode("utf-8"))
        return rows if isinstance(rows, list) else None
    except Exception:
        return None


def add_manual_rows(new_rows, run=subprocess.run, which=shutil.which):
    """Append rows {"repo": ..., ...} that no row already names. One read, one write.

    Repos already present (even disabled) are left alone. Returns (note, added_repos).
    """
    added = []

    def mutate(rows):
        added.clear()  # a 409 retry re-runs mutate on the fresh file
        for row in new_rows:
            if not has_repo(rows, row["repo"]):
                rows.append(dict(row))
                added.append(row["repo"])
        if not added:
            return rows, False, f"store: all rows already in {MANUAL_PATH}"
        return rows, True, f"store: added {', '.join(added)} to {MANUAL_PATH}"

    note = _edit_manual("batch", mutate, run=run, which=which)
    return note, list(added) if note.startswith("store: added") else []


def sync_release(url, run=subprocess.run, which=shutil.which):
    """Add the release's GitHub repo to the store's manual.json. Returns a short status line."""
    repo = repo_from_url(url)
    if repo is None:
        return f"store: skipped, not a GitHub repo: {url}"

    def mutate(rows):
        rows, changed = upsert(rows, repo)
        if not changed:
            return rows, False, f"store: {repo} already in {MANUAL_PATH}"
        return rows, True, f"store: added {repo} to {MANUAL_PATH}"

    return _edit_manual(repo, mutate, run=run, which=which)
