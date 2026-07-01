import json
import os

def rename_in_json():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    list_path = os.path.join(root_dir, "data", "list_hb.json")
    
    if not os.path.exists(list_path):
        print(f"Error: {list_path} not found")
        return
        
    with open(list_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    updated = 0
    for entry in data:
        if "category" in entry:
            entry["platform"] = entry.pop("category")
            updated += 1
            
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Renamed 'category' to 'platform' in {updated} entries in list_hb.json")

def rename_in_py():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_path = os.path.join(root_dir, "collect_homebrew_updates.py")
    
    if not os.path.exists(py_path):
        print(f"Error: {py_path} not found")
        return
        
    with open(py_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Replace references in code
    replacements = {
        "entry['category']": "entry['platform']",
        "entry.get('category'": "entry.get('platform'",
        "entry.get(\"category\"": "entry.get(\"platform\"",
        "local_entry.get('category'": "local_entry.get('platform'",
        "(for description/category)": "(for description/platform)",
        "(Vita category)": "(Vita platform)",
    }
    
    for old, new in replacements.items():
        content = content.replace(old, new)
        
    with open(py_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("Updated collect_homebrew_updates.py with 'platform' replacements")

if __name__ == "__main__":
    rename_in_json()
    rename_in_py()
