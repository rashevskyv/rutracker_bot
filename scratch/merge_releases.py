import json
import os

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manual_path = os.path.join(root_dir, "data", "manual_releases.json")
    generated_path = os.path.join(root_dir, "scratch", "generated_manual_releases.json")
    
    if not os.path.exists(manual_path):
        manual_entries = []
    else:
        with open(manual_path, "r", encoding="utf-8") as f:
            manual_entries = json.load(f)
            
    with open(generated_path, "r", encoding="utf-8") as f:
        generated_entries = json.load(f)
        
    # Clean up specific description for Max Payne
    for entry in generated_entries:
        if entry["app_name"] == "Max NX V2.1.131":
            entry["description"] = "Порт культової гри Max Payne для Nintendo Switch."
            
    # Deduplicate entries by (app_name, version)
    existing_keys = {(e["app_name"].lower(), e["version"].lower()) for e in manual_entries}
    
    added_count = 0
    for entry in generated_entries:
        key = (entry["app_name"].lower(), entry["version"].lower())
        if key not in existing_keys:
            manual_entries.append(entry)
            added_count += 1
            
    with open(manual_path, "w", encoding="utf-8") as f:
        json.dump(manual_entries, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully added {added_count} new entries to {manual_path} (total entries: {len(manual_entries)})")

if __name__ == "__main__":
    main()
