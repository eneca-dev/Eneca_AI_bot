"""Tests for GraphClient — verified against mocked httpx.

We don't hit real Microsoft Graph. The goal is to verify the right HTTP
shape, token caching, profile caching, and graceful failure modes.
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.graph_client import GraphClient


# --- Helpers ---


def _make_response(status_code: int, json_body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


def _make_token_response(access_token: str = "tok-1", expires_in: int = 3600) -> MagicMock:
    return _make_response(200, {"access_token": access_token, "expires_in": expires_in})


def _make_client(post_response=None, get_response=None, post_responses=None, get_responses=None):
    """Build an httpx.AsyncClient mock supporting `async with`."""
    client = MagicMock()

    if post_responses is not None:
        client.post = AsyncMock(side_effect=post_responses)
    elif post_response is not None:
        client.post = AsyncMock(return_value=post_response)

    if get_responses is not None:
        client.get = AsyncMock(side_effect=get_responses)
    elif get_response is not None:
        client.get = AsyncMock(return_value=get_response)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


def _configured_client() -> GraphClient:
    gc = GraphClient.__new__(GraphClient)
    gc._token = None
    gc._token_expires_at = 0.0
    gc._profile_cache = {}
    return gc


@pytest.fixture
def fake_settings():
    """Patch core.config.settings used inside graph_client to look configured."""
    with patch("services.graph_client.settings") as s:
        s.microsoft_app_id = "app-id"
        s.microsoft_app_password = "secret"
        s.tenant_id = "tenant"
        yield s


# --- is_configured ---


def test_is_configured_false_when_missing():
    gc = _configured_client()
    with patch("services.graph_client.settings") as s:
        s.microsoft_app_id = None
        s.microsoft_app_password = "x"
        s.tenant_id = "y"
        assert gc.is_configured is False


def test_is_configured_true_when_all_set(fake_settings):
    gc = _configured_client()
    assert gc.is_configured is True


# --- get_user_profile: not-configured short-circuit ---


@pytest.mark.asyncio
async def test_get_user_profile_returns_none_when_not_configured():
    gc = _configured_client()
    with patch("services.graph_client.settings") as s:
        s.microsoft_app_id = None
        s.microsoft_app_password = None
        s.tenant_id = None
        result = await gc.get_user_profile("aad-1")
    assert result is None


@pytest.mark.asyncio
async def test_get_user_profile_returns_none_for_empty_aad():
    gc = _configured_client()
    assert await gc.get_user_profile(None) is None
    assert await gc.get_user_profile("") is None


# --- Happy path ---


@pytest.mark.asyncio
async def test_get_user_profile_happy_path(fake_settings):
    gc = _configured_client()
    token_resp = _make_token_response("tok-A")
    profile_resp = _make_response(200, {
        "displayName": "Иван Петров",
        "jobTitle": "Инженер-конструктор",
        "department": "ГР",
        "companyName": "Eneca",
        "mail": "ivan@eneca.com",
        "id": "aad-42",
    })

    cm_token, _ = _make_client(post_response=token_resp)
    cm_get, _ = _make_client(get_response=profile_resp)

    with patch("services.graph_client.httpx.AsyncClient", side_effect=[cm_token, cm_get]):
        result = await gc.get_user_profile("aad-42")

    assert result == {
        "displayName": "Иван Петров",
        "jobTitle": "Инженер-конструктор",
        "department": "ГР",
        "companyName": "Eneca",
        "mail": "ivan@eneca.com",
    }


# --- Token caching ---


@pytest.mark.asyncio
async def test_token_is_cached_across_calls(fake_settings):
    gc = _configured_client()
    profile_body = {"displayName": "x", "jobTitle": None, "department": None, "companyName": None, "mail": None}

    token_resp = _make_token_response("tok-cached")
    get_resp_1 = _make_response(200, {**profile_body, "displayName": "User-1"})
    get_resp_2 = _make_response(200, {**profile_body, "displayName": "User-2"})

    cm_token, _ = _make_client(post_response=token_resp)
    cm_get_1, _ = _make_client(get_response=get_resp_1)
    cm_get_2, _ = _make_client(get_response=get_resp_2)

    # First call: token + profile. Second call: only profile (token cached).
    with patch("services.graph_client.httpx.AsyncClient", side_effect=[cm_token, cm_get_1, cm_get_2]):
        await gc.get_user_profile("aad-1")
        await gc.get_user_profile("aad-2")

    assert gc._token == "tok-cached"


# --- Profile caching ---


@pytest.mark.asyncio
async def test_profile_is_cached_within_ttl(fake_settings):
    gc = _configured_client()

    token_resp = _make_token_response("tok-A")
    profile_resp = _make_response(200, {
        "displayName": "Иван", "jobTitle": "Eng", "department": None,
        "companyName": "Eneca", "mail": None,
    })
    cm_token, _ = _make_client(post_response=token_resp)
    cm_get, get_client = _make_client(get_response=profile_resp)

    with patch("services.graph_client.httpx.AsyncClient", side_effect=[cm_token, cm_get]):
        first = await gc.get_user_profile("aad-1")
        second = await gc.get_user_profile("aad-1")  # must hit cache, no new HTTP

    assert first == second
    # Only ONE GET happened
    get_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_profile_cache_expires_after_ttl(fake_settings):
    gc = _configured_client()
    gc._profile_cache["aad-1"] = ({"displayName": "old"}, time.time() - gc.PROFILE_TTL_SECONDS - 1)

    token_resp = _make_token_response("tok-A")
    profile_resp = _make_response(200, {
        "displayName": "new", "jobTitle": None, "department": None,
        "companyName": None, "mail": None,
    })
    cm_token, _ = _make_client(post_response=token_resp)
    cm_get, _ = _make_client(get_response=profile_resp)

    with patch("services.graph_client.httpx.AsyncClient", side_effect=[cm_token, cm_get]):
        result = await gc.get_user_profile("aad-1")

    assert result["displayName"] == "new"


# --- Failure modes ---


@pytest.mark.asyncio
async def test_get_user_profile_404_returns_none(fake_settings):
    gc = _configured_client()
    token_resp = _make_token_response("tok-A")
    not_found = _make_response(404, {"error": {"message": "User not found"}})

    cm_token, _ = _make_client(post_response=token_resp)
    cm_get, _ = _make_client(get_response=not_found)

    with patch("services.graph_client.httpx.AsyncClient", side_effect=[cm_token, cm_get]):
        result = await gc.get_user_profile("aad-missing")

    assert result is None


@pytest.mark.asyncio
async def test_get_user_profile_403_returns_none(fake_settings):
    """Insufficient permissions (admin consent missing) → graceful None."""
    gc = _configured_client()
    token_resp = _make_token_response("tok-A")
    forbidden = _make_response(403, {"error": {"message": "Insufficient privileges"}})

    cm_token, _ = _make_client(post_response=token_resp)
    cm_get, _ = _make_client(get_response=forbidden)

    with patch("services.graph_client.httpx.AsyncClient", side_effect=[cm_token, cm_get]):
        result = await gc.get_user_profile("aad-1")

    assert result is None


@pytest.mark.asyncio
async def test_get_user_profile_token_failure_returns_none(fake_settings):
    """If OAuth fails, profile fetch must not raise — just return None."""
    gc = _configured_client()
    bad_token_resp = _make_response(401, {"error": "unauthorized_client"})
    bad_token_resp.raise_for_status = MagicMock(side_effect=Exception("OAuth 401"))

    cm_token, _ = _make_client(post_response=bad_token_resp)

    with patch("services.graph_client.httpx.AsyncClient", side_effect=[cm_token]):
        result = await gc.get_user_profile("aad-1")

    assert result is None
