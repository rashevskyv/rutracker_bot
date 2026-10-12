"""Add the GitHub repo of each new homebrew digest item to the Emu Radar Store (manual.json).

Hook: digest/homebrew.py flags an entry "pending" only when add_entry appends it. Every homebrew
source (collectors and manual releases) goes through that call, so each new item is flagged once.
send_homebrew_digest.py calls sync_pending_digest_items() before the send. Legacy entries have no flag,
so the first run after deploy does not flood the store.

Every failure is logged and never raised. Outcome per item: added, exists, no_repo, skipped_platform
(done) or failed, deferred (kept pending, retried on the next digest run).
"""
import asyncio
import html
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.request
from typing import Dict, List, Optional

from services import gpt, store_manual

logger = logging.getLogger(__name__)

CATALOG_URL = f"https://raw.githubusercontent.com/{store_manual.STORE_REPO}/main/catalog.json"
SECTION = "Digest"
MAX_ADDS = 20          # additions per run; more items stay pending for the next run
BUDGET_S = 60.0        # whole step; checked before each item
LLM_TIMEOUT_S = 15.0   # one repo-finding call (gpt.complete may try 3 models)
PAGE_TIMEOUT_S = 10.0
PAGE_MAX_BYTES = 300_000
PAGE_TEXT_CHARS = 6000
DONE = ("added", "exists", "no_repo", "skipped_platform")

# First path segments of github.com that are not user or org repos.
RESERVED_OWNERS = {"orgs", "sponsors", "topics", "marketplace", "apps", "users", "settings", "features",
                   "collections", "explore", "login", "search", "notifications", "about", "pricing", "enterprise"}
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_LINK_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.IGNORECASE)

EMU_RE = re.compile(r"\bemu\w*|\bfork\w*|libretro", re.IGNORECASE)
EMU_RE_UK = re.compile(r"форк|емул")
TOOL_RE = re.compile(r"\b(utilit\w*|installer|player|module|compiler|manager|scripts?|drivers?|librar(y|ies)|tools?)\b",
                     re.IGNORECASE)
TOOL_RE_UK = re.compile(r"утиліт|інсталятор|плеєр|модуль|компілятор|менеджер|скрипт|драйвер|бібліотек")


def sync_enabled(env=None, which=shutil.which) -> bool:
    """STORE_SYNC=0 turns the step off. Otherwise it runs only when gh is installed (writes need it)."""
    env = os.environ if env is None else env
    if str(env.get("STORE_SYNC", "")).strip() == "0":
        return False
    return which("gh") is not None


def is_switch(platform) -> bool:
    """'Switch' or 'Nintendo Switch' yes. '3DS/DS(i)/Switch' no: a multi-console label is not a Switch-only release."""
    parts = [p.strip().lower() for p in str(platform or "").split("/") if p.strip()]
    return bool(parts) and all("switch" in p for p in parts)


def github_repo_from_url(url: str) -> Optional[str]:
    """'https://github.com/owner/repo/releases/tag/v1' -> 'owner/repo'. None for orgs, gists, non-GitHub."""
    repo = store_manual.repo_from_url(url or "")
    if repo is None or repo.split("/")[0].lower() in RESERVED_OWNERS:
        return None
    return repo


def category_for(title: str, description: str) -> str:
    """Keyword heuristic: emulator/fork -> emu, utility/tool words -> tool, otherwise port."""
    text = f"{title} {description}"
    if EMU_RE.search(text) or EMU_RE_UK.search(text.lower()):
        return "emu"
    if TOOL_RE.search(text) or TOOL_RE_UK.search(text.lower()):
        return "tool"
    return "port"


