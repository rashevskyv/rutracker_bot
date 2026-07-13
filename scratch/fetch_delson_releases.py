import asyncio
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings_loader import get_session, close_clients
from services.translation import translate_short_description
from scratch.fetch_new_releases import load_github_token, github_request, get_repo_details, process_repo

async def main():
    session = get_session()
    
    repos = [
        ("delsonazevedo", "Zelda-LA-DX-HD-Updated", "Zelda: Link's Awakening DX HD"),
        ("delsonazevedo", "Celeste64-Switch", "Celeste 64"),
        ("delsonazevedo", "BattleShip-Switch", "BattleShip"),
        ("delsonazevedo", "Starship", "Starship"),
        ("delsonazevedo", "Castlevania-ReVamped-Open-Source-Edition-Switch", "Castlevania: ReVamped - Open Source Edition"),
        ("delsonazevedo", "crazytaxy_nx", "Crazy Taxi NX"),
        ("delsonazevedo", "openbor", "OpenBOR")
    ]
    
    # Load manual releases to find existing entries
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manual_path = os.path.join(root_dir, "data", "manual_releases.json")
    
    if not os.path.exists(manual_path):
        manual_entries = []
    else:
        with open(manual_path, "r", encoding="utf-8") as f:
            manual_entries = json.load(f)
            
    # Keywords to detect existing games
    # Zelda and Castlevania are already known to be in manual releases.
    # Let's check which authors they have, and compile the final lists.
    
    fetched_data = []
    for owner, repo_name, custom_name in repos:
        print(f"Fetching {owner}/{repo_name}...")
        details = await get_repo_details(session, owner, repo_name)
        if details:
            entry = await process_repo(details, custom_name)
            fetched_data.append((repo_name, entry))
        else:
            print(f"Could not fetch {owner}/{repo_name}", file=sys.stderr)
            
    output_path = os.path.join(root_dir, "scratch", "fetched_delson.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fetched_data, f, ensure_ascii=False, indent=2)
        
    print(f"Fetched {len(fetched_data)} repos and saved to {output_path}")
    await close_clients()

if __name__ == "__main__":
    asyncio.run(main())
