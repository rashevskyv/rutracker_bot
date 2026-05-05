"""
Migration script: Split list_hb.json into static registry + dynamic state.

Run once on the server to create data/hb_state.json from existing data/list_hb.json,
and list_hb.json (static registry) in the repo root.

Usage:
    python migrate_hb_state.py
"""
import json
import os
import sys

STATIC_FIELDS = ['category', 'app_name', 'api_url', 'description', 'prefix', 'new']
DYNAMIC_FIELDS = ['comm_date', 'tag_name', 'html_url']

OLD_LIST_PATH = os.path.join('data', 'list_hb.json')
NEW_REGISTRY_PATH = os.path.join('data', 'list_hb.json')
STATE_PATH = os.path.join('data', 'hb_state.json')


def migrate():
    # Determine source: prefer data/list_hb.json (server), fallback to list_hb.json (dev)
    source_path = OLD_LIST_PATH if os.path.exists(OLD_LIST_PATH) else NEW_REGISTRY_PATH

    if not os.path.exists(source_path):
        print(f"ERROR: Source file not found: {source_path}")
        sys.exit(1)

    print(f"Reading source: {source_path}")
    with open(source_path, 'r', encoding='utf-8') as f:
        entries = json.load(f)

    print(f"Loaded {len(entries)} entries")

    # Build state dict (keyed by api_url)
    state = {}
    for entry in entries:
        api_url = entry.get('api_url', '')
        if not api_url:
            continue
        state[api_url] = {}
        for field in DYNAMIC_FIELDS:
            if field in entry:
                state[api_url][field] = entry[field]

    # Build static registry (only static fields)
    registry = []
    for entry in entries:
        static_entry = {}
        for field in STATIC_FIELDS:
            if field in entry:
                static_entry[field] = entry[field]
        registry.append(static_entry)

    # Write state
    os.makedirs('data', exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"Created {STATE_PATH} with {len(state)} entries")

    # Write static registry
    with open(NEW_REGISTRY_PATH, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    print(f"Created {NEW_REGISTRY_PATH} with {len(registry)} entries")

    if len(state) != len(registry):
        print(f"Note: Entry count mismatch (State: {len(state)}, Registry: {len(registry)}). This is normal if multiple apps share the same repository.")
    print(f"\nMigration complete! You can now safely delete {OLD_LIST_PATH} if needed.")


if __name__ == '__main__':
    migrate()
