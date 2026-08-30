"""Request shaping and brand validation.

The two gateways agree on paths and responses but disagree on verb and on where
GrillNumber travels. These assertions mirror the app's Retrofit interfaces:

    legacy  CloudShadowAPI.getState(@Query("GrillNumber"))
    new     CloudShadowAPINew.getState(@Body Map)
    legacy  CloudDBRetrofitAPI.listGrills(@Query("GrillNumber"))
    new     CloudDBRetrofitAPINewForSmartShade.listGrills(@Body JsonObject)  # AppName
"""

import asyncio

import pytest


@pytest.fixture
def make(api, const):
    def _make(brand_key):
        return api.SmartShadeApi(None, "u@e.com", brand=const.BRANDS[brand_key])
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


def test_already_lower_case_is_not_retried(api, const, monkeypatch):
    tried = []

    async def fake_auth(self, password=None):
        tried.append(self._username)
        raise api.SmartShadeAuthError("[InitiateAuth] User does not exist.")

    monkeypatch.setattr(api.SmartShadeApi, "authenticate", fake_auth)
    with pytest.raises(api.SmartShadeAuthError):
        _run(api.validate_brand(None, "bills@example.com", "pw", const.BRANDS["marygrove"]))
    assert tried == ["bills@example.com"]
