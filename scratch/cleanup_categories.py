import json
import os

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    list_path = os.path.join(root_dir, "data", "list_hb.json")
    
    if not os.path.exists(list_path):
        print(f"Error: {list_path} not found!")
        return
        
    with open(list_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    updated_count = 0
    for entry in data:
        cat = entry.get("category")
        if cat == "3DS/DS(i)":
            entry["category"] = "DS(i)"
            updated_count += 1
        elif cat == "3DS/DS(i)/Switch":
            entry["category"] = "PC/Mobile"
            updated_count += 1
            
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully cleaned up {updated_count} categories in {list_path}")

if __name__ == "__main__":
    main()
