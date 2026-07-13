import json
import os

def check():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manual_path = os.path.join(root_dir, "data", "manual_releases.json")
    
    if not os.path.exists(manual_path):
        print("manual_releases.json not found")
        return
        
    with open(manual_path, "r", encoding="utf-8") as f:
        entries = json.load(f)
        
    keywords = ["zelda", "celeste", "battleship", "starship", "castlevania", "crazy", "taxi", "openbor"]
    
    print("Matches in manual_releases.json:")
    for entry in entries:
        app_name = entry.get("app_name", "").lower()
        release_url = entry.get("release_url", "").lower()
        description = entry.get("description", "").lower()
        
        matches = [kw for kw in keywords if kw in app_name or kw in release_url or kw in description]
        if matches:
            print(f"- App: {entry.get('app_name')}")
            print(f"  Version: {entry.get('version')}")
            print(f"  URL: {entry.get('release_url')}")
            print(f"  Matched keywords: {matches}")
            print(f"  Processed: {entry.get('processed')}")
            print()

if __name__ == "__main__":
    check()
