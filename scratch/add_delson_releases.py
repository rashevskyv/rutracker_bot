import json
import os

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manual_path = os.path.join(root_dir, "data", "manual_releases.json")
    fetched_path = os.path.join(root_dir, "scratch", "fetched_delson.json")
    
    if not os.path.exists(manual_path):
        print("Error: manual_releases.json not found")
        return
    if not os.path.exists(fetched_path):
        print("Error: fetched_delson.json not found")
        return
        
    with open(manual_path, "r", encoding="utf-8") as f:
        manual_entries = json.load(f)
        
    with open(fetched_path, "r", encoding="utf-8") as f:
        fetched_data = json.load(f)
        
    # Check existing releases by URL
    existing_urls = {e["release_url"].strip().lower() for e in manual_entries}
    
    # Add new releases
    added_count = 0
    for repo_name, entry in fetched_data:
        url = entry["release_url"].strip().lower()
        if url not in existing_urls:
            # We add it
            manual_entries.append(entry)
            existing_urls.add(url)
            added_count += 1
            print(f"Added new release: {entry['app_name']} ({entry['version']})")
        else:
            print(f"Skipped (already exists): {entry['app_name']} ({entry['version']})")
            
    # Define mapping to update names with authors for Zelda and Castlevania
    # The rule is: if the game is already in manual releases, we add the author name next to it.
    # We will identify Zelda and Castlevania entries and apply appropriate suffix.
    
    updated_names_count = 0
    
    for entry in manual_entries:
        app_name = entry.get("app_name", "")
        url = entry.get("release_url", "")
        
        # Check if Zelda or Castlevania game
        is_zelda = "zelda" in app_name.lower() or "dusklight" in app_name.lower() or "tmc" in app_name.lower()
        is_castlevania = "castlevania" in app_name.lower() or "sotn nx" in app_name.lower()
        
        if is_zelda or is_castlevania:
            # Determine author
            author = None
            if "delsonazevedo" in url.lower():
                author = "delsonazevedo"
            elif "hayatog" in url.lower():
                author = "HayatoG"
            elif "nagaa95" in url.lower():
                author = "NaGaa95"
            elif "zeldamc_ukr" in url.lower():
                author = "ZeldaMC"
            elif "kefir_ukr" in url.lower() or "blackdragonstudio" in url.lower():
                author = "Black Dragon Studio"
                
            if author:
                # We need to construct the new app name
                new_app_name = app_name
                
                # Check if it already has the author
                if f"({author})" not in app_name and f"від {author}" not in app_name:
                    # Clean up some specific names
                    if "dusklight (Zelda: Twilight Princess від HayatoG" in app_name:
                        new_app_name = "dusklight (Zelda: Twilight Princess) (HayatoG)"
                    elif "tmc (Zelda: Minish Cap)" in app_name:
                        new_app_name = "tmc (Zelda: Minish Cap) (HayatoG)"
                    elif author == "delsonazevedo":
                        new_app_name = f"{app_name} (delsonazevedo)"
                    else:
                        new_app_name = f"{app_name} ({author})"
                        
                if new_app_name != app_name:
                    print(f"Renamed: '{app_name}' -> '{new_app_name}'")
                    entry["app_name"] = new_app_name
                    updated_names_count += 1
                    
    # Save back manual_releases.json
    with open(manual_path, "w", encoding="utf-8") as f:
        json.dump(manual_entries, f, ensure_ascii=False, indent=2)
        
    print(f"\nSummary: Added {added_count} releases. Renamed {updated_names_count} entries.")

if __name__ == "__main__":
    main()
