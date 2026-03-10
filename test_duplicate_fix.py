
import sys
import os
from unittest.mock import MagicMock, patch

# Mock some dependencies before importing telegram_sender
sys.modules['settings_loader'] = MagicMock()
import settings_loader
settings_loader.LOG = True
settings_loader.bot = MagicMock()
settings_loader.GROUPS = [
    {'group_name': 'Group A', 'chat_id': 123, 'topic_id': None, 'language': 'RU'},
    {'group_name': 'Group A Duplicate', 'chat_id': 123, 'topic_id': None, 'language': 'RU'},
    {'group_name': 'Group B', 'chat_id': 456, 'topic_id': 1, 'language': 'RU'}
]
settings_loader.ERROR_TG = []

from telegram_sender import send_to_telegram

def test_deduplication():
    print("Testing deduplication logic in send_to_telegram...")
    
    # Mock download functions to avoid network calls
    with patch('telegram_sender.download_cover_image_tg', return_value=None), \
         patch('telegram_sender.download_trailer_thumbnail_tg', return_value=(None, None)), \
         patch('telegram_sender.summarize_description_with_ai', side_effect=lambda x, **kwargs: x):
        
        send_to_telegram(
            title_for_caption="Test Title",
            cover_image_url=None,
            magnet_link="magnet:?xt=test",
            description="Test Description"
        )
        
        # Check how many times bot.send_message or bot.send_photo was called
        # Strategy 1 should call send_message because there are no photos
        call_count = settings_loader.bot.send_message.call_count
        print(f"Total send_message calls: {call_count}")
        
        if call_count == 2:
            print("SUCCESS: Only 2 unique groups were processed (A and B). Duplicate A was skipped.")
        else:
            print(f"FAILURE: Expected 2 calls, but got {call_count}.")

if __name__ == "__main__":
    test_deduplication()
