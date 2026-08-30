"""Smart-Shade PRO cloud API: Cognito SRP auth + REST calls.

Self-contained (no boto3/pycognito). Implements AWS Cognito USER_SRP_AUTH with
SECRET_HASH, then talks to the app's API Gateway. The ``Authorization`` header
carries the Cognito **ID token** (the app mislabels it "access" but sends the ID
token), matching the decompiled OkHttp interceptor.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import logging
import os

import aiohttp

from .const import (
    BRANDS,
    DEFAULT_BRAND,
    Brand,
    EP_COMMAND,
    EP_LIST,
    EP_STATE,
)

_LOGGER = logging.getLogger(__name__)

# RFC 5054 3072-bit group N with generator g=2 (the values AWS Cognito uses).
_N_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74"
    "020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F1437"
    "4FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF05"
    "98DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB"
    "9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF695581718"
    "3995497CEA956AE515D2261898FA051015728E5A8AAAC42DAD33170D04507A33"
    "A85521ABDF1CBA64ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6BF12FFA06D98A0864"
    "D87602733EC86A64521F2B18177B200CBBE117577A615D6C770988C0BAD946E2"
    "08E24FA074E5AB3143DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF"
)
_N = int(_N_HEX, 16)
_G = 2
_INFO_BITS = b"Caldera Derived Key"

# Cognito's SRP timestamp must be English regardless of system locale, so we
# cannot use strftime("%a %b") here.
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _hash_sha256(buf: bytes) -> str:
    """SHA-256 hex digest, zero-padded to 64 chars as Cognito expects."""
    return hashlib.sha256(buf).hexdigest().rjust(64, "0")


def _hex_hash(hex_str: str) -> str:
    return _hash_sha256(bytes.fromhex(hex_str))


def _pad_hex(long_int) -> str:
    """Pad a hex string the way Cognito's SRP expects (leading 00 if high bit set)."""
    hash_str = format(long_int, "x") if isinstance(long_int, int) else long_int
    if len(hash_str) % 2 == 1:
        hash_str = "0" + hash_str
    elif hash_str[0] in "89abcdef":
        hash_str = "00" + hash_str
    return hash_str


def _compute_hkdf(ikm: bytes, salt: bytes) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    hmac_hash = hmac.new(prk, _INFO_BITS + bytes([1]), hashlib.sha256).digest()
    return hmac_hash[:16]


def _secret_hash(username: str, brand: Brand) -> str:
    msg = (username + brand.client_id).encode("utf-8")
    key = brand.client_secret.encode("utf-8")
    return base64.b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode()


class SmartShadeAuthError(Exception):
    """Authentication failed."""


class SmartShadeApiError(Exception):
    """A REST call failed."""


