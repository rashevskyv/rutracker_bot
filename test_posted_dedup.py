"""Feed deduplication: [Обновлено] entries must not repost when the run re-reads an old feed tail."""
import time
from datetime import datetime, timedelta

import main

LINK = "https://rutracker.org/forum/viewtopic.php?t=1"


def entry(updated: datetime):
    return {"link": LINK, "updated_parsed": time.gmtime(updated.timestamp())}


def posted(at: datetime):
    # main.save_posted_link stores naive local time
    return {LINK: at.replace(tzinfo=None).isoformat()}


def test_new_topic_posted_once():
    now = datetime.now()
    assert main.is_already_posted(entry(now), posted(now - timedelta(days=1)), is_updated=False)
    assert not main.is_already_posted(entry(now), {}, is_updated=False)


def test_update_seen_before_our_post_is_skipped():
    now = datetime.now().astimezone()
    assert main.is_already_posted(entry(now - timedelta(minutes=10)), posted(now), is_updated=True)


def test_update_after_our_post_is_announced():
    now = datetime.now().astimezone()
    assert not main.is_already_posted(entry(now), posted(now - timedelta(days=1)), is_updated=True)


def test_update_without_feed_time_is_announced():
    assert not main.is_already_posted({"link": LINK}, posted(datetime.now()), is_updated=True)