def store_title(app_name: str, owner: str) -> str:
    """'Name (owner)' -> 'Name'. Other parentheses are kept."""
    m = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", app_name or "")
    if m and m.group(2).strip().lower() == owner.lower() and m.group(1).strip():
        return m.group(1).strip()
    return (app_name or "").strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _fetch_page(url: str) -> Optional[str]:
    """Raw text of a web page, bounded in size and time. None when the link is not a web page."""
    if not url.startswith(("http://", "https://")):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "RuTracker-Bot-StoreSync/1.0"})
    with urllib.request.urlopen(req, timeout=PAGE_TIMEOUT_S) as r:
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            return None
        raw = r.read(PAGE_MAX_BYTES)
    return raw.decode("utf-8", errors="replace")


def _page_for_llm(raw: str) -> str:
    """GitHub links first (they survive truncation), then the visible text."""
    links = list(dict.fromkeys(m.group(1) for m in GITHUB_LINK_RE.finditer(raw)))
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    text = _clean(body)
    prefix = "GitHub links on the page: " + ", ".join(links) + "\n" if links else ""
    return (prefix + text)[:PAGE_TEXT_CHARS]


async def ask_repo(item: Dict, page_text: str) -> Optional[str]:
    """Ask the bot's LLM for the project's GitHub repo. Returns 'owner/name' or None. Raises on LLM failure."""
    prompt = (
        "Find the GitHub repository of this Nintendo Switch homebrew project. "
        "Its release link is not a GitHub link. Use only the page text below. "
        'Reply with JSON only: {"repo": "owner/name" or null, "reason": "short reason"}. '
        "The repo must be the project's own repository that hosts the Switch release, and it must appear "
        "in the page text as github.com/owner/name. Never invent a repo. If unsure, return null.\n\n"
        f"App: {item.get('app_name', '')}\nRelease link: {item.get('release_url', '')}\n"
        f"Description: {_clean(item.get('description', ''))[:500]}\n\nPage text:\n{page_text}"
    )
    out = await gpt.complete(prompt, max_tokens=200, temperature=0, label="store-sync")
    if out is None:
        raise RuntimeError("LLM unavailable")  # an outage is not a "no repo" verdict
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    repo = json.loads(m.group(0)).get("repo")
    if not isinstance(repo, str):
        return None
    repo = repo.strip().strip("/")
    return repo if REPO_RE.match(repo) else None


def repo_exists(repo: str, run=subprocess.run) -> bool:
    """True if gh can read the repo, False on HTTP 404. Any other failure raises."""
    r = run(["gh", "api", f"repos/{repo}", "--jq", ".full_name"], capture_output=True, text=True, timeout=15)
    if r.returncode == 0:
        return True
    if "HTTP 404" in (r.stderr or ""):
        return False
    raise RuntimeError(f"gh api repos/{repo} failed")


def load_store_state(run=subprocess.run, which=shutil.which, fetch_json=None) -> set:
    """Lower-cased repos known to the store: catalog.json entries plus every manual.json row (disabled too).

    Raises when either file cannot be read. Writing without this list could create duplicates.
    """
    if fetch_json is None:
        def fetch_json(url):
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "RuTracker-Bot-StoreSync/1.0"}),
                                        timeout=PAGE_TIMEOUT_S) as r:
                return json.loads(r.read().decode("utf-8"))
    catalog = fetch_json(CATALOG_URL)
    rows = store_manual.read_manual_rows(run=run, which=which)
    if rows is None:
        raise RuntimeError("manual.json unreadable")
    repos = {str(e.get("repo", "")).lower() for e in catalog.get("entries", []) if isinstance(e, dict)}
    repos |= {str(r.get("repo", "")).lower() for r in rows if isinstance(r, dict)}
    return repos


