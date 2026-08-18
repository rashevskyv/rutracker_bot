"""Service for managing user and chat notification subscriptions (RuTracker feed, digests, eShop deals)."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

USER_SUBS_FILE = os.path.join("data", "user_subscriptions.json")

VALID_SUBSCRIPTION_TYPES = {"deals", "rutracker", "digests"}


class SubscriptionService:
    """Manages granular subscriptions per chat/user for deals, tracker feed, and digests."""

    def __init__(self, filepath: str = USER_SUBS_FILE):
        self.filepath = filepath

    def _load_data(self) -> Dict[str, Any]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read user subscriptions file '{self.filepath}': {e}")
                return {}
        return {}

    def _save_data(self, data: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save user subscriptions data: {e}")

    def _get_key(self, chat_id: int, topic_id: Optional[int] = None) -> str:
        return f"{chat_id}_{topic_id}" if topic_id else str(chat_id)

    def get_subscriptions(
        self, chat_id: int, topic_id: Optional[int] = None
    ) -> Dict[str, bool]:
        """
        Get active subscription status for a chat/user.
        By default in DMs/chats, ALL automated broadcasts are False.
        """
        data = self._load_data()
        key = self._get_key(chat_id, topic_id)
        user_data = data.get(key, {})
        subs = user_data.get("subscriptions", {})
        return {
            "deals": bool(subs.get("deals", False)),
            "rutracker": bool(subs.get("rutracker", False)),
            "digests": bool(subs.get("digests", False)),
        }

    def set_subscription(
        self,
        chat_id: int,
        sub_type: str,
        enabled: bool,
        chat_type: str = "private",
        title: str = "",
        topic_id: Optional[int] = None,
        language: str = "UA",
    ) -> Dict[str, bool]:
        """
        Enable or disable a specific subscription type ('deals', 'rutracker', 'digests', 'all').
        Returns the updated subscription dictionary.
        """
        data = self._load_data()
        key = self._get_key(chat_id, topic_id)

        if key not in data:
            data[key] = {
                "chat_id": chat_id,
                "chat_type": chat_type,
                "title": title or f"Chat_{chat_id}",
                "topic_id": topic_id,
                "language": language,
                "subscriptions": {
                    "deals": False,
                    "rutracker": False,
                    "digests": False,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        subs = data[key].setdefault(
            "subscriptions", {"deals": False, "rutracker": False, "digests": False}
        )

        sub_type_clean = sub_type.lower().strip()
        if sub_type_clean == "all":
            for k in VALID_SUBSCRIPTION_TYPES:
                subs[k] = enabled
        elif sub_type_clean in VALID_SUBSCRIPTION_TYPES:
            subs[sub_type_clean] = enabled
        else:
            raise ValueError(f"Unknown subscription type: '{sub_type}'. Valid: {VALID_SUBSCRIPTION_TYPES | {'all'}}")

        data[key]["updated_at"] = datetime.now(timezone.utc).isoformat()
        if title:
            data[key]["title"] = title
        if chat_type:
            data[key]["chat_type"] = chat_type
        if topic_id is not None:
            data[key]["topic_id"] = topic_id
        if language:
            data[key]["language"] = language

        self._save_data(data)
        return {
            "deals": bool(subs.get("deals", False)),
            "rutracker": bool(subs.get("rutracker", False)),
            "digests": bool(subs.get("digests", False)),
        }

    def get_subscribers_for(self, sub_type: str) -> List[Dict[str, Any]]:
        """
        Get all active subscribers for a specific subscription type.
        Used by main.py, send_daily_digest.py, and send_eshop_deals.py.
        """
        sub_type_clean = sub_type.lower().strip()
        data = self._load_data()
        subscribers = []
        for key, record in data.items():
            subs = record.get("subscriptions", {})
            if subs.get(sub_type_clean, False):
                subscribers.append({
                    "chat_id": record.get("chat_id"),
                    "topic_id": record.get("topic_id"),
                    "title": record.get("title", f"Sub_{key}"),
                    "chat_type": record.get("chat_type", "private"),
                    "language": record.get("language", "UA"),
                })
        return subscribers
