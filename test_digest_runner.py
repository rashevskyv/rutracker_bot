"""Guards for the shared digest plumbing: cooldown, targets, send loop."""
import asyncio
import json
import os
import tempfile
import types
from datetime import datetime, timedelta

from digest import runner


def test_last_run_roundtrip():
    path = os.path.join(tempfile.mkdtemp(), "last.json")

    # missing file -> now minus the default age
    got = runner.get_last_run_time(path, timedelta(days=7))
    assert timedelta(days=6, hours=23) < datetime.now() - got < timedelta(days=7, hours=1)

    runner.save_last_run_time(path)
    assert datetime.now() - runner.get_last_run_time(path, timedelta(days=7)) < timedelta(minutes=1)

    # corrupt file -> falls back, does not raise
    open(path, "w", encoding="utf-8").write("{not json")
    assert datetime.now() - runner.get_last_run_time(path, timedelta(hours=24)) > timedelta(hours=23)


def test_cooldown():
    just_now = datetime.now() - timedelta(hours=1)
    long_ago = datetime.now() - timedelta(hours=21)
    orig_mode, orig_env = runner.IS_TEST_MODE, os.environ.get('FORCE_TASK')
    try:
        runner.IS_TEST_MODE = False
        os.environ.pop('FORCE_TASK', None)
        assert runner.in_cooldown(just_now, 'run_x', 'X') is True
        assert runner.in_cooldown(long_ago, 'run_x', 'X') is False

        # FORCE_TASK overrides, but only for the matching task
        os.environ['FORCE_TASK'] = 'run_x'
        assert runner.in_cooldown(just_now, 'run_x', 'X') is False
        assert runner.in_cooldown(just_now, 'run_y', 'Y') is True

        # test mode never cools down
        os.environ.pop('FORCE_TASK', None)
        runner.IS_TEST_MODE = True
        assert runner.in_cooldown(just_now, 'run_x', 'X') is False
    finally:
        runner.IS_TEST_MODE = orig_mode
        os.environ.pop('FORCE_TASK', None)
        if orig_env is not None:
            os.environ['FORCE_TASK'] = orig_env


def test_collect_target_groups():
    config = {
        'GROUPS': [{'group_name': 'A', 'chat_id': 1, 'topic_id': '5', 'language': 'UA'},
                   {'chat_id': 2}],
        'DIGEST_CHANNEL': {'group_name': 'D', 'chat_id': 3, 'enabled': True},
    }
    groups = runner.collect_target_groups(config)
    assert [g['name'] for g in groups] == ['A', 'Unknown', 'D']
    assert groups[1]['language'] == 'RU'  # default

    # disabled channel is dropped
    config['DIGEST_CHANNEL']['enabled'] = False
    assert len(runner.collect_target_groups(config)) == 2
    assert runner.collect_target_groups({}) == []


def test_parse_topic_id():
    assert runner.parse_topic_id('5') == 5
    assert runner.parse_topic_id(5) == 5
    assert runner.parse_topic_id(None) is None
    assert runner.parse_topic_id('') is None
    assert runner.parse_topic_id('  ') is None


def test_send_to_groups():
    seen = []

    class FakeManager:
        async def send_digest(self, **kw):
            seen.append(kw)
            if kw['target_chat_id'] == 2:
                raise RuntimeError("bad chat")

    groups = [{'name': 'A', 'chat_id': 1, 'topic_id': '7', 'language': 'UA'},
              {'name': 'B', 'chat_id': 2, 'topic_id': None, 'language': 'RU'},
              {'name': 'C', 'chat_id': 3, 'topic_id': '', 'language': 'RU'}]

    sent = asyncio.run(runner.send_to_groups(
        FakeManager(), groups, datetime(2026, 1, 1), "test digest",
        translate=lambda g: g.get('language') == 'UA'))

    # one group failed, the other two still went out
    assert sent == 2, sent
    assert [k['target_chat_id'] for k in seen] == [1, 2, 3]
    assert seen[0]['target_topic_id'] == 7 and seen[2]['target_topic_id'] is None
    assert seen[0]['translate_to_ua'] is True and seen[1]['translate_to_ua'] is False

    # translate=None -> manager is called without the flag (swuk digest takes none)
    seen.clear()
    asyncio.run(runner.send_to_groups(FakeManager(), groups[:1], datetime(2026, 1, 1), "swuk"))
    assert 'translate_to_ua' not in seen[0]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  {name} ok")
    print("digest runner ok")
