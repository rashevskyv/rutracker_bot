import os
import re

def sanitize_files():
    scratch_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_sanitize = [
        "fetch_coi.py",
        "fetch_github_info.py",
        "fetch_new_releases.py",
        "fetch_tico.py",
        "fetch_user_list.py"
    ]
    
    loader_code = """# Load GitHub token dynamically from environment or settings
def load_github_token():
    import os
    import json
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    # Try config/local_settings.json or settings.json
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for filename in ["local_settings.json", "settings.json"]:
        path = os.path.join(root_dir, "config", filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    val = cfg.get("GITHUB_TOKEN")
                    if val and not val.startswith("os.environ"):
                        return val
            except Exception:
                pass
    return None

GITHUB_TOKEN = load_github_token()"""

    for fname in files_to_sanitize:
        fpath = os.path.join(scratch_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Replace GITHUB_TOKEN = "hardcoded..." line with loader_code
            token_prefix = "gh" + "o_"
            pattern = r'GITHUB_TOKEN\s*=\s*["\']' + token_prefix + r'[^"\']*["\']'
            new_content = re.sub(pattern, loader_code, content)
            
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Sanitized secrets in {fname}")

def delete_bak_file():
    scratch_dir = os.path.dirname(os.path.abspath(__file__))
    bak_path = os.path.join(scratch_dir, "local_settings.json.bak")
    if os.path.exists(bak_path):
        os.remove(bak_path)
        print("Deleted local_settings.json.bak")

if __name__ == "__main__":
    sanitize_files()
    delete_bak_file()
