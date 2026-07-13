import json
import os

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manual_path = os.path.join(root_dir, "data", "manual_releases.json")
    
    with open(manual_path, "r", encoding="utf-8") as f:
        entries = json.load(f)
        
    print(f"Total entries: {len(entries)}")
    print("\nLast 10 entries in manual_releases.json:")
    for entry in entries[-10:]:
        print(f"- {entry.get('app_name')} | Version: {entry.get('version')} | URL: {entry.get('release_url')} | Processed: {entry.get('processed')}")

if __name__ == "__main__":
    main()
