"""sync_gist_state must refuse to guess which Gist to write to."""
import re
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).with_name("sync_gist_state.py")


def test_no_hardcoded_gist_id():
    """A 32-hex literal in the source means someone re-added the default."""
    body = SRC.read_text(encoding="utf-8")
    leftovers = re.findall(r"['\"][0-9a-f]{32}['\"]", body)
    assert not leftovers, f"hardcoded gist id back in the source: {leftovers}"


def test_missing_gist_id_is_fatal():
    """No GIST_ID anywhere -> exit 1 with an explanation, never a silent default."""
    env = {
        "PATH": __import__("os").environ.get("PATH", ""),
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
        # deliberately no GIST_ID / GIST_TOKEN
    }
    local_cfg = SRC.parent / "config" / "local_settings.json"
    original_content = None
    if local_cfg.exists():
        original_content = local_cfg.read_text(encoding="utf-8")
        try:
            cfg_dict = __import__("json").loads(original_content)
            if "GIST_ID" in cfg_dict:
                del cfg_dict["GIST_ID"]
                local_cfg.write_text(__import__("json").dumps(cfg_dict), encoding="utf-8")
        except Exception:
            pass

    try:
        r = subprocess.run(
            [sys.executable, str(SRC), "upload"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(SRC.parent), env=env,
        )
        assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
        combined = (r.stdout + r.stderr).lower()
        assert "gist_id" in combined, combined[-400:]
        assert "46128fc489e0fd60e226ff26dc638e97" not in combined
    finally:
        if original_content is not None:
            local_cfg.write_text(original_content, encoding="utf-8")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  {name} ok")
    print("gist config ok")
