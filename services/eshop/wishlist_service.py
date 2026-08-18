"""Service for managing user and chat eShop wishlists with persistent storage."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WISHLIST_FILE = os.path.join("data", "eshop_wishlist.json")


class WishlistService:
    """Handles wishlist operations per user or chat."""

    def __init__(self, filepath: str = WISHLIST_FILE):
        self.filepath = filepath

    def _load_data(self) -> Dict[str, Any]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read wishlist file '{self.filepath}': {e}")
                return {}
        return {}

    def _save_data(self, data: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save wishlist data: {e}")

    def _get_key(self, chat_id: int, topic_id: Optional[int] = None) -> str:
        return f"{chat_id}_{topic_id}" if topic_id else str(chat_id)

    def add_game(
        self,
        chat_id: int,
        title: str,
        nsuid: Optional[str] = None,
        fs_id: Optional[str] = None,
        topic_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Add a game to the wishlist for a specific chat/topic.
        Returns the added item dict.
        """
        data = self._load_data()
        key = self._get_key(chat_id, topic_id)
        if key not in data:
            data[key] = {
                "chat_id": chat_id,
                "topic_id": topic_id,
                "items": [],
            }

        items: List[Dict[str, Any]] = data[key].setdefault("items", [])

        # Check if already exists (case-insensitive)
        clean_title = title.strip()
        for item in items:
            if item.get("title", "").lower() == clean_title.lower():
                return item

        now_iso = datetime.now(timezone.utc).isoformat()
        new_item = {
            "title": clean_title,
            "nsuid": nsuid,
            "fs_id": fs_id,
            "added_at": now_iso,
            "last_notified_discount": None,
        }
        items.append(new_item)
        self._save_data(data)
        return new_item

    def remove_game(
        self, chat_id: int, title: str, topic_id: Optional[int] = None
    ) -> bool:
        """Remove a game from the wishlist. Returns True if removed."""
        data = self._load_data()
        key = self._get_key(chat_id, topic_id)
        if key not in data:
            return False

        items: List[Dict[str, Any]] = data[key].get("items", [])
        clean_title = title.strip().lower()
        initial_len = len(items)
        data[key]["items"] = [
            item for item in items if clean_title not in item.get("title", "").lower()
        ]

        if len(data[key]["items"]) < initial_len:
            self._save_data(data)
            return True
        return False

    def get_wishlist(
        self, chat_id: int, topic_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve all wishlist items for a given chat/topic."""
        data = self._load_data()
        key = self._get_key(chat_id, topic_id)
        return data.get(key, {}).get("items", [])

    def clear_wishlist(self, chat_id: int, topic_id: Optional[int] = None) -> bool:
        """Clear all items for a given chat/topic."""
        data = self._load_data()
        key = self._get_key(chat_id, topic_id)
        if key in data:
            data[key]["items"] = []
            self._save_data(data)
            return True
        return False

    def get_all_wishlists(self) -> Dict[str, Any]:
        """Return full dictionary of all registered wishlists."""
        return self._load_data()

    def update_notification(
        self, key: str, title: str, discount_percent: float
    ) -> None:
        """Mark a wishlist item as notified for the given discount."""
        data = self._load_data()
        if key in data:
            for item in data[key].get("items", []):
                if item.get("title", "").lower() == title.lower():
                    item["last_notified_discount"] = discount_percent
                    item["last_notified_at"] = datetime.now(timezone.utc).isoformat()
                    break
            self._save_data(data)
