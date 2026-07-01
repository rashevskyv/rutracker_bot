import json
import os

def update_names():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manual_path = os.path.join(root_dir, "data", "manual_releases.json")
    
    if not os.path.exists(manual_path):
        print(f"Error: {manual_path} not found")
        return
        
    with open(manual_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    replacements = {
        "Cr3 NX": "Cr3 NX (Chaos Rings III)",
        "Ct NX": "Ct NX (Chrono Trigger)",
        "Ff3 3d NX": "Ff3 3d NX (Final Fantasy III 3D)",
        "Ff4tay NX": "Ff4tay NX (Final Fantasy IV: The After Years)",
        "Ff4 3d NX": "Ff4 3d NX (Final Fantasy IV 3D)",
        "Ffd NX": "Ffd NX (Final Fantasy Dimensions)",
        "Gtactw NX": "Gtactw NX (GTA: Chinatown Wars)",
        "Gtalcs NX": "Gtalcs NX (GTA: Liberty City Stories)",
        "Hl2 NX": "Hl2 NX (Half-Life 2)",
        "Layton2 NX": "Layton2 NX (Professor Layton: Pandora's Box)",
        "Layton3 NX": "Layton3 NX (Professor Layton: Lost Future)",
        "Layton NX": "Layton NX (Professor Layton: Curious Village)",
        "Lswtcs NX": "Lswtcs NX (LEGO Star Wars: The Complete Saga)",
        "Lswtfa NX": "Lswtfa NX (LEGO Star Wars: The Force Awakens)",
        "Max NX V2.1.131": "Max NX (Max Payne)",
        "Openmohaa NX": "Openmohaa NX (Medal of Honor: Allied Assault)",
        "Sotn NX": "Sotn NX (Castlevania: Symphony of the Night)",
        "Tf2 NX": "Tf2 NX (Team Fortress 2)",
        "Vcmi NX": "Vcmi NX (Heroes of Might and Magic III)",
        "Armsx2 NX": "Armsx2 NX (PS2 Emulator)",
        "dusklight": "dusklight (Zelda: Twilight Princess)",
        "tmc": "tmc (Zelda: Minish Cap)",
        "Redriver2 Switch": "Redriver2 Switch (Driver 2)",
        "Coi NX": "Coi NX (Castle of Illusion)"
    }
    
    updated_count = 0
    for entry in data:
        if not entry.get("processed"):
            old_name = entry.get("app_name")
            if old_name in replacements:
                entry["app_name"] = replacements[old_name]
                print(f"Updated: '{old_name}' -> '{entry['app_name']}'")
                updated_count += 1
                
    with open(manual_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully updated {updated_count} names in manual_releases.json")

if __name__ == "__main__":
    update_names()
