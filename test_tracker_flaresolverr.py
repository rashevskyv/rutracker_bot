"""Unit tests for FlareSolverr diagnostic reporting and fail-fast handling in tracker_parser."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from bs4 import BeautifulSoup
import aiohttp
from parsers import tracker_parser


@pytest.mark.asyncio
async def test_flaresolverr_unconfigured():
    """Verify fetch_via_flaresolverr records error when URL is missing."""
    with patch.object(tracker_parser, "FLARESOLVERR_URL", None):
        result = await tracker_parser.fetch_via_flaresolverr("https://rutracker.org/forum/viewtopic.php?t=123")
        assert result is None
        assert tracker_parser.get_last_flaresolverr_error() == "FLARESOLVERR_URL is not configured"


@pytest.mark.asyncio
async def test_flaresolverr_connection_error():
    """Verify fetch_via_flaresolverr records connection failure when FlareSolverr is down."""
    mock_session = MagicMock()
    mock_session.post.side_effect = aiohttp.ClientConnectorError(
        connection_key=MagicMock(), os_error=OSError(1225, "Connection refused")
    )
    with patch.object(tracker_parser, "get_session", return_value=mock_session), \
         patch.object(tracker_parser, "FLARESOLVERR_URL", "http://localhost:8191/v1"):
        result = await tracker_parser.fetch_via_flaresolverr("https://rutracker.org/forum/viewtopic.php?t=123")
        assert result is None
        err = tracker_parser.get_last_flaresolverr_error()
        assert err is not None
        assert "Cannot connect to FlareSolverr" in err


@pytest.mark.asyncio
async def test_flaresolverr_success_updates_cookies_and_ua():
    """Verify successful FlareSolverr bypass extracts cookies and User-Agent."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "status": "ok",
        "solution": {
            "response": "<html><title>Test Page</title><body>Content</body></html>",
            "cookies": [{"name": "cf_clearance", "value": "test_cf_token"}],
            "userAgent": "Mozilla/5.0 Custom UA"
        }
    })

    mock_post_context = AsyncMock()
    mock_post_context.__aenter__.return_value = mock_response
    mock_post_context.__aexit__.return_value = None

    mock_session = MagicMock()
    mock_session.post.return_value = mock_post_context

    with patch.object(tracker_parser, "get_session", return_value=mock_session), \
         patch.object(tracker_parser, "FLARESOLVERR_URL", "http://localhost:8191/v1"):
        result = await tracker_parser.fetch_via_flaresolverr("https://rutracker.org/forum/viewtopic.php?t=123")
        assert result is not None
        assert result.title.string == "Test Page"
        assert tracker_parser.get_last_flaresolverr_error() is None
        assert tracker_parser.FLARESOLVERR_USER_AGENT == "Mozilla/5.0 Custom UA"
        assert tracker_parser.RUTRACKER_COOKIES.get("cf_clearance") == "test_cf_token"


@pytest.mark.asyncio
async def test_fetch_page_content_fail_fast_on_unreachable_flaresolverr():
    """Verify fetch_page_content fails fast on attempt 1 if FlareSolverr is unreachable."""
    mock_curl_resp = MagicMock()
    mock_curl_resp.status_code = 403
    mock_curl_resp.text = "<html><title>Just a moment...</title></html>"

    mock_curl_session = AsyncMock()
    mock_curl_session.get = AsyncMock(return_value=mock_curl_resp)
    mock_curl_session.__aenter__.return_value = mock_curl_session
    mock_curl_session.__aexit__.return_value = None

    with patch("parsers.tracker_parser.CurlSession", return_value=mock_curl_session), \
         patch("parsers.tracker_parser.fetch_via_flaresolverr", return_value=None), \
         patch.object(tracker_parser, "last_flaresolverr_error", "Cannot connect to FlareSolverr at http://localhost:8191/v1 (Connection refused)"):
        with pytest.raises(ValueError) as excinfo:
            await tracker_parser.fetch_page_content("https://rutracker.org/forum/viewtopic.php?t=123", retries=15)

        err_text = str(excinfo.value)
        assert "FlareSolverr is unreachable" in err_text
        assert "docker run" in err_text
        # Ensure it failed fast without looping 15 times
        assert mock_curl_session.get.call_count <= 2  # rutracker.org + mirror check


@pytest.mark.asyncio
async def test_fetch_page_content_mirror_success():
    """Verify fetch_page_content uses rutracker.net directly if org is 403 but net is 200."""
    org_resp = MagicMock()
    org_resp.status_code = 403
    org_resp.text = "<html><title>Just a moment...</title></html>"

    net_resp = MagicMock()
    net_resp.status_code = 200
    net_resp.text = "<html><title>Mirror OK</title><body>Success</body></html>"
    net_resp.content = b"<html><title>Mirror OK</title><body>Success</body></html>"

    async def mock_get(url, **kwargs):
        if "rutracker.net" in url:
            return net_resp
        return org_resp

    mock_curl_session = AsyncMock()
    mock_curl_session.get.side_effect = mock_get
    mock_curl_session.__aenter__.return_value = mock_curl_session
    mock_curl_session.__aexit__.return_value = None

    with patch("parsers.tracker_parser.CurlSession", return_value=mock_curl_session), \
         patch("parsers.tracker_parser.fetch_via_flaresolverr") as mock_flare:
        soup = await tracker_parser.fetch_page_content("https://rutracker.org/forum/viewtopic.php?t=123", retries=3)
        assert soup is not None
        assert soup.title.string == "Mirror OK"
        # FlareSolverr was not even needed because direct mirror succeeded!
        mock_flare.assert_not_called()
