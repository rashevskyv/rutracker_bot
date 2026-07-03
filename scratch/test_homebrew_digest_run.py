import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import settings_loader and force IS_TEST_MODE to True
import core.settings_loader
core.settings_loader.IS_TEST_MODE = True

# Also override the setting dictionary's 'test' value
core.settings_loader.settings['test'] = True

# Now import send_homebrew_digest functions
from send_homebrew_digest import send_digest
from core.settings_loader import close_clients

async def run_test():
    print("Running send_digest in TEST mode...")
    await send_digest()
    await close_clients()

if __name__ == "__main__":
    asyncio.run(run_test())
