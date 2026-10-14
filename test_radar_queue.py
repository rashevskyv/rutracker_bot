import copy
import pytest
import radar_queue as rq


def row():
    return {"platform": "Switch", "app_name": "Game", "version": "v1", "description": "A native port.",
            "release_url": "https://example.com/release", "date": "2026-10-14T12:00:00Z"}


@pytest.mark.parametrize("field,value", [("platform", "root"), ("release_url", "file:///etc/passwd"),
                                       ("release_url", "https://user:password@example.com/x"),
                                       ("date", "invalid"), ("description", "x" * 221)])
def test_rejects_invalid_request(field, value):
    request = row()
    request[field] = value
    with pytest.raises(ValueError):
        rq.validated_rows([request])


def test_caller_cannot_set_publication_state_or_identity():
    request = dict(row(), processed=True, type="game", inbox_id="chosen", added_at="old", is_new=False)
    result = rq.validated_rows([request])[0]
    assert result["processed"] is False and result["type"] == "homebrew" and result["is_new"] is True
    assert result["inbox_id"] != "chosen" and result["added_at"] != "old"


def test_queue_preserves_inbox_and_deduplicates(monkeypatch):
    import add_release as ar
    old = dict(row(), inbox_id="existing")
    new = dict(row(), release_url="https://example.com/another")
    original = copy.deepcopy(old)
    monkeypatch.setattr(ar.sgs, "resolve_gist_credentials", lambda: ("test", "fake", None))
    monkeypatch.setattr(ar, "read_gist", lambda *args: ([], [old]))
    written = []
    monkeypatch.setattr(ar, "write_inbox", lambda gist, token, rows: written.extend(rows))
    rq.queue_rows([row(), new, new])
    assert len(written) == 2 and written[0] == original
    assert written[1]["release_url"] == new["release_url"]