class SmartShadeApi:
    """Handles Cognito SRP auth (+ refresh) and the REST endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str | None = None,
        brand: Brand | None = None,
        app_name: str | None = None,
        pool_username: str | None = None,
    ) -> None:
        self._session = session
        self._brand = brand or BRANDS[DEFAULT_BRAND]
        # Only meaningful on the newer gateway. Defaults to the brand's own
        # value; the override exists so a stored entry keeps working if the
        # constant is ever corrected.
        self._app_name = app_name or self._brand.app_name
        self._username = username
        # Username used for SECRET_HASH on refresh. The pool's real username
        # differs from the sign-in alias; it is learned from an ID token and
        # persisted in the config entry, because without it a stored refresh
        # token cannot be used after a restart.
        self._refresh_username = pool_username or username
        self._password = password
        self._id_token: str | None = None
        self._refresh_token: str | None = None
        self._pool_name = self._brand.pool_name
        # Whether this app client actually has a secret configured.
        # Cognito returns "Unable to verify secret hash for client <id>" when a
        # SECRET_HASH is sent to a client that has NO secret, so we probe once
        # and remember the answer.
        self._use_secret_hash: bool = False
        self._small_a = 0
        self._large_a = 0
        self._new_ephemeral()

    def _new_ephemeral(self) -> None:
        """Generate a fresh SRP ephemeral key pair."""
        while True:
            self._small_a = int.from_bytes(os.urandom(128), "big") % _N
            self._large_a = pow(_G, self._small_a, _N)
            if self._large_a % _N != 0:
                return

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    def set_refresh_token(self, token: str | None) -> None:
        self._refresh_token = token

    @property
    def username(self) -> str:
        """The username that actually authenticated (see validate_brand)."""
        return self._username

    @property
    def pool_username(self) -> str:
        """The pool username to persist alongside the refresh token."""
        return self._refresh_username

    def _maybe_secret(self, params: dict, username: str) -> dict:
        """Add SECRET_HASH only if this client is known to require it."""
        if self._use_secret_hash:
            params["SECRET_HASH"] = _secret_hash(username, self._brand)
        return params

    async def _idp(self, target: str, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"AWSCognitoIdentityProviderService.{target}",
        }
        async with self._session.post(
            self._brand.idp_url, headers=headers, data=json.dumps(payload)
        ) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200:
                # Prefix with the step so InitiateAuth vs RespondToAuthChallenge
                # failures are distinguishable in the log (they raise identically).
                raise SmartShadeAuthError(
                    f"[{target}] "
                    + body.get("message", f"HTTP {resp.status}")
                )
            _LOGGER.debug("%s ok", target)
            return body

    def _password_authentication_key(
        self, srp_b: int, salt: int, user_id_for_srp: str
    ) -> bytes:
        u = int(_hex_hash(_pad_hex(self._large_a) + _pad_hex(srp_b)), 16)
        if u == 0:
            raise SmartShadeAuthError("SRP u == 0")
        k = int(_hex_hash(_pad_hex(_N) + _pad_hex(_G)), 16)
        username_password = f"{self._pool_name}{user_id_for_srp}:{self._password}"
        username_password_hash = _hash_sha256(username_password.encode("utf-8"))
        x = int(_hex_hash(_pad_hex(salt) + username_password_hash), 16)
        g_mod_pow = pow(_G, x, _N)
        int_value2 = srp_b - k * g_mod_pow
        s = pow(int_value2, self._small_a + u * x, _N)
        return _compute_hkdf(bytes.fromhex(_pad_hex(s)), bytes.fromhex(_pad_hex(u)))

    async def authenticate(self, password: str | None = None) -> None:
        """Full SRP login. Stores ID + refresh tokens."""
        if password is not None:
            self._password = password
        if not self._password:
            raise SmartShadeAuthError("password required")

        self._new_ephemeral()

        async def _initiate() -> dict:
            params = {
                "USERNAME": self._username,
                "SRP_A": format(self._large_a, "x"),
            }
            return await self._idp(
                "InitiateAuth",
                {
                    "AuthFlow": "USER_SRP_AUTH",
                    "ClientId": self._brand.client_id,
                    "AuthParameters": self._maybe_secret(params, self._username),
                },
            )

        try:
            init = await _initiate()
        except SmartShadeAuthError as err:
            msg = str(err).lower()
            # Client *does* have a secret and we omitted it -> flip and retry once.
            if "secret_hash" in msg or "configured with secret" in msg:
                self._use_secret_hash = True
                _LOGGER.debug("client requires SECRET_HASH; retrying with it")
                init = await _initiate()
            else:
                raise
        params = init["ChallengeParameters"]
        user_id_for_srp = params["USER_ID_FOR_SRP"]
        srp_b = int(params["SRP_B"], 16)
        salt = int(params["SALT"], 16)
        secret_block_b64 = params["SECRET_BLOCK"]
        secret_block = base64.b64decode(secret_block_b64)

        hkdf = self._password_authentication_key(srp_b, salt, user_id_for_srp)

        now = datetime.datetime.now(datetime.timezone.utc)
        # Non-zero-padded day + English names, e.g. "Wed Aug 27 14:05:01 UTC 2026"
        timestamp = (
            f"{_DAYS[now.weekday()]} {_MONTHS[now.month - 1]} {now.day} "
            f"{now:%H:%M:%S} UTC {now.year}"
        )
        msg = (
            self._pool_name.encode("utf-8")
            + user_id_for_srp.encode("utf-8")
            + secret_block
            + timestamp.encode("utf-8")
        )
        signature = base64.b64encode(
            hmac.new(hkdf, msg, hashlib.sha256).digest()
        ).decode()

        async def _respond(hash_username: str) -> dict:
            return await self._idp(
                "RespondToAuthChallenge",
                {
                    "ChallengeName": "PASSWORD_VERIFIER",
                    "ClientId": self._brand.client_id,
                    "ChallengeResponses": self._maybe_secret(
                        {
                            "USERNAME": user_id_for_srp,
                            "PASSWORD_CLAIM_SECRET_BLOCK": secret_block_b64,
                            "PASSWORD_CLAIM_SIGNATURE": signature,
                            "TIMESTAMP": timestamp,
                        },
                        hash_username,
                    ),
                },
            )

        # Cognito normally wants SECRET_HASH over USER_ID_FOR_SRP here, but on
        # alias-enabled pools it can require the originally-supplied username.
        try:
            resp = await _respond(user_id_for_srp)
        except SmartShadeAuthError as err:
            if (
                "secret hash" in str(err).lower()
                and user_id_for_srp != self._username
            ):
                _LOGGER.debug(
                    "challenge SECRET_HASH rejected for USER_ID_FOR_SRP; "
                    "retrying with the supplied username"
                )
                resp = await _respond(self._username)
            else:
                raise
        result = resp.get("AuthenticationResult")
        if not result:
            raise SmartShadeAuthError(
                f"unexpected challenge: {resp.get('ChallengeName')}"
            )
        self._id_token = result["IdToken"]
        self._refresh_token = result.get("RefreshToken", self._refresh_token)
        self._capture_token_username()

    def _capture_token_username(self) -> None:
        """Remember the pool's real username from the ID token.

        REFRESH_TOKEN_AUTH validates SECRET_HASH against the actual pool
        username (the cognito:username claim), which differs from the email
        alias used to sign in. Hashing the alias there fails validation.
        """
        if not self._id_token:
            return
        try:
            payload = self._id_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except Exception:  # noqa: BLE001 - malformed token, keep the alias
            _LOGGER.debug("could not decode ID token claims")
            return
        real = claims.get("cognito:username") or claims.get("sub")
        if real and real != self._username:
            _LOGGER.debug("using pool username from ID token for refresh")
            self._refresh_username = real

    async def refresh(self) -> None:
        """Refresh the ID token using the stored refresh token.

        Two things can be wrong on a cold start, and both used to make this
        fail outright so every restart fell back to a full password login:

        1. Whether this client needs a SECRET_HASH is probed and remembered by
           `authenticate`, but a fresh object starts not knowing.
        2. The hash must be computed over the pool's real username, not the
           email alias. That is learned from an ID token, so it is only known
           after a full login unless it was persisted.

        So try the candidates rather than assuming, and remember what worked.
        """
        if not self._refresh_token:
            raise SmartShadeAuthError("no refresh token")

        # Persisted/learned pool username first, sign-in alias as a fallback.
        candidates = [self._refresh_username]
        if self._username != self._refresh_username:
            candidates.append(self._username)

        last: SmartShadeAuthError | None = None
        for username in candidates:
            # At most twice per username: once as currently configured, once
            # more if Cognito tells us the SECRET_HASH expectation is wrong.
            for _ in range(2):
                try:
                    resp = await self._idp(
                        "InitiateAuth",
                        {
                            "AuthFlow": "REFRESH_TOKEN_AUTH",
                            "ClientId": self._brand.client_id,
                            "AuthParameters": self._maybe_secret(
                                {"REFRESH_TOKEN": self._refresh_token}, username
                            ),
                        },
                    )
                except SmartShadeAuthError as err:
                    last = err
                    msg = str(err).lower()
                    if "secret_hash was not received" in msg or (
                        "configured with secret" in msg
                    ):
                        self._use_secret_hash = True
                        continue
                    if "unable to verify secret hash" in msg:
                        # Either the wrong username for the hash, or the client
                        # has no secret at all. Flip the flag once, then let the
                        # next candidate username try.
                        if self._use_secret_hash and len(candidates) == 1:
                            self._use_secret_hash = False
                            continue
                        break
                    raise
                else:
                    self._id_token = resp["AuthenticationResult"]["IdToken"]
                    self._refresh_username = username
                    self._capture_token_username()
                    _LOGGER.debug("refresh ok (secret_hash=%s)", self._use_secret_hash)
                    return

        raise last or SmartShadeAuthError("refresh failed")

    async def _ensure_token(self) -> None:
        if self._id_token:
            return
        if self._refresh_token:
            await self.refresh()
        else:
            await self.authenticate()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        body: dict | None = None,
        _retry: bool = True,
    ) -> dict:
        """Call the brand's API Gateway.

        Callers pick the verb and whether the serial rides in `params` or
        `body`; see `_shape`. Everything else -- auth header, one-shot token
        refresh, error handling -- is identical across both gateways.
        """
        await self._ensure_token()
        headers = {
            "Authorization": self._id_token,
            # The app's interceptor sends this alongside Authorization; the
            # gateway's authorizer rejects the request (401) without it.
            "IdentityProvider": "Cognito",
            "User-Agent": "AndroidApp-okhttp-user-agent",
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body)

        async with self._session.request(
            method,
            self._brand.api_base + endpoint,
            headers=headers,
            params=params or {},
            data=data,
        ) as resp:
            text = await resp.text()
            _LOGGER.debug(
                "%s %s%s params=%s -> HTTP %s: %s",
                method,
                self._brand.api_base,
                endpoint,
                params,
                resp.status,
                text[:400],
            )
            # API Gateway answers 403 "Missing Authentication Token" when the
            # path/method doesn't exist. That is a routing bug, NOT an expired
            # token, so don't burn a refresh on it (which masks the real error).
            routing_error = "missing authentication token" in text.lower()
            if resp.status == 401 and _retry and not routing_error:
                _LOGGER.debug("token rejected; refreshing and retrying once")
                self._id_token = None
                await self._ensure_token()
                return await self._request(method, endpoint, params, body, False)
            if resp.status >= 400:
                raise SmartShadeApiError(
                    f"{endpoint} HTTP {resp.status}: {text[:300]}"
                )
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw": text}

    # --- REST surface ---
    # The two gateways expose the same paths but differ in verb and in where
    # GrillNumber travels: legacy uses GET + query parameter, the newer one
    # POSTs it in the JSON body. See Brand.new_api.
    def _shape(self, serial: str) -> tuple[str, dict | None, dict | None]:
        """(method, query params, body) for a read addressed at one serial."""
        if self._brand.new_api:
            return "POST", None, {"GrillNumber": serial}
        return "GET", {"GrillNumber": serial}, None

    @property
    def app_name(self) -> str | None:
        return self._app_name

    @property
    def brand(self) -> Brand:
        return self._brand

    async def get_grill_list(self, serial: str = "") -> list[dict]:
        """List the account's devices.

        The two gateways disagree about more than the verb here: the legacy one
        takes GrillNumber as a query parameter (empty lists everything), while
        the newer one takes {"AppName": ...} in the body and no GrillNumber at
        all. Confirmed in NavMainViewModel$listGrills$1, which builds a
        JsonObject holding only AppName before calling the new interface.
        """
        if self._brand.new_api:
            method, params, body = "POST", None, {"AppName": self._app_name}
        else:
            method, params, body = self._shape(serial)
        data = await self._request(method, EP_LIST, params=params, body=body)
        _LOGGER.debug("get-grill-list raw: %s", data)
        if isinstance(data, dict):
            items = data.get("data")
            if isinstance(items, list):
                return items
        return []

    async def get_state(self, serial: str) -> dict:
        method, params, body = self._shape(serial)
        return await self._request(method, EP_STATE, params=params, body=body)

    async def send_command(
        self, serial: str, cmd_key: str, value: float, cid: int
    ) -> dict:
        """Send one RF press via the hub's device shadow.

        Shape confirmed from a live shadow:
            {"state": {"desired": {
                "MODE": 1, "SchCommand": 0, "CID": "<n>",
                "CMD_LST": {"CMD_steps": [{"C": "1:4:1:0", "D": 0.2}]}}}}
        CID is a monotonically increasing command id; the hub echoes the one it
        executed back as reported.LastCID.
        """
        desired = {
            "MODE": 1,
            "SchCommand": 0,
            "CID": str(cid),
            "CMD_LST": {"CMD_steps": [{"C": cmd_key, "D": value}]},
        }
        command = json.dumps({"state": {"desired": desired}})
        _LOGGER.debug("send_command %s -> %s", serial, command)
        if self._brand.new_api:
            return await self._request(
                "POST", EP_COMMAND, body={"GrillNumber": serial, "Command": command}
            )
        return await self._request(
            "POST",
            EP_COMMAND,
            params={"GrillNumber": serial},
            body={"Command": command},
        )


async def validate_brand(
    session: aiohttp.ClientSession,
    username: str,
    password: str,
    brand: Brand,
    attempts: list[dict] | None = None,
) -> tuple[SmartShadeApi, list[dict]]:
    """Sign in to one brand and prove the account is usable.

    The brand is chosen by the user, never guessed. An earlier version probed
    both Cognito pools in turn, which meant a Liberty owner's credentials were
    offered to the Smart Shade pool first -- a failed login against a pool they
    have no account in, and two lockout attempts for one typo. Asking is both
    kinder and easier: the answer is the icon on their phone.

    Success requires the device list, not merely a token. A brand that
    authenticates but cannot list devices is not usable, and failing here means
    no config entry is created -- far better than a half-working install whose
    buttons silently do nothing.

    Pass `attempts` to collect a record of what happened. It holds no
    credentials -- only the brand key, the outcome and the exception class.
    """
    log = attempts if attempts is not None else []
    api = SmartShadeApi(session, username, brand=brand)

    try:
        await api.authenticate(password)
    except SmartShadeAuthError as err:
        # Cognito usernames are case-sensitive unless the pool was created
        # otherwise, so "Bills@..." is a different user from "bills@...".
        # People capitalise the first letter of an email all the time, and the
        # resulting "User does not exist" gives no hint that case is the
        # problem. Retry once in lower case rather than silently lowercasing
        # up front, which would break a genuinely capitalised account.
        lowered = username.lower()
        if "user does not exist" in str(err).lower() and lowered != username:
            _LOGGER.debug("brand %s: retrying sign-in in lower case", brand.key)
            api = SmartShadeApi(session, lowered, brand=brand)
            try:
                await api.authenticate(password)
            except SmartShadeAuthError:
                raise err from None
            else:
                _LOGGER.info("signed in after lower-casing the email")
                log.append({
                    "brand": brand.key,
                    "result": "auth OK after lower-casing the email",
                    "app_name": brand.app_name,
                    "detail": None,
                })
                hubs = await api.get_grill_list()
                log.append({
                    "brand": brand.key,
                    "result": f"MATCHED, {len(hubs)} device(s)",
                    "app_name": brand.app_name,
                    "detail": None,
                })
                return api, hubs
        _LOGGER.debug("brand %s: auth rejected (%s)", brand.key, err)
        log.append(
            {
                "brand": brand.key,
                "result": "auth rejected",
                "app_name": brand.app_name,
                "detail": type(err).__name__,
            }
        )
        raise

    try:
        hubs = await api.get_grill_list()
    except SmartShadeApiError as err:
        _LOGGER.debug("brand %s: authed but list failed (%s)", brand.key, err)
        log.append(
            {
                "brand": brand.key,
                "result": "authenticated, device list FAILED",
                # AppName is ours and safe; the error is the server's and gets
                # reduced to endpoint + status in the report.
                "app_name": brand.app_name,
                "detail": str(err),
            }
        )
        raise

    log.append(
        {
            "brand": brand.key,
            "result": f"MATCHED, {len(hubs)} device(s)",
            "app_name": brand.app_name,
            "detail": None,
        }
    )
    _LOGGER.info(
        "signed in to %s: %d device(s)", brand.name, len(hubs)
    )
    return api, hubs
