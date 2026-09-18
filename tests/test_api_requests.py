"""Request shaping and brand validation.

The two gateways agree on paths and responses but disagree on verb and on where
GrillNumber travels. These assertions mirror the app's Retrofit interfaces:

    legacy  CloudShadowAPI.getState(@Query("GrillNumber"))
    new     CloudShadowAPINew.getState(@Body Map)
    legacy  CloudDBRetrofitAPI.listGrills(@Query("GrillNumber"))
    new     CloudDBRetrofitAPINewForSmartShade.listGrills(@Body JsonObject)  # AppName
"""

import asyncio
import base64
import json
import time

import pytest


@pytest.fixture
def make(api, const):
    def _make(brand_key):
        return api.SmartShadeApi(None, "u@e.com", brand=const.BRANDS[brand_key])
    return _make


def _jwt(**claims) -> str:
    """A token that is only ever parsed, never verified."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


class _FakeResponse:
    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Serves queued (status, body) pairs and records the token each call sent."""

    def __init__(self, *responses) -> None:
        self._responses = list(responses)
        self.tokens: list[str | None] = []

    def request(self, method, url, headers=None, params=None, data=None):
        self.tokens.append((headers or {}).get("Authorization"))
        return _FakeResponse(*self._responses.pop(0))


@pytest.fixture
def signed_in(api, const, monkeypatch):
    """An API client holding a live token, with `refresh` stubbed and counted."""

    def _make(*responses, exp_in=3600):
        session = _FakeSession(*responses)
        client = api.SmartShadeApi(
            session, "u@e.com", brand=const.BRANDS["marygrove"]
        )
        client.set_refresh_token("stored-refresh-token")
        client._store_id_token(_jwt(exp=time.time() + exp_in))
        refreshed = []

        async def fake_refresh(self):
            refreshed.append(True)
            self._store_id_token(_jwt(exp=time.time() + 86400))

        monkeypatch.setattr(api.SmartShadeApi, "refresh", fake_refresh)
        return client, session, refreshed

    return _make


def test_legacy_read_is_get_with_query_param(make):
    assert make("smartshade")._shape("MNH-1") == ("GET", {"GrillNumber": "MNH-1"}, None)


def test_new_read_is_post_with_body(make):
    assert make("liberty")._shape("MNH-1") == ("POST", None, {"GrillNumber": "MNH-1"})


def test_app_name_defaults_from_the_brand(make):
    assert make("liberty").app_name == "liberty"
    assert make("macdonald").app_name == "macdonald"
    assert make("smartshade").app_name is None


def test_stored_app_name_overrides_the_brand_default(api, const):
    client = api.SmartShadeApi(
        None, "u@e.com", brand=const.BRANDS["liberty"], app_name="from-entry"
    )
    assert client.app_name == "from-entry"


def test_pool_name_used_for_srp_comes_from_the_brand(make):
    assert make("liberty")._pool_name == "8oziOkCAf"


def _run(coro):
    return asyncio.run(coro)


def test_validate_brand_contacts_only_the_chosen_pool(api, const, monkeypatch):
    """The reason the brand is asked for rather than probed."""
    seen = []

    async def fake_auth(self, password=None):
        seen.append(self._brand.pool_id)

    async def fake_list(self, serial=""):
        return [{"GrillNumber": "MNH-1"}]

    monkeypatch.setattr(api.SmartShadeApi, "authenticate", fake_auth)
    monkeypatch.setattr(api.SmartShadeApi, "get_grill_list", fake_list)

    _run(api.validate_brand(None, "u@e.com", "pw", const.BRANDS["liberty"]))
    assert seen == [const.BRANDS["liberty"].pool_id]


