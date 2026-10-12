"""services/store_manual.py: store manual.json sync with a fake `gh`. No network, no credentials."""
import base64
import json
import subprocess
from types import SimpleNamespace

import services.store_manual as sm


class FakeGh:
    """Serves manual.json like the contents API and records PUT bodies."""

    def __init__(self, rows, fail_put=0, fail_get=False):
        self.content = json.dumps(rows, indent=2)
        self.sha = "sha1"
        self.fail_put = fail_put
        self.fail_get = fail_get
        self.puts = []

    def __call__(self, argv, input=None, **kwargs):
        assert argv[:2] == ["gh", "api"]
        if "-X" in argv:  # PUT
            if self.fail_put:
                self.fail_put -= 1
                raise subprocess.CalledProcessError(1, argv)
            body = json.loads(input)
            assert body["sha"] == self.sha, "PUT must carry the sha it read"
            self.puts.append(body)
            self.content = base64.b64decode(body["content"]).decode("utf-8")
            self.sha = f"sha{len(self.puts) + 1}"
            return SimpleNamespace(stdout="{}")
        if self.fail_get:
            raise subprocess.CalledProcessError(1, argv)
        enc = base64.encodebytes(self.content.encode("utf-8")).decode()  # GitHub wraps base64 in newlines
        return SimpleNamespace(stdout=json.dumps({"sha": self.sha, "content": enc}))


def gh_present(_name):
    return "/usr/bin/gh"


class TestRepoFromUrl:
    def test_release_and_tag_urls(self):
        assert sm.repo_from_url("https://github.com/Owner/Repo") == "Owner/Repo"
        assert sm.repo_from_url("https://github.com/o/r/releases/tag/v1.2") == "o/r"
        assert sm.repo_from_url("https://github.com/o/r.git") == "o/r"

    def test_non_github_or_incomplete_is_none(self):
        assert sm.repo_from_url("https://gitlab.com/o/r") is None
        assert sm.repo_from_url("https://github.com/o") is None


class TestUpsert:
    def test_adds_new_repo_with_only_repo_key(self):
        rows, changed = sm.upsert([], "o/r")
        assert changed and rows == [{"repo": "o/r"}]

    def test_known_repo_is_unchanged_case_insensitively(self):
        rows, changed = sm.upsert([{"repo": "O/R", "title": "T"}], "o/r")
        assert not changed and rows == [{"repo": "O/R", "title": "T"}]

    def test_disabled_row_is_enabled_and_other_fields_kept(self):
        rows, changed = sm.upsert([{"repo": "o/r", "disabled": True, "section": "PC"}], "o/r")
        assert changed and rows == [{"repo": "o/r", "section": "PC"}]


class TestSync:
    def test_adds_repo_once_and_is_idempotent(self):
        gh = FakeGh([{"repo": "a/b", "title": "A"}])
        assert "added o/r" in sm.sync_release("https://github.com/o/r/releases/tag/v2", run=gh, which=gh_present)
        assert json.loads(gh.content) == [{"repo": "a/b", "title": "A"}, {"repo": "o/r"}]
        assert gh.puts[0]["branch"] == "main"
        again = sm.sync_release("https://github.com/o/r", run=gh, which=gh_present)
        assert "already" in again and len(gh.puts) == 1

    def test_empty_manual_file(self):
        gh = FakeGh([])
        sm.sync_release("https://github.com/o/r", run=gh, which=gh_present)
        assert json.loads(gh.content) == [{"repo": "o/r"}]

    def test_gh_missing_warns_and_makes_no_call(self):
        gh = FakeGh([])
        msg = sm.sync_release("https://github.com/o/r", run=gh, which=lambda _n: None)
        assert msg.startswith("store: WARNING gh not found") and gh.puts == []

    def test_gh_failure_warns_not_raises(self):
        msg = sm.sync_release("https://github.com/o/r", run=FakeGh([], fail_get=True), which=gh_present)
        assert msg.startswith("store: WARNING")

    def test_conflict_on_put_retries_once(self):
        gh = FakeGh([], fail_put=1)
        msg = sm.sync_release("https://github.com/o/r", run=gh, which=gh_present)
        assert "added o/r" in msg and len(gh.puts) == 1

    def test_persistent_conflict_warns(self):
        gh = FakeGh([], fail_put=2)
        msg = sm.sync_release("https://github.com/o/r", run=gh, which=gh_present)
        assert msg.startswith("store: WARNING") and gh.puts == []

    def test_non_github_url_is_skipped_without_gh(self):
        gh = FakeGh([])
        assert sm.sync_release("https://example.com/o/r", run=gh, which=gh_present).startswith("store: skipped")
        assert gh.puts == []

    def test_manual_file_not_a_list_is_left_alone(self):
        gh = FakeGh({"not": "a list"})
        msg = sm.sync_release("https://github.com/o/r", run=gh, which=gh_present)
        assert msg.startswith("store: WARNING") and gh.puts == []


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
