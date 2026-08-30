"""Token refresh.

Refresh used to fail on every cold start, so the stored token was dead weight
and each restart quietly fell back to a full password login. Two causes: the
SECRET_HASH requirement is probed at login and forgotten, and the hash must be
computed over the pool's real username rather than the sign-in alias.
"""

import asyncio

import pytest

ALIAS = "person@example.com"
POOL_USER = "a1b2c3d4-5566-7788-99aa-bbccddeeff00"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(api, const):
    def _make(**kw):
        return api.SmartShadeApi(None, ALIAS, brand=const.BRANDS["marygrove"], **kw)
    return _make


def fake_idp(script):
    """Replay Cognito responses, recording the SECRET_HASH each attempt sent."""
    calls = []

    async def _idp(self, target, payload):
        params = payload["AuthParameters"]
        calls.append({"secret_hash": params.get("SECRET_HASH")})
        outcome = script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return {"AuthenticationResult": {"IdToken": outcome}}

    return _idp, calls


def token_for(username):
    """Minimal unsigned JWT carrying a cognito:username claim."""
    import base64, json
    body = base64.urlsafe_b64encode(
        json.dumps({"cognito:username": username}).encode()
    ).decode().rstrip("=")
    return f"header.{body}.sig"


def test_persisted_pool_username_makes_refresh_succeed_first_try(client, api, monkeypatch):
    c = client(pool_username=POOL_USER)
    c._use_secret_hash = True
    c.set_refresh_token("tok")
    idp, calls = fake_idp([token_for(POOL_USER)])
    monkeypatch.setattr(api.SmartShadeApi, "_idp", idp)
    run(c.refresh())
    assert len(calls) == 1, "should not need to retry when the username is known"
    assert c.pool_username == POOL_USER


def test_refresh_probes_the_secret_hash_requirement(client, api, monkeypatch):
    """A fresh object does not know the client needs a SECRET_HASH."""
    c = client(pool_username=POOL_USER)
    c.set_refresh_token("tok")
    assert c._use_secret_hash is False
    idp, calls = fake_idp([
        api.SmartShadeAuthError(
            "[InitiateAuth] Client x is configured with secret but SECRET_HASH was not received"
        ),
        token_for(POOL_USER),
    ])
    monkeypatch.setattr(api.SmartShadeApi, "_idp", idp)
    run(c.refresh())
    assert calls[0]["secret_hash"] is None
    assert calls[1]["secret_hash"] is not None
    assert c._use_secret_hash is True


def test_refresh_falls_back_to_the_alias_when_pool_username_is_wrong(client, api, monkeypatch):
    """Covers entries saved before the pool username was persisted."""
    c = client(pool_username="stale-value")
    c._use_secret_hash = True
    c.set_refresh_token("tok")
    idp, calls = fake_idp([
        api.SmartShadeAuthError("[InitiateAuth] Unable to verify secret hash for client x"),
        token_for(POOL_USER),
    ])
    monkeypatch.setattr(api.SmartShadeApi, "_idp", idp)
    run(c.refresh())
    assert len(calls) == 2
    # The ID token's claim wins, so the next save persists the right value.
    assert c.pool_username == POOL_USER


def test_refresh_learns_and_exposes_the_pool_username(client, api, monkeypatch):
    c = client()
    c._use_secret_hash = True
    c.set_refresh_token("tok")
    assert c.pool_username == ALIAS
    idp, _ = fake_idp([token_for(POOL_USER)])
    monkeypatch.setattr(api.SmartShadeApi, "_idp", idp)
    run(c.refresh())
    assert c.pool_username == POOL_USER, "must be persistable after a refresh"


def test_refresh_without_a_token_fails_fast(client):
    with pytest.raises(Exception) as e:
        run(client().refresh())
    assert "no refresh token" in str(e.value)


def test_refresh_gives_up_rather_than_looping(client, api, monkeypatch):
    c = client(pool_username=POOL_USER)
    c._use_secret_hash = True
    c.set_refresh_token("expired")
    err = api.SmartShadeAuthError("[InitiateAuth] Refresh Token has expired")
    idp, calls = fake_idp([err] * 6)
    monkeypatch.setattr(api.SmartShadeApi, "_idp", idp)
    with pytest.raises(api.SmartShadeAuthError):
        run(c.refresh())
    assert len(calls) <= 4, f"bounded retries, got {len(calls)}"