def test_validate_brand_requires_a_device_list_not_just_a_token(api, const, monkeypatch):
    async def fake_auth(self, password=None):
        return None

    async def boom(self, serial=""):
        raise api.SmartShadeApiError("get-grill-list HTTP 400: nope")

    monkeypatch.setattr(api.SmartShadeApi, "authenticate", fake_auth)
    monkeypatch.setattr(api.SmartShadeApi, "get_grill_list", boom)

    with pytest.raises(api.SmartShadeApiError):
        _run(api.validate_brand(None, "u@e.com", "pw", const.BRANDS["liberty"]))


def test_attempts_log_records_outcome_without_credentials(api, const, monkeypatch):
    async def fake_auth(self, password=None):
        raise api.SmartShadeAuthError("NotAuthorizedException")

    monkeypatch.setattr(api.SmartShadeApi, "authenticate", fake_auth)
    attempts = []
    with pytest.raises(api.SmartShadeAuthError):
        _run(
            api.validate_brand(
                None, "u@e.com", "hunter2", const.BRANDS["smartshade"], attempts=attempts
            )
        )
    assert attempts[0]["brand"] == "smartshade"
    assert "hunter2" not in str(attempts)
    assert "u@e.com" not in str(attempts)


def test_capitalised_email_is_retried_in_lower_case(api, const, monkeypatch):
    """Cognito usernames are case-sensitive; "Bills@" != "bills@".

    The resulting "User does not exist" gives no hint that case is the problem,
    so a single lower-case retry is worth it.
    """
    tried = []

    async def fake_auth(self, password=None):
        tried.append(self._username)
        if self._username != "bills@example.com":
            raise api.SmartShadeAuthError("[InitiateAuth] User does not exist.")

    async def fake_list(self, serial=""):
        return [{"GrillNumber": "MNH-1"}]

    monkeypatch.setattr(api.SmartShadeApi, "authenticate", fake_auth)
    monkeypatch.setattr(api.SmartShadeApi, "get_grill_list", fake_list)

    client, hubs = _run(
        api.validate_brand(None, "Bills@example.com", "pw", const.BRANDS["marygrove"])
    )
    assert tried == ["Bills@example.com", "bills@example.com"]
    assert client.username == "bills@example.com", "the working spelling must be stored"
    assert len(hubs) == 1


def test_lower_case_retry_only_fires_for_user_not_found(api, const, monkeypatch):
    """A wrong password must not cause a second login attempt."""
    tried = []

    async def fake_auth(self, password=None):
        tried.append(self._username)
        raise api.SmartShadeAuthError("[InitiateAuth] Incorrect username or password.")

    monkeypatch.setattr(api.SmartShadeApi, "authenticate", fake_auth)
    with pytest.raises(api.SmartShadeAuthError):
        _run(api.validate_brand(None, "Bills@example.com", "pw", const.BRANDS["marygrove"]))
    assert tried == ["Bills@example.com"], "must not burn a second attempt"


_EXPIRED_400 = (400, '{"isOkay": false, "code": 400, "msg": "No Authorizer User Id"}')
_OK = (200, '{"isOkay": true, "code": 200, "data": []}')


def test_expired_token_400_is_refreshed_and_retried(signed_in):
    """The failure that took the integration down for four days.

    The gateway's authorizer reports an expired ID token as a 400, not a 401.
    Treated as an ordinary API error it is fatal for the life of the process:
    the dead token stays cached, so every later poll repeats it verbatim.
    """
    client, session, refreshed = signed_in(_EXPIRED_400, _OK)

    assert _run(client.get_grill_list()) == []
    assert len(refreshed) == 1, "a rejected token must trigger exactly one refresh"
    assert session.tokens[0] != session.tokens[1], "the retry must use the new token"


def test_ordinary_400_is_not_mistaken_for_an_expired_token(api, signed_in):
    """A paired accessory has no shadow and answers 400. That is not an expiry."""
    client, _session, refreshed = signed_in(
        (400, '{"isOkay": false, "code": 400, "msg": "No shadow found"}')
    )

    with pytest.raises(api.SmartShadeApiError):
        _run(client.get_state("USL-1"))
    assert refreshed == [], "must not burn a refresh on a real error"