async def sync_new_homebrew_to_store(items: List[Dict], *, run=subprocess.run, which=shutil.which,
                                     fetch=_fetch_page, ask=ask_repo, exists=repo_exists,
                                     load=load_store_state, add=store_manual.add_manual_rows,
                                     clock=time.monotonic) -> Dict[str, str]:
    """Process new homebrew digest items. Returns {release_url: outcome}. Never raises."""
    outcomes: Dict[str, str] = {}
    if not items:
        return outcomes
    if not sync_enabled(which=which):
        logger.info("store-sync: off (STORE_SYNC=0 or gh not found); %d item(s) stay pending", len(items))
        return outcomes

    def done(item, outcome, msg):
        outcomes[item.get("release_url", "")] = outcome
        logger.info("store-sync: %s | %s | %s", outcome, item.get("app_name", "?"), msg)

    switch_items = []
    for item in items:
        if is_switch(item.get("platform")):
            switch_items.append(item)
        else:
            done(item, "skipped_platform", f"platform {item.get('platform')!r} is not Switch-only")

    try:
        known = await asyncio.to_thread(load, run, which)
    except Exception as e:
        logger.warning("store-sync: store state unreadable (%s); %d item(s) stay pending", type(e).__name__, len(switch_items))
        for item in switch_items:
            outcomes[item.get("release_url", "")] = "deferred"
        return outcomes

    deadline = clock() + BUDGET_S
    llm_ok = True
    to_add: List[Dict] = []
    for item in switch_items:
        url = item.get("release_url", "")
        if clock() > deadline:
            outcomes[url] = "deferred"
            continue
        repo = github_repo_from_url(url)
        if repo is None:
            if not llm_ok:
                outcomes[url] = "failed"
                continue
            try:
                raw = await asyncio.to_thread(fetch, url)
            except Exception as e:
                outcomes[url] = "failed"
                logger.warning("store-sync: page fetch failed for %s: %s", url, type(e).__name__)
                continue
            if raw is None:
                done(item, "no_repo", f"not a web page: {url}")
                continue
            try:
                repo = await asyncio.wait_for(ask(item, _page_for_llm(raw)), LLM_TIMEOUT_S)
            except Exception as e:
                llm_ok = False  # stop calling the LLM for the rest of this run
                outcomes[url] = "failed"
                logger.warning("store-sync: LLM failed (%s); remaining links wait for the next run", type(e).__name__)
                continue
            if repo and f"github.com/{repo}".lower() not in raw.lower():
                repo = None  # the model named a repo the page never links to
            if not repo:
                done(item, "no_repo", f"no GitHub repo for {url}")
                continue
        if repo.lower() in known:
            done(item, "exists", f"{repo} already in store")
            continue
        if len(to_add) >= MAX_ADDS:
            outcomes[url] = "deferred"
            continue
        try:
            ok = await asyncio.to_thread(exists, repo)
        except Exception as e:
            outcomes[url] = "failed"
            logger.warning("store-sync: repo check failed for %s: %s", repo, type(e).__name__)
            continue
        if not ok:
            done(item, "no_repo", f"{repo} does not exist on GitHub")
            continue
        owner = repo.split("/")[0]
        category = category_for(store_title(item.get("app_name", ""), owner), _clean(item.get("description", "")))
        to_add.append({"repo": repo, "title": store_title(item.get("app_name", ""), owner),
                       "section": SECTION, "category": category, "_item": item})
        known.add(repo.lower())

    if to_add:
        rows = [{k: v for k, v in r.items() if k != "_item"} for r in to_add]
        try:
            note, added = await asyncio.to_thread(add, rows, run=run, which=which)
        except Exception as e:
            note, added = f"store: WARNING write failed ({type(e).__name__})", []
        for r in to_add:
            item = r["_item"]
            if note.startswith("store: WARNING"):
                outcomes[item.get("release_url", "")] = "failed"
                logger.warning("store-sync: %s", note)
            elif r["repo"] in added:
                done(item, "added", f"{r['repo']} as {r['category']} ({r['title']})")
            else:
                done(item, "exists", f"{r['repo']} was already in store")
    return outcomes


async def sync_pending_digest_items(manager, **deps) -> Dict[str, str]:
    """Run the step for the homebrew digest's pending entries and mark the decided ones done."""
    pending = manager.pending_store_sync()
    if not pending:
        return {}
    outcomes = await sync_new_homebrew_to_store(pending, **deps)
    for url, outcome in outcomes.items():
        if outcome in DONE:
            manager.set_store_sync(url, "done")
    return outcomes