def test_routing_error_is_not_mistaken_for_an_expired_token(api, signed_in):
    client, _session, refreshed = signed_in(
        (403, '{"message": "Missing Authentication Token"}')
    )

    with pytest.raises(api.SmartShadeApiError):
        _run(client.get_grill_list())
    assert refreshed == [], "a wrong path is not an auth problem"


def test_401_still_refreshes(signed_in):
    client, _session, refreshed = signed_in((401, "Unauthorized"), _OK)

    _run(client.get_grill_list())
    assert len(refreshed) == 1


def test_token_is_renewed_before_it_expires(signed_in):
    """Renew on the clock, so the 400 above is never provoked in the first place."""
    client, session, refreshed = signed_in(_OK, exp_in=30)

    _run(client.get_grill_list())
    assert len(refreshed) == 1
    assert session.tokens[0] == client._id_token, "the request must use the fresh token"


def test_live_token_is_reused(signed_in):
    client, _session, refreshed = signed_in(_OK, exp_in=3600)

    _run(client.get_grill_list())
    assert refreshed == [], "a token with an hour left needs no renewal"


def test_expiry_is_read_from_the_token(make):
    client = make("marygrove")
    client._store_id_token(_jwt(exp=time.time() + 86400))
    assert not client._token_expired()

    client._store_id_token(_jwt(exp=time.time() - 1))
    assert client._token_expired()


def test_undecodable_token_leaves_expiry_unknown(make):
    """No `exp` means fall back to reacting to rejections, not renewing blindly."""
    client = make("marygrove")
    client._store_id_token("not-a-jwt")
    assert client._id_token_exp is None
    assert not client._token_expired()


def test_pool_username_still_comes_from_the_token(make):
    client = make("marygrove")
    client._store_id_token(_jwt(exp=time.time() + 60, **{"cognito:username": "pool-user"}))
    assert client.pool_username == "pool-user"


def test_refresh_falls_back_to_the_password(api, const, monkeypatch):
    """A revoked refresh token should not need a reauth prompt if we hold a password."""
    calls = []

    async def fake_refresh(self):
        calls.append("refresh")
        raise api.SmartShadeAuthError("Refresh Token has expired")

    async def fake_auth(self, password=None):
        calls.append("authenticate")
        self._store_id_token(_jwt(exp=time.time() + 86400))

    monkeypatch.setattr(api.SmartShadeApi, "refresh", fake_refresh)
    monkeypatch.setattr(api.SmartShadeApi, "authenticate", fake_auth)

    client = api.SmartShadeApi(
        _FakeSession(_OK), "u@e.com", password="pw", brand=const.BRANDS["marygrove"]
    )
    client.set_refresh_token("stale")
    _run(client.get_grill_list())
    assert calls == ["refresh", "authenticate"]


def test_refresh_failure_without_a_password_is_raised(api, const, monkeypatch):
    async def fake_refresh(self):
        raise api.SmartShadeAuthError("Refresh Token has expired")

    monkeypatch.setattr(api.SmartShadeApi, "refresh", fake_refresh)
    client = api.SmartShadeApi(
        _FakeSession(_OK), "u@e.com", brand=const.BRANDS["marygrove"]
    )
    client.set_refresh_token("stale")
    with pytest.raises(api.SmartShadeAuthError):
        _run(client.get_grill_list())


def test_already_lower_case_is_not_retried(api, const, monkeypatch):
    tried = []

    async def fake_auth(self, password=None):
        tried.append(self._username)
        raise api.SmartShadeAuthError("[InitiateAuth] User does not exist.")

    monkeypatch.setattr(api.SmartShadeApi, "authenticate", fake_auth)
    with pytest.raises(api.SmartShadeAuthError):
        _run(api.validate_brand(None, "bills@example.com", "pw", const.BRANDS["marygrove"]))
    assert tried == ["bills@example.com"]
